import json
import uuid
from datetime import datetime
from cryptography.fernet import Fernet
import os

# For demonstration, use a static key if not set
SECRET_KEY = os.getenv("FERNET_KEY", Fernet.generate_key().decode())
fernet = Fernet(SECRET_KEY.encode())

# In-memory mock database
users_db = {}
messages_db = []
contacts_db = {}

# ==========================================
# AUDIT LOGGING — ระบบบันทึกเหตุการณ์
# ==========================================

# AuditAction: ค่าคงที่แบบ Enum-like สำหรับประเภทเหตุการณ์
# การใช้ค่าคงที่แทนสตริงอิสระช่วยให้:
#   1. วิเคราะห์พฤติกรรมผู้ใช้ได้ง่าย (Group By, Filter)
#   2. ลดความผิดพลาดจากการพิมพ์ผิด (Typo)
#   3. เป็นมาตรฐาน Digital ID ที่สามารถนำไปสร้าง Risk Score ได้
class AuditAction:
    # ----- Identity Lifecycle (วงจรชีวิตตัวตนดิจิทัล) -----
    REGISTER          = "REGISTER"            # สร้างตัวตนใหม่ในระบบ
    LOGIN_SUCCESS     = "LOGIN_SUCCESS"       # ยืนยันตัวตนสำเร็จ
    LOGIN_FAILED      = "LOGIN_FAILED"        # ยืนยันตัวตนล้มเหลว (จับ Brute-force)
    LOGOUT            = "LOGOUT"              # สิ้นสุด Session

    # ----- Communication (การสื่อสาร) -----
    SEND_MESSAGE      = "SEND_MESSAGE"        # ส่งข้อความ (เก็บ Metadata เท่านั้น ไม่เก็บเนื้อหา)

    # ----- Social Graph (ความสัมพันธ์ระหว่างตัวตน) -----
    ADD_CONTACT       = "ADD_CONTACT"         # สร้างความสัมพันธ์ใหม่ระหว่าง 2 ตัวตน

    # ----- Security Events (เหตุการณ์ด้านความปลอดภัย) -----
    STYLOMETRY_ALERT  = "STYLOMETRY_ALERT"    # ระบบตรวจพบรูปแบบการเขียนผิดปกติ
    MFA_SETUP         = "MFA_SETUP"           # ผู้ใช้เปิดใช้งาน TOTP สำเร็จครั้งแรก
    MFA_VERIFY        = "MFA_VERIFY"          # ผ่านการตรวจสอบ TOTP ระหว่าง Login
    MFA_FAILED        = "MFA_FAILED"          # ป้อนรหัส TOTP ผิด (จับ Replay attack)
    ADAPTIVE_MFA      = "ADAPTIVE_MFA"        # ระบบบังคับ MFA เพราะตรวจพบ Device ใหม่


# audit_logs_db: ฐานข้อมูล In-memory สำหรับเก็บ Audit Log
# โครงสร้าง: List ของ Dict แต่ละรายการ
# หมายเหตุ: ในระบบ Production ควรย้ายไปใช้ SQLite / PostgreSQL
# เพื่อให้คงอยู่แม้ Server Restart
audit_logs_db: list[dict] = []


def create_audit_log_table() -> None:
    """
    สร้างโครงสร้างตาราง Audit Log (In-memory version)

    เหตุผลที่ต้องเก็บแต่ละ Field เพื่อ Digital Identification:
    ┌─────────────────┬───────────────────────────────────────────────────────────┐
    │ Field           │ ประโยชน์ด้าน Digital ID                                   │
    ├─────────────────┼───────────────────────────────────────────────────────────┤
    │ id              │ อ้างอิง Log เฉพาะรายเพื่อตรวจสอบย้อนหลัง                  │
    │ user_id         │ ผูก Event เข้ากับตัวตน (Nullable สำหรับ Login ล้มเหลว)   │
    │ action          │ ประเภทเหตุการณ์ — ใช้วิเคราะห์ Pattern ของผู้ใช้          │
    │ ip_address      │ ระบุตำแหน่งทางเครือข่าย ตรวจจับ IP ผิดปกติ / VPN         │
    │ user_agent      │ ระบุ Device/Browser — ตรวจ Device ที่ไม่คุ้นเคย           │
    │ extra_data      │ ข้อมูลเสริม เช่น receiver, stylometry_score                │
    │ timestamp       │ ลำดับเวลา — วิเคราะห์ Frequency, Brute-force Pattern      │
    └─────────────────┴───────────────────────────────────────────────────────────┘
    """
    # ล้างตารางและเริ่มใหม่ (ใช้ตอน startup เพื่อ reset state)
    global audit_logs_db
    audit_logs_db = []


