from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, List
from collections import deque
from datetime import datetime, timedelta
from jose import JWTError, jwt
import asyncio
import bcrypt
import json
import uuid
import io
import base64
import pyotp
import qrcode
import httpx

from logic import database, bot
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
    # สร้าง User system_bot ในฐานข้อมูลถ้ายังไม่มี
    # (จำเป็นสำหรับ get_messages ที่ต้องการ user ทั้งสองฝั่งมีอยู่)
    database.ensure_system_bot()

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
        # [NEW] เก็บ Trust Score แบบ Real-time ตาม Session ของคนนั้น (คะแนนเต็ม 100)
        self.user_trust_scores: Dict[str, float] = {}
        # [NEW] เก็บประโยคแชท 5 ประโยคที่สร้างคะแนนต่ำ เพื่อรอ Retrain ตอน Verified
        self.suspicious_buffer: Dict[str, List[str]] = {}
        # [NEW] Per-user asyncio.Lock เพื่อป้องกัน Race Condition บน Trust Score EMA
        self.ai_prediction_locks: Dict[str, asyncio.Lock] = {}

    async def connect(self, ws: WebSocket, username: str):
        await ws.accept()
        self.active_connections[username] = ws
        if username not in self.user_message_windows:
            self.user_message_windows[username] = deque(maxlen=5)
        if username not in self.user_trust_scores:
            self.user_trust_scores[username] = 100.0  # Initial Score
        if username not in self.suspicious_buffer:
            self.suspicious_buffer[username] = []
        if username not in self.ai_prediction_locks:
            self.ai_prediction_locks[username] = asyncio.Lock()

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


async def _trigger_retrain_and_unfreeze(username: str):
    """
    Real-time Feedback Loop: ดึงข้อความใน Buffer ไป Fine-tune AI ทันทีที่ปลดล็อคสำเร็จ
    """
    if username in manager.user_trust_scores:
        manager.user_trust_scores[username] = 100.0  # Reset Trust Score กลับเป็น 100 เต็ม
        
    suspicious_msgs = manager.suspicious_buffer.get(username, [])
    if suspicious_msgs:
        # ยิง HTTP Request เบื้องหลังไปอัปเดตโมเดล (Background Task)
        asyncio.create_task(_send_retrain_request(username, suspicious_msgs))
        # Clear buffer
        manager.suspicious_buffer[username] = []

    # ส่งคำสั่ง UNFREEZE กลับไปเปิดแชทที่ถูก Freeze ไว้
    unfreeze_payload = {"type": "UNFREEZE", "score": 100.0}
    await manager.send_personal_message(json.dumps(unfreeze_payload), username)


async def _send_retrain_request(username: str, suspicious_msgs: List[str]):
    # ดึงประวัติที่ผ่านมา 30 ข้อความไปเป็น historical สำหรับป้องกัน Catastrophic Forgetting
    history_records = database.get_messages(username, "system_bot")
    # เอาเฉพาะข้อความที่ผู้ใช้พิมพ์
    user_historical = [msg["content"] for msg in history_records if msg["sender"] == username][-30:]
    
    if not user_historical:
        # Fallback ในกรณีประวัติน้อย
        user_historical = suspicious_msgs * 5
        
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "user_id": username,
                "historical_messages": user_historical,
                "new_messages": suspicious_msgs
            }
            res = await client.post("http://localhost:8001/api/retrain_personal", json=payload)
            res.raise_for_status()
            print(f"✅ Auto-Retrain Success for {username}. AI weights adapted!")
    except Exception as e:
        print(f"❌ Auto-Retrain Failed for {username}: {e}")


