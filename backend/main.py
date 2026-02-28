from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List
from collections import deque
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
import json
import uuid
import io
import base64
import pyotp
import qrcode

from logic import database, mock_ai
from logic.database import AuditAction

# ตั้งค่า Security เบื้องต้น
SECRET_KEY = "thai_stylometry_v2_very_secure_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI(title="Thai Stylometry V2 API")

# --------- STARTUP ---------
@app.on_event("startup")
async def startup_event():
    """
    เรียก create_audit_log_table() ตอนเริ่ม Server
    เพื่อให้มั่นใจว่าโครงสร้างตาราง Audit Log พร้อมใช้งานก่อน Request แรกเข้ามา
    """
    database.create_audit_log_table()

# --------- AUDIT HELPERS ---------
def get_client_ip(request: Request) -> str:
    """
    ดึง IP Address จริงของ Client
    รองรับกรณีที่ผ่าน Reverse Proxy (X-Forwarded-For)
    การเก็บ IP ช่วยตรวจจับ:
      - Brute-force จาก IP เดียวกัน
      - การเข้าใช้งานจากประเทศ/ภูมิภาคผิดปกติ (Geo-anomaly)
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str:
    """
    ดึง User-Agent (Browser/OS/Device) จาก Request Header
    การเก็บ User-Agent ช่วย:
      - ตรวจจับ Device ที่ไม่เคยใช้มาก่อน (New Device Detection)
      - ระบุ Automated Bot / Script ที่โจมตีระบบ
      - ประกอบ Digital Fingerprint ของ Session
    """
    return request.headers.get("user-agent", "unknown")

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

# ========================================
# MFA PENDING SESSIONS
# ========================================
# pending_mfa_sessions: เก็บ Session ชั่วคราวที่รอการยืนยัน TOTP
# Key   = UUID token (ส่งกลับให้ Frontend)
# Value = {"username": str, "type": "login" | "setup"}
#
# "login"  — ผู้ใช้ผ่านรหัสผ่านแล้ว รอใส่ TOTP ก่อนรับ JWT
# "setup"  — ผู้ใช้เพิ่งสมัคร รอ Scan QR และยืนยัน TOTP ครั้งแรก
#
# Token มีอายุสั้น (ควร expire ใน Production) เพื่อป้องกัน
# การนำ Session Token เก่าที่ยังไม่ verified มาใช้ซ้ำ
MFA_APP_NAME = "ThaiStylometryDID"
pending_mfa_sessions: Dict[str, dict] = {}


def _create_mfa_session(username: str, session_type: str) -> str:
    """สร้าง UUID token สำหรับ MFA Session และบันทึกลง pending_mfa_sessions"""
    token = str(uuid.uuid4())
    pending_mfa_sessions[token] = {"username": username, "type": session_type}
    return token


def _pop_mfa_session(token: str, expected_type: str) -> str:
    """
    ดึงและลบ MFA Session ออกจาก dict
    Single-use: ใช้ครั้งเดียวแล้วหมดอายุทันที ป้องกัน Token Reuse
    """
    session = pending_mfa_sessions.pop(token, None)
    if not session or session["type"] != expected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired MFA session token",
        )
    return session["username"]


# --------- REST API ENDPOINTS ---------

from pydantic import BaseModel
class AuthModel(BaseModel):
    username: str
    password: str

class ContactAdd(BaseModel):
    contact_username: str

class MfaSetupRequest(BaseModel):
    setup_token: str   # UUID ที่ได้จาก /api/register

class MfaVerifyRequest(BaseModel):
    token: str         # UUID ที่ได้จาก /api/register (setup) หรือ /api/login (login)
    code: str          # รหัส TOTP 6 หลักจาก Authenticator App

@app.post("/api/register")
async def register(request: Request, user: AuthModel):
    hashed_pw = get_password_hash(user.password)
    if database.create_user(user.username, hashed_pw):
        # บันทึก: การสร้างตัวตนใหม่ในระบบ Digital ID
        # สำคัญสำหรับตรวจสอบว่ามีการสร้าง Account จำนวนมากผิดปกติ (Mass Registration)
        database.save_audit_log(
            action=AuditAction.REGISTER,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            user_id=user.username,
        )
        # MFA บังคับ: สร้าง setup_token ส่งกลับไปให้ Frontend
        # Frontend ต้องนำ setup_token ไปเรียก /api/auth/mfa/setup เพื่อสร้าง QR Code
        # จนกว่าจะ verify สำเร็จ ผู้ใช้จะยังไม่ได้รับ JWT Cookie
        setup_token = _create_mfa_session(user.username, "setup")
        return {
            "msg": "User created successfully",
            "mfa_setup_required": True,
            "setup_token": setup_token,
        }
    raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/api/login")
async def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = database.get_user(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        # บันทึก: การ Login ล้มเหลว — หัวใจของการตรวจจับ Brute-force
        # user_id อาจเป็น None หรือชื่อที่ป้อนมา (อาจไม่มีในระบบ)
        # การเก็บ IP + Timestamp ช่วยนับความถี่การพยายาม Login ในช่วงเวลาหนึ่ง
        database.save_audit_log(
            action=AuditAction.LOGIN_FAILED,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            user_id=form_data.username or None,
            extra_data={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    current_ip = get_client_ip(request)
    current_ua = get_user_agent(request)

    # ---- Adaptive Authentication ----
    # เปรียบเทียบ IP และ User-Agent ปัจจุบันกับประวัติ LOGIN_SUCCESS
    # ถ้าพบว่าเป็น Device/Network ที่ไม่เคยเห็นมาก่อน → บังคับ MFA
    # เหตุผล: แม้รหัสผ่านจะถูกต้อง แต่ Device ใหม่อาจหมายความว่า
    #   1. Credential ถูกขโมยและนำไปใช้บน Device อื่น
    #   2. ผู้ใช้ถูก Phishing แล้วมีคนอื่น Login แทน
    known_ips, known_uas = database.get_known_devices(form_data.username)
    is_new_device = (current_ip not in known_ips) or (current_ua not in known_uas)

    mfa_required = user.get("is_mfa_enabled", False) or is_new_device

    if mfa_required:
        if is_new_device and not user.get("is_mfa_enabled", False):
            # Adaptive Auth: Device ใหม่ แต่ยังไม่ได้เปิด MFA
            # บันทึกเหตุการณ์ไว้เพื่อ Audit และแจ้ง Frontend ให้ Setup MFA ก่อน
            database.save_audit_log(
                action=AuditAction.ADAPTIVE_MFA,
                ip_address=current_ip,
                user_agent=current_ua,
                user_id=user["username"],
                extra_data={"reason": "new_device_detected", "mfa_enabled": False},
            )
            # สร้าง setup_token ให้ผู้ใช้ไป Setup MFA ก่อน
            setup_token = _create_mfa_session(user["username"], "setup")
            return {
                "mfa_required": True,
                "adaptive_auth": True,
                "mfa_enabled": False,
                "setup_token": setup_token,
                "msg": "New device detected. Please set up MFA before proceeding.",
            }

        # MFA เปิดอยู่ (หรือ is_new_device + mfa_enabled) → ออก session_token เพื่อรอ TOTP
        # ยังไม่ Set Cookie — รอให้ผ่าน /api/auth/mfa/verify ก่อน
        if is_new_device:
            database.save_audit_log(
                action=AuditAction.ADAPTIVE_MFA,
                ip_address=current_ip,
                user_agent=current_ua,
                user_id=user["username"],
                extra_data={"reason": "new_device_detected", "mfa_enabled": True},
            )
        session_token = _create_mfa_session(user["username"], "login")
        return {
            "mfa_required": True,
            "adaptive_auth": is_new_device,
            "session_token": session_token,
        }

    # ---- Login สำเร็จ ไม่ต้อง MFA ----
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )

    # บันทึก: การ Login สำเร็จ — ยืนยันตัวตนถูกต้อง
    # ใช้ติดตาม Session ใหม่และวิเคราะห์ Pattern เวลาการเข้าใช้งาน (Time-based Anomaly)
    database.save_audit_log(
        action=AuditAction.LOGIN_SUCCESS,
        ip_address=current_ip,
        user_agent=current_ua,
        user_id=user["username"],
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

# ========================================
# MFA ENDPOINTS
# ========================================

@app.post("/api/auth/mfa/setup")
async def mfa_setup(data: MfaSetupRequest):
    """
    Step 1 ของ MFA Setup: สร้าง TOTP Secret และคืน QR Code

    Flow:
      1. ตรวจสอบ setup_token จาก pending_mfa_sessions
      2. สร้าง Shared Secret ด้วย pyotp.random_base32()
      3. บันทึก Secret ลงข้อมูลผู้ใช้ (ยังไม่ enable — รอ verify)
      4. สร้าง otpauth:// URL → วาด QR Code → แปลงเป็น Base64 PNG
      5. คืนค่า: { qr_code_base64, secret } ให้ Frontend แสดงผล

    หมายเหตุ: ไม่ expire setup_token ที่นี่ — ยังต้องใช้ใน /api/auth/mfa/verify
    จึงเก็บ token ไว้ใน pending_mfa_sessions จนกว่าจะ verify สำเร็จ
    """
    # ค้นหา session โดยไม่ pop (ยังต้องใช้ใน verify)
    session = pending_mfa_sessions.get(data.setup_token)
    if not session or session["type"] != "setup":
        raise HTTPException(status_code=400, detail="Invalid or expired setup token")

    username = session["username"]
    user = database.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # สร้าง Shared Secret: Base32 string ขนาด 32 chars (160 bits)
    # Secret นี้จะถูกแชร์ระหว่าง Server และ Authenticator App ของผู้ใช้
    # ใน Production ควรเข้ารหัสด้วย Fernet ก่อนบันทึกลง Database
    secret = pyotp.random_base32()
    database.set_mfa_secret(username, secret)

    # สร้าง otpauth:// URI มาตรฐาน RFC 6238
    # Format: otpauth://totp/<AppName>:<username>?secret=<secret>&issuer=<AppName>
    # URI นี้คือข้อมูลที่ QR Code เข้ารหัสไว้ — Authenticator App จะอ่านและบันทึก Secret
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=MFA_APP_NAME,
    )

    # วาด QR Code และแปลงเป็น Base64 PNG สำหรับส่งไปยัง Frontend
    qr_img = qrcode.make(totp_uri)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "qr_code_base64": qr_b64,      # ใช้ใน <img src="data:image/png;base64,...">
        "secret": secret,              # แสดงเป็น Backup Code ให้ผู้ใช้บันทึกไว้
        "issuer": MFA_APP_NAME,
    }


@app.post("/api/auth/mfa/verify")
async def mfa_verify(request: Request, response: Response, data: MfaVerifyRequest):
    """
    ยืนยัน TOTP Code และ Complete MFA Flow (Setup หรือ Login)

    สำหรับ type="setup":
      - ตรวจสอบ TOTP ครั้งแรก → เปิดใช้งาน MFA → ออก JWT Cookie
      - บันทึก MFA_SETUP ใน Audit Log

    สำหรับ type="login":
      - ตรวจสอบ TOTP → ออก JWT Cookie
      - บันทึก MFA_VERIFY + LOGIN_SUCCESS ใน Audit Log

    หลักการ TOTP Verification:
      pyotp.TOTP(secret).verify(code) จะ:
        1. คำนวณรหัสที่ถูกต้อง ณ เวลาปัจจุบัน (±1 window = ±30 วิ)
        2. เปรียบเทียบแบบ Constant-time (ป้องกัน Timing Attack)
        3. คืนค่า True ถ้าตรงกัน
    """
    # ตรวจสอบว่า token เป็น "setup" หรือ "login"
    session = pending_mfa_sessions.get(data.token)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired MFA token")

    session_type = session["type"]
    if session_type not in ("setup", "login"):
        raise HTTPException(status_code=400, detail="Invalid session type")

    # ดึง username แล้ว pop session ออก (Single-use token)
    username = _pop_mfa_session(data.token, session_type)
    user = database.get_user(username)
    if not user or not user.get("mfa_secret"):
        raise HTTPException(status_code=400, detail="MFA not configured for this user")

    # ตรวจสอบ TOTP code ด้วย Shared Secret
    totp = pyotp.TOTP(user["mfa_secret"])
    if not totp.verify(data.code, valid_window=1):
        # บันทึก: TOTP ล้มเหลว — อาจเป็น Replay Attack หรือนาฬิกาผิดเวลา
        database.save_audit_log(
            action=AuditAction.MFA_FAILED,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            user_id=username,
            extra_data={"session_type": session_type},
        )
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    audit_action = AuditAction.MFA_SETUP if session_type == "setup" else AuditAction.MFA_VERIFY

    if session_type == "setup":
        # เปิดใช้งาน MFA อย่างเป็นทางการหลังยืนยัน TOTP ครั้งแรกสำเร็จ
        database.verify_and_enable_mfa(username)

    # บันทึก Audit Log
    database.save_audit_log(
        action=audit_action,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        user_id=username,
        extra_data={"session_type": session_type},
    )
    # บันทึก LOGIN_SUCCESS ด้วยสำหรับ flow login
    if session_type == "login":
        database.save_audit_log(
            action=AuditAction.LOGIN_SUCCESS,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            user_id=username,
            extra_data={"via": "mfa_verify"},
        )

    # ออก JWT Cookie หลังผ่าน TOTP
    access_token = create_access_token(
        data={"sub": username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"msg": "MFA verified. Login successful.", "mfa_setup_complete": session_type == "setup"}


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

@app.get("/api/me/logs")
async def get_my_audit_logs(current_user: str = Depends(get_current_user_from_cookie)):
    """
    ดึงประวัติความปลอดภัย (Audit Logs) ของผู้ใช้ที่ล็อกอินอยู่

    เหตุผลที่ต้องมี Endpoint นี้ตามหลัก Digital ID:
    - ความโปร่งใส (Transparency): ผู้ใช้มีสิทธิ์รู้ว่าระบบบันทึกอะไรเกี่ยวกับตัวเองบ้าง
    - ตรวจสอบการบุกรุก: ผู้ใช้สามารถดูว่ามีการ LOGIN_FAILED ซ้ำๆ หรือมี
                          STYLOMETRY_ALERT ที่บ่งชี้ว่าบัญชีถูกยึดหรือไม่
    - สิทธิ์การเข้าถึงข้อมูล: ตามมาตรา PDPA ผู้ใช้มีสิทธิ์ขอดูข้อมูลส่วนตัว

    Returns:
        {"logs": [...]} — รายการ Audit Logs ทั้งหมดของผู้ใช้ เรียงตาม timestamp
    """
    logs = database.get_audit_logs(user_id=current_user)
    return {"logs": logs}

@app.get("/api/contacts/search/{query}")
async def search_contacts(query: str, current_user: str = Depends(get_current_user_from_cookie)):
    # ค้นหาชื่อเพื่อน
    users = database.get_all_users()
    matched = [u for u in users if query.lower() in u.lower() and u != current_user]
    return {"results": matched}

@app.post("/api/contacts/add")
async def add_contact(request: Request, data: ContactAdd, current_user: str = Depends(get_current_user_from_cookie)):
    success = database.add_contact(current_user, data.contact_username)
    if success:
        # บันทึก: การสร้างความสัมพันธ์ใหม่ใน Social Graph
        # เก็บทั้ง initiator และ target เพื่อ Map ความสัมพันธ์ระหว่าง Digital Identity
        database.save_audit_log(
            action=AuditAction.ADD_CONTACT,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            user_id=current_user,
            extra_data={"contact_added": data.contact_username},
        )

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

            # บันทึก Audit Log สำหรับการส่งข้อความ
            # เก็บเฉพาะ Metadata (sender, receiver, timestamp) ไม่เก็บเนื้อหาข้อความ
            # เพื่อความเป็นส่วนตัวตามหลัก Data Minimization (PDPA/GDPR)
            # แต่ยังสามารถวิเคราะห์ความถี่และความสัมพันธ์ระหว่าง Digital Identity ได้
            ws_ip = websocket.client.host if websocket.client else "unknown"
            ws_ua = websocket.headers.get("user-agent", "unknown")
            database.save_audit_log(
                action=AuditAction.SEND_MESSAGE,
                ip_address=ws_ip,
                user_agent=ws_ua,
                user_id=sender,
                extra_data={"receiver": receiver, "content_length": len(content)},
            )

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
                    # บันทึก Audit Log: ตรวจพบรูปแบบการเขียนผิดปกติ
                    # เหตุการณ์นี้สำคัญมากสำหรับ Digital ID —
                    # อาจหมายความว่ามีคนอื่นใช้บัญชีนี้ (Account Takeover)
                    database.save_audit_log(
                        action=AuditAction.STYLOMETRY_ALERT,
                        ip_address=ws_ip,
                        user_agent=ws_ua,
                        user_id=sender,
                        extra_data={"stylometry_score": round(score, 4), "threshold": 0.95},
                    )
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
