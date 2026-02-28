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

def create_user(username, hashed_password):
    if username in users_db:
        return False
    users_db[username] = {"username": username, "password": hashed_password}
    contacts_db[username] = []
    return True

def get_user(username):
    return users_db.get(username)

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