async def _evaluate_trust_score(sender: str, sliding_window: List[str], ws_ip: str, ws_ua: str):
    """
    Background task: ยิง /api/predict แบบ Non-blocking แล้วอัปเดต EMA Trust Score

    Flow:
      1. ตรวจ per-user Lock — ถ้ามีงานค้างอยู่ให้ข้ามเพื่อป้องกัน Race Condition
      2. POST /api/predict -> ai_score
      3. Log: [Old Score] -> [AI Prediction Score] -> [New EMA Score]
      4. อัปเดต EMA ใน manager.user_trust_scores
      5. ส่ง SECURITY_UPDATE (score เท่านั้น) กลับหา sender
      6. ถ้าคะแนนต่ำเกินเกณฑ์ ยิง SECURITY_FREEZE alert
    """
    lock = manager.ai_prediction_locks.get(sender)
    if lock is None or lock.locked():
        # มีการประเมินค้างอยู่แล้ว — ข้ามเพื่อไม่ให้คะแนน EMA อัปเดตไม่เป็นลำดับ
        print(f"⏭️  [TrustScore] {sender}: Evaluation skipped (lock busy)")
        return

    async with lock:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                ai_payload = {"user_id": sender, "messages": sliding_window}
                response = await client.post("http://localhost:8001/api/predict", json=ai_payload)

                if response.status_code in (400, 404):
                    print(f"⚠️  [TrustScore] {sender}: AI Model missing or not calibrated — skipped.")
                    return

                response.raise_for_status()
                ai_data = response.json()

                raw_ai = float(ai_data.get("trust_score", 1.0))

                # Normalise to 0-100 regardless of whether the model returns
                # a probability (0.0-1.0) or a percentage (0-100).
                normalized_ai = raw_ai if raw_ai > 1.0 else raw_ai * 100.0

                old_score = manager.user_trust_scores.get(sender, 100.0)

                # EMA: 0.8 weight on history keeps the score stable for real users;
                # 0.2 weight on the new AI reading lets genuine anomalies still decay it.
                new_score = (old_score * 0.8) + (normalized_ai * 0.2)
                new_score = max(0.0, min(100.0, new_score))

                manager.user_trust_scores[sender] = new_score

                # 📊 Score audit log — shows exact math every cycle
                print(f"🧮 Math Check: Old={old_score:.2f}, AI={normalized_ai:.2f}, New={new_score:.2f}")
                print(f"📊 [TrustScore] {sender}: {old_score:.1f} → AI={normalized_ai:.1f} → EMA={new_score:.1f}")

                # ส่ง SECURITY_UPDATE พร้อม score กลับหา sender
                score_payload = {
                    "type": "SECURITY_UPDATE",
                    "score": round(new_score, 4),
                }
                await manager.send_personal_message(json.dumps(score_payload), sender)

                # Multi-Level Threshold Alert (raised thresholds — less aggressive)
                freeze_level = None
                if new_score < 30:
                    freeze_level = "MFA"
                elif new_score < 50:
                    freeze_level = "PASSWORD"

                if freeze_level:
                    manager.suspicious_buffer[sender] = sliding_window
                    database.save_audit_log(
                        action=AuditAction.STYLOMETRY_ALERT,
                        ip_address=ws_ip,
                        user_agent=ws_ua,
                        user_id=sender,
                        extra_data={"score": round(new_score, 2), "level": freeze_level},
                    )
                    alert_payload = {
                        "type": "SECURITY_FREEZE",
                        "level": freeze_level,
                        "score": round(new_score, 2),
                    }
                    await manager.send_personal_message(json.dumps(alert_payload), sender)

        # ─── Graceful Degradation: all AI-service failure modes are caught here.
        # None of these exceptions propagate — chat delivery is always unaffected.
        except httpx.TimeoutException:
            # Timeout is a subclass of RequestError; catch it first for a clearer log
            print(f"⏱️  [TrustScore] {sender}: AI Service timed out — skipping this cycle")
        except httpx.HTTPStatusError as e:
            # raise_for_status() fires for any non-2xx that isn't already handled (e.g. 500)
            print(f"⚠️  [TrustScore] {sender}: AI Service returned HTTP {e.response.status_code} — skipping this cycle")
        except httpx.RequestError as e:
            # Connection refused, DNS failure, etc. — AI microservice is simply down
            print(f"⚠️  [TrustScore] {sender}: AI Service unreachable — {type(e).__name__}: {e}")
        except Exception as e:
            # Catch-all: JSON decode errors, unexpected bugs, etc.
            # Trust Score is left unchanged for this cycle; WebSocket is unaffected.
            print(f"⚠️  [TrustScore] {sender}: Unexpected evaluation error ({type(e).__name__}) — {e}")


# ========================================
# DEV TOOLS & TEST MODE
# ========================================

from pydantic import BaseModel

class DevGenerateRequest(BaseModel):
    persona: str # 'owner' or 'hacker'
    topic: str = "เรื่องทั่วไป"