def save_audit_log(
    action: str,
    ip_address: str,
    user_agent: str,
    user_id: str | None = None,
    extra_data: dict | None = None,
) -> dict:
    """
    บันทึกเหตุการณ์ลง Audit Log

    Args:
        action      : ประเภทเหตุการณ์ ควรใช้ค่าจาก AuditAction เท่านั้น
        ip_address  : IP ของผู้ใช้ ดึงจาก request.client.host
        user_agent  : Browser/OS info ดึงจาก Header "user-agent"
        user_id     : Username หรือ None (กรณี Login ล้มเหลว ยังไม่รู้ว่าใคร)
        extra_data  : ข้อมูลเสริมตามบริบท เช่น {"receiver": "bob", "score": 0.87}

    Returns:
        dict ของ Log Entry ที่เพิ่งบันทึก

    หมายเหตุด้าน Privacy:
        - ไม่เก็บเนื้อหาข้อความ (Content) เพื่อความเป็นส่วนตัว
        - เก็บเพียง Metadata เพื่อตรวจสอบได้ว่า "ใคร ทำอะไร เมื่อไหร่ จากที่ไหน"
        - ตามหลัก Data Minimization ของ PDPA / GDPR
    """
    log_entry = {
        "id":           str(uuid.uuid4()),
        "user_id":      user_id,                            # Nullable
        "action":       action,                             # ค่าจาก AuditAction
        "ip_address":   ip_address or "unknown",
        "user_agent":   user_agent or "unknown",
        "extra_data":   extra_data or {},                   # JSON เสริม
        "timestamp":    datetime.utcnow().isoformat() + "Z" # ISO 8601 UTC
    }
    audit_logs_db.append(log_entry)
    return log_entry


def get_audit_logs(user_id: str | None = None, action: str | None = None) -> list[dict]:
    """
    ดึง Audit Log พร้อม Filter ตาม user_id และ/หรือ action
    ใช้สำหรับ Admin Dashboard หรือการวิเคราะห์พฤติกรรมผู้ใช้
    """
    result = audit_logs_db
    if user_id:
        result = [l for l in result if l["user_id"] == user_id]
    if action:
        result = [l for l in result if l["action"] == action]
    return result

# ==========================================
# MFA — Multi-Factor Authentication (TOTP)
# ==========================================
#
# หลักการ Shared Secret ใน TOTP (Time-based One-Time Password)
# ──────────────────────────────────────────────────────────────
# TOTP ทำงานบนหลักการ "Shared Secret" กล่าวคือ:
#   1. ตอน Setup: Server สุ่มสร้าง Secret Key (Base32 string) แล้วส่งให้ผู้ใช้
#      ผ่าน QR Code — ผู้ใช้นำไปสแกนใน Authenticator App (Google/Authy)
#   2. ทั้ง Server และ App ต่างมี Secret Key ชุดเดียวกัน + เวลาปัจจุบัน (UTC)
#   3. เมื่อต้องการยืนยัน: App คำนวณ HMAC-SHA1(secret, floor(time/30))  → รหัส 6 หลัก
#      Server คำนวณค่าเดิมอิสระ แล้วเปรียบเทียบ
#   4. รหัสมีอายุ 30 วินาที — แม้ดักจับได้ก็ใช้ซ้ำไม่ได้ (Replay-resistant)
#   5. Secret ถูกเก็บบน Server (Encrypted ใน Production) และใน App ของผู้ใช้
#      ไม่มีการส่ง Secret ผ่านเครือข่ายอีกหลังจาก Setup ครั้งแรก
#
# ประโยชน์ต่อ Digital ID:
#   - พิสูจน์ความเป็นเจ้าของ Device จริง ๆ (Something You Have)
#   - รหัสผ่านอย่างเดียวไม่พอ — ป้องกัน Credential Stuffing
#   - ตรวจจับการยึดบัญชี (Account Takeover) ด้วย Adaptive Auth

