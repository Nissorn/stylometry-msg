from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List
from collections import deque
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
import json

from logic import database, mock_ai

# ตั้งค่า Security เบื้องต้น
SECRET_KEY = "thai_stylometry_v2_very_secure_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI(title="Thai Stylometry V2 API")

# --------- CORS CONFIGURATION ---------
# อนุญาตเฉพาะ Frontend Astro/React จากพอร์ต 4321, 4322, 4323 (และ credentials=True เพื่อให้รับ-ส่ง Cookie ได้)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4321", "http://127.0.0.1:4321",
        "http://localhost:4322", "http://127.0.0.1:4322",
        "http://localhost:4323", "http://127.0.0.1:4323"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Set-Cookie", "Authorization", "Access-Control-Allow-Origin"],
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return {}

# --------- SECURITY UTILS ---------
def verify_password(plain_password, hashed_password):
    # ใช้ bcrypt เพื่อตรวจเช็ครหัสผ่าน
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    # แปลง password เป็น bytes ก่อน hash
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_from_cookie(request: Request):
    """
    ดึง JWT Token จาก HTTP Only Cookie ของ Request
    ใช้ป้องกัน XSS (Cross-Site Scripting) เนื่องจาก JavaScript ฝั่ง Client จะอ่านค่า Cookie ไม่ได้
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        # 📌 ตัดคำว่า "Bearer " ออก ถ้ามีการแนบมาด้วย
        # ปกติเวลาเราเซ็ตค่า "Bearer [token]" ลงใน Cookie, Browser อาจจะมอง "Bearer" และ "[token]"
        # เป็น string เดียวกัน แต่ต้องระวังอักขระพิเศษ หรือถ้าเอาไปใช้ตรง ๆ ก็ให้ตัดก่อน
        # โดยจัดการกับกรณีที่ติด space หรือหลุด URL encoded มาด้วย
        token_str = token.strip()
        if token_str.lower().startswith("bearer "):
            token_str = token_str[7:].strip()
        elif token_str.lower().startswith("bearer%20"):
            token_str = token_str[9:].strip()
            
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user_from_ws(token: str):
    """
    Validate JWT Token สำหรับ WebSocket
    จุดสำคัญด้านความปลอดภัย: ไม่ปล่อยให้เช็คเพียงแค่ Username เพราะเสี่ยงต่อดึงข้อมูล (Spoofing)
    """
    try:
        # ระบบ WebSocket อาจส่งคำว่า Bearer หรือเพียวๆมาก็ได้
        token_str = token.strip()
        if token_str.lower().startswith("bearer "):
            token_str = token_str[7:].strip()
        elif token_str.lower().startswith("bearer%20"):
            token_str = token_str[9:].strip()
            
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

# --------- WEBSOCKET CONNECTION MANAGER ---------
class ConnectionManager:
    def __init__(self):
        # แมป Dictionary ระหว่าง Username เข้ากับ WebSocket Object
        # การใช้แบบนี้ช่วยให้ระบบรู้จักว่า User คนไหนเชื่อมต่ออยู่ผ่าน Connection ไหน
        self.active_connections: Dict[str, WebSocket] = {}
        # แมป User เข้ากับ Rolling Window ของข้อความ (1 คนมี deque ของตัวเองไว้เก็บข้อความ)
        # deque(maxlen=5) จะช่วยจัดการลบข้อความเก่าสุดอัตโนมัติเมื่อครบ 5 รายการ (In-memory)
        self.user_message_windows: Dict[str, deque] = {}

    async def connect(self, ws: WebSocket, username: str):
        await ws.accept()
        self.active_connections[username] = ws
        if username not in self.user_message_windows:
            self.user_message_windows[username] = deque(maxlen=5)

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]
        # ตัว Rolling window สามารถเก็บไว้หรือเคลียร์ทิ้งก็ได้ 
        # เพื่อความปลอดภัยและขึ้นรอบใหม่ เราอาจจะเคลียร์ทิ้งตอน disconnect
        if username in self.user_message_windows:
            del self.user_message_windows[username]

    async def send_personal_message(self, message: str, username: str):
        # ส่งหาเฉพาะตัวบุคคล (เช่น ฝั่งผู้รับ, หรือส่ง Alert ไปให้ฝั่งคนพิมพ์)
        ws = self.active_connections.get(username)
        if ws:
            await ws.send_text(message)

manager = ConnectionManager()

# --------- REST API ENDPOINTS ---------

from pydantic import BaseModel
class AuthModel(BaseModel):
    username: str
    password: str

class ContactAdd(BaseModel):
    contact_username: str

@app.post("/api/register")
async def register(user: AuthModel):
    hashed_pw = get_password_hash(user.password)
    # สมัครสมาชิก
    if database.create_user(user.username, hashed_pw):
        return {"msg": "User created successfully"}
    raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/api/login")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = database.get_user(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    
    # 📌 Security Upgrade: ส่ง Token กลับไปทาง Set-Cookie (HttpOnly, Secure, SameSite=Lax)
    # เพื่อป้องกันไม่ให้ฝั่ง Frontend ใช้ JavaScript เข้าถึง Token (XSS Protection)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False,    # ⚠️ ปิด secure=True ชั่วคราวก่อน เพราะตอนพัฒนาเราใช้ HTTP (localhost) ถ้ายอมให้เป็น True คุกกี้จะไม่ยอมบันทึกบน Browser
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"msg": "Login successful"}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"msg": "Logout successful"}

@app.get("/api/me")
async def get_me(current_user: str = Depends(get_current_user_from_cookie)):
    """
    Endpoint นี้สำหรับใช้เป็น Auth Guard ในฝั่ง Frontend
    โดยจะตรวจสอบสถานะจาก HttpOnly Cookie เพื่อยืนยันว่าผู้ใช้คนนี้ยังมี Session ที่ถูกต้อง (ยังไม่หมดอายุและ valid)
    หาก Cookie หาย หรือ Token หมดอายุ ตัวอ้างอิง get_current_user_from_cookie จะบังคับโยน HTTP 401 ออกมาอัตโนมัติ
    """
    return {"username": current_user, "status": "authenticated"}

@app.get("/api/contacts/search/{query}")
async def search_contacts(query: str, current_user: str = Depends(get_current_user_from_cookie)):
    # ค้นหาชื่อเพื่อน
    users = database.get_all_users()
    matched = [u for u in users if query.lower() in u.lower() and u != current_user]
    return {"results": matched}

@app.post("/api/contacts/add")
async def add_contact(data: ContactAdd, current_user: str = Depends(get_current_user_from_cookie)):
    success = database.add_contact(current_user, data.contact_username)
    if success:
        # 📌 แจ้งเตือนแบบ Real-time (System Notification)
        # ส่งไปหา User B (contact_username) ว่า User A (current_user) แอดและเริ่มสนทนาแล้ว
        notification_payload = {
            "type": "CONTACT_ADDED",
            "message": f"{current_user} ได้เริ่มการสนทนากับคุณ"
        }
        await manager.send_personal_message(json.dumps(notification_payload), data.contact_username)

        return {"msg": "Contact added"}
    raise HTTPException(status_code=400, detail="Could not add contact")

@app.get("/api/contacts/list")
async def list_contacts(current_user: str = Depends(get_current_user_from_cookie)):
    contacts = database.list_contacts(current_user)
    return {"contacts": contacts}

@app.get("/api/messages/{target_username}")
async def get_chat_history(target_username: str, current_user: str = Depends(get_current_user_from_cookie)):
    messages = database.get_messages(current_user, target_username)
    return {"messages": messages}

# --------- WEBSOCKET CHAT ---------
@app.websocket("/ws/chat/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # 📌 WebSocket Security: ตรวจสอบความถูกต้องของ Token ก่อนให้เชื่อมต่อ
    # เพื่อป้องกันผู้ไม่ประสงค์ดีปลอมตัวโดยระบุแค่พารามิเตอร์ username
    # โดยให้อ่านจาก HttpOnly Cookie (access_token) ซึ่งปลอดภัยกว่าและป้องกัน XSS ได้
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    valid_user = get_current_user_from_ws(token)
    if not valid_user or valid_user != username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            receiver = payload.get("receiver")
            content = payload.get("content")
            
            if not receiver or not content:
                continue
                
            sender = username  # กำหนดชัดเจนว่า sender คือคนที่เชื่อมต่อท่อนี้
            
            # 📌 1. Data Flow & Encryption: บันทึกข้อความลง DB (ที่ใช้การเข้ารหัส Fernet อยู่แล้ว)
            database.save_message(sender=sender, receiver=receiver, content=content)
            
            # 📌 2. ส่งข้อความแชทไปหาผู้รับ (Receiver) ตามปกติ (ถ้ากำลังออนไลน์)
            msg_to_send = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            await manager.send_personal_message(json.dumps(msg_to_send), receiver)
            
            # 📌 3. AI Logic Integration: กฎเหล็ก (STRICT RULE) ของการแยกคนส่ง-คนรับ
            # ระบบจะนำข้อความใส่เข้า deque ของ "sender" (คนที่พิมพ์ข้อความ) เท่านั้น
            # ห้ามเอา receiver (ผู้รับ) หรือข้อมูลอื่นมาเป็น Key เด็ดขาด เพื่อป้องกัน AI เอาประโยคคนอื่นมาสลับคน
            user_dq = manager.user_message_windows[sender]
            user_dq.append(content)
            
            count = len(user_dq)
            score = None
            
            # ตรวจตราด้วยแบบจำลอง 3 ฐานข้อมูลเมื่อครบ 5 ข้อความของคนพิมพ์คนนี้
            if count == 5:
                # ส่ง Array list ของข้อความทั้ง 5 ไปหา AI Mock สำหรับคนส่ง
                score = mock_ai.simulate_3_brains(list(user_dq))
                
                # ถ้าคะแนนต่ำกว่าเกณฑ์ ให้ส่ง SECURITY_FREEZE
                if score < 0.95:
                    alert_payload = {
                        "type": "SECURITY_FREEZE",
                        "score": round(score, 4)
                    }
                    await manager.send_personal_message(json.dumps(alert_payload), sender)
            
            # 📌 4. บังคับส่งสถานะกลับ (Strict Routing): ส่ง SECURITY_UPDATE กลับไปหา ท่อของคนส่ง (sender) เท่านั้น
            # เช็คให้ชัวร์ว่าจะไม่มีทางถูกส่งไปหา receiver อย่างเด็ดขาด
            update_payload = {
                "type": "SECURITY_UPDATE",
                "count": count,
                "score": round(score, 4) if score is not None else None
            }
            await manager.send_personal_message(json.dumps(update_payload), sender)
                    
    except WebSocketDisconnect:
        manager.disconnect(username)