class DevAutoCalibrateRequest(BaseModel):
    user_id: str

@app.post("/api/dev/generate_message")
async def dev_generate_message(req: DevGenerateRequest, current_user: str = Depends(get_current_user_from_cookie)):
    """
    สร้างข้อความจำลองด้วย LLM เพื่อลดเวลาคิดประโยคพิมพ์
    persona="owner"  -> ข้อความสุภาพ พิมพ์ถูกหลัก
    persona="hacker" -> ข้อความวัยรุ่น คำแสลง พิมพ์ผิด
    """
    import os
    from logic import bot
    
    api_key = os.getenv("TYPHOON_API_KEY", "").strip()
    if not api_key:
        # Fallback offline
        if req.persona == "owner":
            return {"message": "สวัสดีครับ วันนี้อากาศดีจังเลย คิดเหมือนผมไหมครับ?"}
        return {"message": "เห้ยย ว่าไงพวก วันนี้ไม่ได้ไปไหนหวะ แย่สึด55555"}
        
    import random
    import uuid
    
    topics = [
        "การทำงาน", "สภาพอากาศ", "อาหารการกิน", "การเดินทาง",
        "เพื่อนร่วมงาน", "เทคโนโลยี", "บ่นเรื่องทั่วไป", "วันหยุดพักผ่อน",
        "เกมและซีรีส์", "ความเหนื่อยล้า"
    ]
    
    actual_topic = req.topic
    if req.topic == "เรื่องทั่วไป":
        actual_topic = random.choice(topics)
        
    random_seed = str(uuid.uuid4())[:8]
        
    prompt = f"แต่งประโยคสั้นๆ 1-2 ประโยค (ยาวประมาณ 20-30 คำ) เกี่ยวกับ '{actual_topic}' (Seed: {random_seed} ไม่ให้ซ้ำกับข้อความอื่นๆ) "
    if req.persona == "owner":
        prompt += "ให้สุภาพ เป็นทางการกลางๆ พิมพ์ถูกหลักไวยากรณ์ไทย"
    else:
        prompt += "ให้นามแฝงว่าเป็นแฮกเกอร์ วัยรุ่น พิมพ์ห้วนๆ มีคำแสลง พิมพ์ผิดจงใจ หรือมี 555 เยอะๆ"

    try:
        print(f"DEBUG: Using KEY={api_key[:5]}... PROMPT={prompt}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                'https://api.opentyphoon.ai/v1/chat/completions',
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model":       bot.TYPHOON_MODEL,
                    "messages":    [{"role": "user", "content": prompt}],
                    "max_tokens":  500,
                    "temperature": 0.7,
                    "top_p":       0.95,
                }
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return {"message": text}
    except httpx.HTTPStatusError as e:
        print(f"🔥 Dev Gen HTTP Error: {e.response.text}")
        return {"message": f"API Rejection: {e.response.text}"}
    except Exception as e:
        print(f"🔥 Dev Gen Error: {e}")
        return {"message": "เกิดข้อผิดพลาดในการสร้างข้อความ"}