def create_user(username, hashed_password):
    if username in users_db:
        return False
    users_db[username] = {
        "username":       username,
        "password":       hashed_password,
        # mfa_secret: Shared Secret สำหรับคำนวณ TOTP
        # เก็บเป็น Base32 string — ควร Encrypt ด้วย Fernet ใน Production
        "mfa_secret":     None,
        # is_mfa_enabled: True เมื่อผู้ใช้ยืนยัน TOTP ครั้งแรกสำเร็จแล้วเท่านั้น
        # ป้องกัน Secret ที่ยังไม่ได้ยืนยันถูกใช้งานโดยไม่ตั้งใจ
        "is_mfa_enabled": False,
    }
    contacts_db[username] = []
    return True

def get_user(username):
    return users_db.get(username)


def set_mfa_secret(username: str, secret: str) -> bool:
    """
    บันทึก TOTP Shared Secret ลงในข้อมูลผู้ใช้ (ยังไม่เปิดใช้งาน)
    ต้องรอ verify_and_enable_mfa() สำเร็จก่อน จึงจะถือว่า MFA พร้อมใช้
    """
    user = users_db.get(username)
    if not user:
        return False
    user["mfa_secret"] = secret
    return True


def verify_and_enable_mfa(username: str) -> bool:
    """
    เปลี่ยน is_mfa_enabled = True หลังผู้ใช้ยืนยัน TOTP ครั้งแรกสำเร็จ
    การแยก set_secret / enable เป็น 2 ขั้นเพื่อป้องกัน Secret ที่ไม่ผ่านการยืนยัน
    ถูกนำไปใช้ล็อก Account ผู้ใช้โดยปราศจากความตั้งใจ
    """
    user = users_db.get(username)
    if not user or not user.get("mfa_secret"):
        return False
    user["is_mfa_enabled"] = True
    return True


def get_known_devices(username: str) -> tuple[set[str], set[str]]:
    """
    ดึง IP Address และ User-Agent ที่เคย Login สำเร็จมาก่อน
    ใช้สำหรับ Adaptive Authentication — ตรวจสอบว่า Device ปัจจุบัน
    เคยปรากฏในประวัติ LOGIN_SUCCESS ของผู้ใช้คนนี้หรือไม่

    Returns:
        (known_ips, known_user_agents) — set ของค่าที่เคยพบ
    """
    success_logs = [
        log for log in audit_logs_db
        if log["user_id"] == username and log["action"] == AuditAction.LOGIN_SUCCESS
    ]
    known_ips = {log["ip_address"] for log in success_logs}
    known_uas = {log["user_agent"]  for log in success_logs}
    return known_ips, known_uas

def get_all_users():
    return list(users_db.keys())

def add_contact(username, contact_username):
    # เพิ่มให้ฝั่ง User A (คนแอด)
    if username not in contacts_db:
        contacts_db[username] = []
    if contact_username not in contacts_db[username]:
        contacts_db[username].append(contact_username)
        
    # เพิ่มให้ฝั่ง User B (คู่สนทนา) - Two-way Mutual Add
    if contact_username not in contacts_db:
        contacts_db[contact_username] = []
    if username not in contacts_db[contact_username]:
        contacts_db[contact_username].append(username)
        
    return True

def list_contacts(username):
    return contacts_db.get(username, [])

def save_message(sender, receiver, content):
    """
    Encrypt and save a message.
    The message content is encrypted using Fernet before storing.
    """
    # เข้ารหัสข้อความเพื่อความปลอดภัย (Encryption Flow)
    encrypted_content = fernet.encrypt(content.encode()).decode()
    msg = {
        "sender": sender,
        "receiver": receiver,
        "content_encrypted": encrypted_content
    }
    messages_db.append(msg)
    return msg

def get_messages(user1, user2):
    """
    Retrieve and decrypt messages between two users.
    Order is chronological.
    """
    history = []
    for msg in messages_db:
        if (msg["sender"] == user1 and msg["receiver"] == user2) or \
           (msg["sender"] == user2 and msg["receiver"] == user1):
            
            # ถอดรหัสข้อความก่อนส่งให้ Frontend
            decrypted_content = fernet.decrypt(msg["content_encrypted"].encode()).decode()
            
            history.append({
                "sender": msg["sender"],
                "receiver": msg["receiver"],
                "content": decrypted_content
            })
    return history