@app.post("/api/dev/auto_calibrate")
async def dev_auto_calibrate(req: DevAutoCalibrateRequest, current_user: str = Depends(get_current_user_from_cookie)):
    """
    จำลองการเทรนตั้งต้น 30 ประโยค: เซฟประโยคสไตล์ Owner 30 ประโยคลงระบบอัตโนมัติ 
    ยิง Train และข้ามการเรียนรู้เบื้องต้นทั้งหมดให้ทันทีเพื่อใช้ Test Model
    User is identified from the HttpOnly Cookie — req.user_id is ignored.
    """
    sentences = [
        "สวัสดีครับ ยินดีที่ได้รู้จัก", "ตอนนี้ทำอะไรอยู่เหรอครับ", "ไปกินข้าวด้วยกันไหม?",
        "วันนี้อากาศดีจังเลยนะ", "ฉันคิดว่าแบบนั้นก็ดีนะ", "ไม่มีปัญหา จัดการให้ได้แน่นอน",
        "เดี๋ยวจะรีบส่งงานให้นะครับ", "ช่วยตรวจสอบไฟล์นี้ที", "ขอบคุณมากครับที่แนะนำเรื่องนั้น",
        "แล้วแต่เลย เอาที่สบายใจ", "ไม่เป็นไรครับ ยินดีครับ", "รับทราบ จะดำเนินการเดี๋ยวนี้เลย",
        "น่าสนใจมาก ขอดูรายละเอียดหน่อยครับ", "ทำไมถึงคิดแบบนั้นล่ะครับ", "ก็ว่าอยู่ว่าทำไมแปลกๆ",
        "ตลกมากเลยครับ ขอบคุณที่เล่า", "จริงดิ ไม่น่าเชื่อ", "อ๋อ เข้าใจแล้วครับ",
        "รบกวนหน่อยนะครับ", "ขอโทษทีที่ตอบช้าไปหน่อย", "เดี๋ยวทักไปใหม่นะครับ ช่วงนี้ยุ่งนิดนึง",
        "พรุ่งนี้ว่างหรือเปล่าครับ", "ไม่แน่ใจแฮะ ขอเช็คดูก่อนนะ", "เยี่ยมไปเลย เป็นข่าวดีจริงๆ",
        "โอเค ตกลงตามนี้ครับ", "ได้เลย ไม่มีปัญหาครับผม", "งั้นเดี๋ยวเจอกันพรุ่งนี้นะครับ",
        "ผมเห็นด้วยกับแนวคิดนั้นครับ", "เรื่องนี้ต้องใช้เวลาศึกษาเพิ่มเติม", "จะพยายามทำให้ดีที่สุดนะครับ"
    ]
    
    # Save under the authenticated user (current_user from cookie) so messages
    # render on the right side and get_calibration_progress counts them correctly.
    for s in sentences:
        database.save_message(sender=current_user, receiver="test_mode", content=s)
        
    # Trigger Personal Model Training API Call (similar to logic in websocket)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            train_payload = {
                "user_id": current_user,
                "messages": sentences
            }
            res = await client.post("http://localhost:8001/api/train_personal", json=train_payload)
            res.raise_for_status()
            
            # ดึงประวัติข้อความมาส่งกลับไปให้หน้า Frontend จะได้รับรู้และ refresh แสดงผล 30 แชทล่าสุดเลย
            history = database.get_messages(current_user, "test_mode")
            return {
                "msg": f"Auto-Calibrated and trained 30 baseline sentences for {current_user}.",
                "messages": history[-30:]
            }
    except httpx.HTTPStatusError as e:
        print(f"🔥 Auto-Calibrate HTTPError: {e.response.text}")
        raise HTTPException(status_code=500, detail=f"AI Service Error: {e.response.text}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=repr(e))

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

    # 📌 Security Upgrade: ส่ง Token กลับไปทาง Set-Cookie 
    # ทริกเกอร์ UNFREEZE และ Feedback Loop การสอน AI ถ้านี่มาจากการยืนยัน Account
    await _trigger_retrain_and_unfreeze(user["username"])

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
        # เพิ่ม system_bot เป็น Contact อัตโนมัติ เพื่อให้บอทปรากฏบน Sidebar เสมอ
        database.add_contact(username, 'system_bot')
        # บันทึกข้อความทักทายแรกจากบอทลง DB ทันที เพื่อให้หน้าบ้านเจอข้อความนี้
        # ทันทีที่โหลดแชทครั้งแรก (ก่อน WebSocket ส่งอะไรเลย)
        database.save_message(
            sender='system_bot',
            receiver=username,
            content=bot.FALLBACK_GREETING,
        )

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
    # ทริกเกอร์ UNFREEZE และ Feedback Loop สั่งสอนปรับเปลี่ยน AI Style
    await _trigger_retrain_and_unfreeze(username)

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

@app.get("/api/user/profile")
async def get_user_profile(current_user: str = Depends(get_current_user_from_cookie)):
    """
    ดึงข้อมูลโปรไฟล์และสถานะความปลอดภัยของผู้ใช้ที่ล็อกอินอยู่

    Fields ที่ส่งกลับ:
      username      — ชื่อบัญชี (immutable identifier)
      display_name  — ชื่อที่แสดงผล (fallback = username)
      member_since  — วันที่สร้างตัวตนดิจิทัลนี้ (created_at)
      is_mfa_enabled — สถานะ TOTP จริงจากฐานข้อมูล
      contact_count — จำนวนผู้ติดต่อใน Social Graph

    ใช้สำหรับ:
      - แสดงข้อมูลผู้ใช้บนหน้า Profile / Settings
      - ตรวจสอบสถานะ MFA เพื่อแสดง badge แจ้งเตือนให้เปิดใช้งาน
      - หน้า Privacy Dashboard แสดง Security Summary
    """
    user = database.get_user(current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # list_contacts คืนค่าเป็น List — นับความยาวเพื่อได้ contact_count
    contacts = database.list_contacts(current_user)

    return {
        "username":             user["username"],
        "display_name":         user.get("display_name") or user["username"],
        "member_since":         user.get("created_at", "unknown"),
        "is_mfa_enabled":       user.get("is_mfa_enabled", False),
        "contact_count":        len(contacts),
        "calibration_progress": database.get_calibration_progress(current_user),
    }

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
        # 📌 Pre-fill Sliding Window เมื่อเชื่อมต่อเข้ามาใหม่ (ดึงประวัติ 4 ประโยคล่าสุดฝั่งตัวเอง)
        # เพื่อให้พอพิมพ์ประโยคเดียวปุ๊บ (รวมของเก่า 4 = 5) ระบบประเมินผลได้ทันทีโดยไม่ต้องรอให้พิมพ์ครบ 5 ครั้ง
        user_dq = manager.user_message_windows[username]
        if len(user_dq) == 0:
            recent_msgs = [m.get("content", "") for m in database.messages_db if m.get("sender") == username][-4:]
            # Strip any empty strings that came from encrypted-only records
            user_dq.extend([t for t in recent_msgs if t])
            print(f"🪣 Pre-fill check for {username}: {len(user_dq)} messages in DQ")

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            receiver = payload.get("receiver")
            content = payload.get("content")
            
            if not receiver or not content:
                continue

            print(f"📡 WebSocket Received message for: {receiver}")

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

            # 📌 2b. ถ้า receiver เป็น system_bot ให้เรียก LLM และส่งคำตอบกลับหา sender
            if str(receiver).lower() == "system_bot":
                # ดึงประวัติแชทระหว่าง sender กับ system_bot ก่อนข้อความนี้
                chat_history = database.get_messages(sender, "system_bot")

                async def _reply_as_bot(sndr: str = sender, user_msg: str = content,
                                        history: list = chat_history):
                    bot_reply = await bot.generate_typhoon_response(user_msg, history)
                    ts = datetime.utcnow().isoformat()
                    database.save_message(sender="system_bot", receiver=sndr, content=bot_reply)
                    bot_payload = json.dumps({
                        "sender": "system_bot",
                        "content": bot_reply,
                        "timestamp": ts,
                    })
                    await manager.send_personal_message(bot_payload, sndr)

                asyncio.create_task(_reply_as_bot())

                # 📌 2c. Trigger Initial Training: ถ้าทักหาบอทครบ 5 ประโยคพอดี ให้สร้างโมเดล!
                # เปลี่ยนมาส่งเมื่อครบ 5 พอดี เพื่อไม่ให้สร้างซ้ำซ้อน
                actual_cal_count = sum(1 for m in database.get_messages(sender, "system_bot") if m["sender"] == sender)
                
                if actual_cal_count == 30:
                    sender_msgs_to_bot = [
                        m["content"] for m in database.get_messages(sender, "system_bot")
                        if m["sender"] == sender
                    ][:30] # ดึง 30 ข้อความแรก
                    
                    print(f"🚀 Initializing Personal AI Model for {sender} (Reached {len(sender_msgs_to_bot)} baseline msgs)...")
                    async def _trigger_train():
                        try:
                            async with httpx.AsyncClient(timeout=60.0) as client:
                                # ยิงไปฝึกโมเดลครั้งแรก
                                train_payload = {
                                    "user_id": sender,
                                    "messages": sender_msgs_to_bot
                                }
                                res = await client.post("http://localhost:8001/api/train_personal", json=train_payload)
                                if res.status_code == 200:
                                    print(f"✅ Baseline model successfully curated for {sender}!")
                                else:
                                    print(f"⚠️ Failed to train baseline: {res.text}")
                        except Exception as e:
                            print(f"❌ Initial Model Setup Failed: {e}")
                    
                    asyncio.create_task(_trigger_train())
            
            # 📌 3. AI Logic Integration: กฎเหล็ก (STRICT RULE) ของการแยกคนส่ง-คนรับ
            # ระบบจะนำข้อความใส่เข้า deque ของ "sender" (คนที่พิมพ์ข้อความ) เท่านั้น
            # ห้ามเอา receiver (ผู้รับ) หรือข้อมูลอื่นมาเป็น Key เด็ดขาด เพื่อป้องกัน AI เอาประโยคคนอื่นมาสลับคน
            user_dq = manager.user_message_windows[sender]
            user_dq.append(content)
            
            count = len(user_dq)

            if count >= 5:
                # 📌 Block Premature Prediction: เช็คว่าสร้าง Baseline เสร็จหรือยัง
                actual_cal_count = sum(1 for m in database.get_messages(sender, "system_bot") if m["sender"] == sender)
                print(f"📊 Evaluator check: count={count}, cal_count={actual_cal_count}")
                
                if actual_cal_count < 30:
                    # ข้ามการตรวจสอบเลย ไม่ต้องยิงขอ AI เพราะเดี๋ยว Model not calibrated
                    score = None
                elif actual_cal_count == 30 and str(receiver).lower() == "system_bot":
                    # เราได้ trigger train ไว้ด้านบนแล้ว นี่คือจังหวะที่เพิ่งครบ 5
                    # ให้ล้างตะกร้าข้อความ แล้วข้าม predict
                    manager.user_message_windows[sender].clear()
                    continue
                else:
                    # 📌 Non-blocking AI Evaluation: ยิง /api/predict ใน Background Task
                    # ข้อความถูกส่งหา receiver ไปแล้วข้างบน — Trust Score จะมาทีหลัง ไม่บล็อก WebSocket loop
                    # Per-user Lock จัดการ Race Condition ให้อัตโนมัติใน _evaluate_trust_score
                    sliding_window = list(user_dq)[-5:]
                    asyncio.create_task(_evaluate_trust_score(sender, sliding_window, ws_ip, ws_ua))

                    # 📌 Periodic Retraining (ทุกๆ 100 ข้อความที่พิมพ์หาใครก็ได้)
                    total_sent_msgs = sum(1 for m in database.messages_db if m.get("sender") == sender)
                    if total_sent_msgs > 0 and total_sent_msgs % 100 == 0:
                        print(f"🔄 Periodic Retraining triggered for {sender} (Total texts: {total_sent_msgs})")
                        async def _periodic_retrain():
                            try:
                                async with httpx.AsyncClient(timeout=60.0) as client:
                                    history_records = database.get_messages(sender, "system_bot")
                                    # ดึงประวัติที่มั่นใจว่าเป็นของแท้ (Calibration 30 ประโยคแรก)
                                    user_historical = [m["content"] for m in history_records if m["sender"] == sender][:30]
                                    
                                    # เอา 10 ข้อความล่าสุดไปอัปเดตโมเดล
                                    recent_msgs = [m.get("content", "") for m in database.messages_db if m.get("sender") == sender][-10:]
                                    recent_msgs = [t for t in recent_msgs if t]  # drop empty encrypted-only entries
                                    
                                    payload = {
                                        "user_id": sender,
                                        "historical_messages": user_historical,
                                        "new_messages": recent_msgs
                                    }
                                    res = await client.post("http://localhost:8001/api/retrain_personal", json=payload)
                                    res.raise_for_status()
                                    print(f"✅ Periodic Auto-Retrain Success for {sender}.")
                            except Exception as e:
                                print(f"❌ Periodic Auto-Retrain Failed for {sender}: {e}")
                        
                        asyncio.create_task(_periodic_retrain())
            
            # 📌 4. บังคับส่งสถานะกลับ (Strict Routing): ส่ง SECURITY_UPDATE กลับไปหา ท่อของคนส่ง (sender) เท่านั้น
            # เช็คให้ชัวร์ว่าจะไม่มีทางถูกส่งไปหา receiver อย่างเด็ดขาด
            # หมายเหตุ: score จะถูกส่งแยกจาก _evaluate_trust_score background task (Non-blocking)
            update_payload = {
                "type": "SECURITY_UPDATE",
                "count": count,
                "score": None,
            }
            await manager.send_personal_message(json.dumps(update_payload), sender)
                    
    except WebSocketDisconnect:
        manager.disconnect(username)
