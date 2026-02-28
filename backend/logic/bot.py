"""
logic/bot.py — Stylometry Guardian (Onboarding Bot)
====================================================
เชื่อมต่อกับ Typhoon LLM API (OpenAI-compatible) เพื่อสร้างบอท
ที่ชวนผู้ใช้ใหม่คุย 5 ประโยค เพื่อเก็บ Stylometry Baseline

โมเดล: typhoon-v2.5-30b-a3b-instruct (SCB 10X / AI Thailand)
API:   https://api.opentyphoon.ai/v1  (OpenAI-compatible format)

การตั้งค่า:
    สร้างไฟล์ backend/.env แล้วระบุ:
        TYPHOON_API_KEY=<your_key>
    ระบบจะโหลดค่าอัตโนมัติผ่าน python-dotenv
    หากไม่มี Key ระบบจะตอบด้วย Fallback message แบบออฟไลน์

Privacy Note:
    บอทนี้รับ chat_history ในรูป list[dict] — ไม่มีการเก็บ
    สถานะหรือ Context ใด ๆ ฝั่ง bot.py เอง ทุกอย่างถูก
    บริหารจัดการโดย database.get_messages() ฝั่ง main.py
"""

import os
from pathlib import Path
import httpx
from dotenv import load_dotenv
from typing import Any

# โหลด .env จาก backend/ โดยอัตโนมัติ
# load_dotenv() จะค้นหาไฟล์ .env ใน directory เดียวกับ bot.py ก่อน
# แล้ว walk up ไปยัง parent directories — ใช้ explicit path เพื่อความชัดเจน
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)  # override=False: env var ที่ตั้งไว้แล้วมีความสำคัญกว่า

# ─── Debug: แสดงสถานะ API Key ตอน import ───
# ซ่อนตัวอักษรหลังตัวที่ 5 เพื่อความปลอดภัย แต่ยืนยันได้ว่าโหลดมาจริง
_loaded_key = os.getenv("TYPHOON_API_KEY", "")
if _loaded_key:
    print(f"🔑 Loaded API Key: {_loaded_key[:5]}... (length: {len(_loaded_key)})")
else:
    print("⚠️  TYPHOON_API_KEY not found — bot will use offline fallback")

# ─────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────

TYPHOON_API_URL   = "https://api.opentyphoon.ai/v1/chat/completions"
TYPHOON_MODEL     = "typhoon-v2.5-30b-a3b-instruct"

# ─────────────────────────────────────────────────────────────────────
# ⏱️  Timeout Configuration — สำคัญมากสำหรับ LLM ขนาดใหญ่
# ─────────────────────────────────────────────────────────────────────
# โมเดล LLM ขนาดใหญ่ (เช่น 30B parameters) ต้องการเวลา Inference
# นานกว่า REST API ทั่วไปมาก เพราะต้อง Generate คำตอบทีละ Token
# ตั้งค่า timeout ต่ำเกินไป (เช่น 10–15 วินาที) จะทำให้ได้รับ
# TimeoutException ก่อนที่โมเดลจะ Generate คำตอบเสร็จ
# โดยเฉพาะในช่วง Server Load สูง หรือคำตอบที่ยาว
# แนะนำ ≥60 วินาทีสำหรับโมเดล >7B parameters
REQUEST_TIMEOUT       = 60.0   # วินาที — เพิ่มจาก 30s เพื่อรองรับ Inference ของโมเดล 30B
MAX_HISTORY_MESSAGES  = 6      # จำกัดประวัติแชท = ~3 รอบสนทนา (user+bot) ล่าสุด

# ─────────────────────────────────────────────────────────────────────
# 🧮  Token Budget — ทำความเข้าใจขีดจำกัด Context Window
# ─────────────────────────────────────────────────────────────────────
# Typhoon (และ LLM ทั่วไป) คิด Token แบบ:
#   total_tokens = prompt_tokens + completion_tokens
#   prompt_tokens  = System Prompt + Chat History (ทุก message)
#   completion_tokens = ข้อความที่โมเดล Generate ออกมา (≤ max_tokens)
#
# ตัวอย่างการประเมิน (1 Token ≈ 0.75 คำภาษาอังกฤษ / ~1.5 ตัวอักษรภาษาไทย):
#   System Prompt    ≈  250 tokens
#   6 messages hist  ≈  600 tokens  (เฉลี่ย 100 tok/msg)
#   user_message     ≈   50 tokens
#   ─────────────────────────────────────────────────
#   prompt_tokens    ≈  900 tokens
#   max_tokens       = 2048 (completion budget)
#   ─────────────────────────────────────────────────
#   total            ≈ 2948 tokens  << Context Window (~32K) ✅
#
# ถ้า prompt_tokens + max_tokens > Context Window → 400 Bad Request!
# วิธีแก้: ลด MAX_HISTORY_MESSAGES หรือลด max_tokens
MAX_TOKENS_COMPLETION = 2048   # Token Budget สำหรับ output — เพิ่มจาก 512

# ⚠️  ไม่ใช้ constant สำหรับ API Key เพื่อให้อ่านค่าใหม่ทุกครั้งที่เรียกฟังก์ชัน
# (ป้องกันกรณี .env โหลดหลัง module import)

# ─────────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────────

SYSTEM_PROMPT = (
    'คุณคือ "Stylometry Guardian" บอทผู้ช่วยในระบบแชทความปลอดภัยสูง '
    'หน้าที่ของคุณคือชวนผู้ใช้ใหม่คุยจำนวน 5 ประโยค เพื่อให้ระบบ AI '
    'ด้านหลังเก็บสไตล์การพิมพ์ (Thai-Stylometry) ของผู้ใช้เป็นข้อมูลตั้งต้น '
    'กฎการคุย: '
    '1. แนะนำตัวสั้นๆ และบอกผู้ใช้อย่างโปร่งใสว่ากำลังทำ Calibration เพื่อความปลอดภัย '
    '2. ถามคำถามปลายเปิด 1 คำถามต่อ 1 เทิร์น (เช่น ความเห็นเรื่อง AI, ประสบการณ์โดนแฮก) '
    '3. เมื่อคุยครบ 5 ประโยค ให้กล่าวขอบคุณและบอกว่าบัญชีพร้อมใช้งาน '
    '4. ใช้ภาษาไทยที่เป็นมิตร สุภาพ Tech-savvy'
)

# ─────────────────────────────────────────────────
#  Fallback responses (ใช้เมื่อไม่มี API Key หรือ API ล่ม)
# ─────────────────────────────────────────────────

FALLBACK_GREETING = (
    "สวัสดีครับ! ผมคือ Stylometry Guardian 🛡️\n"
    "ระบบกำลังทำการ Calibration เพื่อจำ \"ลายนิ้วมือดิจิทัล\" ของการพิมพ์คุณ\n"
    "เพียงคุยกับผม 5 ประโยค บัญชีของคุณจะได้รับการป้องกันสูงสุด\n\n"
    "เริ่มเลยนะครับ — คุณคิดว่า AI จะช่วยพัฒนาชีวิตประจำวันได้อย่างไรบ้าง?"
)

# Alias สำหรับ import จาก main.py ด้วย bot.SYSTEM_PROMPT_GREETING
SYSTEM_PROMPT_GREETING = FALLBACK_GREETING

FALLBACK_RESPONSE = (
    "ขอบคุณที่แชร์ครับ! ระบบได้บันทึก Stylometry ของคุณเรียบร้อยแล้ว 🎯\n"
    "ช่วยเล่าให้ฟังอีกสักเรื่องได้ไหมครับ? เช่น ประสบการณ์ใช้งานระบบความปลอดภัยออนไลน์ของคุณ"
)


# ─────────────────────────────────────────────────
#  Core Function
# ─────────────────────────────────────────────────

async def generate_typhoon_response(
    user_message: str,
    chat_history: list[dict[str, Any]],
) -> str:
    """
    ส่ง user_message + chat_history ไปให้ Typhoon LLM แล้วคืนคำตอบของบอท

    Args:
        user_message : ข้อความล่าสุดจาก User (สตริง)
        chat_history : รายการข้อความก่อนหน้าในรูปแบบ OpenAI Messages
                       เช่น [{"role": "user", "content": "..."}, ...]
                       ควรสร้างมาจาก database.get_messages() แล้ว map role

    Returns:
        str — ข้อความตอบกลับจาก Typhoon (หรือ Fallback หากไม่มี API Key / API ล่ม)

    หมายเหตุ Async:
        ฟังก์ชันนี้ใช้ httpx.AsyncClient เพื่อให้ I/O ไม่บล็อก Event Loop
        ควรเรียกผ่าน asyncio.create_task() ใน WebSocket handler เสมอ
        เพื่อให้ WebSocket สามารถรับข้อความอื่น ๆ ระหว่างรอ API ได้
    """
    # ─── อ่าน API Key ใหม่ทุกครั้งที่เรียก (ป้องกัน key ว่างเปล่าตอน import) ───
    api_key = os.getenv("TYPHOON_API_KEY", "").strip()

    # ─── Fallback: ถ้าไม่มี API Key ให้ตอบแบบ offline ───
    if not api_key:
        print("⚠️  generate_typhoon_response: TYPHOON_API_KEY is empty — using fallback")
        is_first_message = len(chat_history) == 0
        return FALLBACK_GREETING if is_first_message else FALLBACK_RESPONSE

    # ─── สร้าง Messages array ตามรูปแบบ OpenAI Chat Completions ───
    # Format: [system] + [ประวัติแชท] + [ข้อความล่าสุด]
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # แปลง chat_history (จาก DB) → OpenAI format
    # DB เก็บ {"sender": "alice", "receiver": "system_bot", "content": "..."}
    # Typhoon ต้องการ {"role": "user"/"assistant", "content": "..."}
    for msg in chat_history:
        if msg.get("sender") == "system_bot":
            messages.append({"role": "assistant", "content": msg["content"]})
        else:
            messages.append({"role": "user", "content": msg["content"]})

    # เพิ่มข้อความล่าสุดของ User
    messages.append({"role": "user", "content": user_message})

    # ─── ตัดประวัติแชทที่ยาวเกินไป ─────────────────────────────────────
    # API มี Token Limit — ถ้าส่ง messages มากเกินไปจะได้รับ 400 Bad Request
    # เก็บเฉพาะ: [system] + [MAX_HISTORY_MESSAGES ข้อความล่าสุดรวมข้อความปัจจุบัน]
    # MAX_HISTORY_MESSAGES=6 หมายถึง ~3 รอบสนทนา (user+bot) — เพียงพอสำหรับ
    # Context ของบอท Onboarding 5 ประโยค โดยไม่ทำให้ prompt_tokens บวมเกินไป
    if len(messages) > MAX_HISTORY_MESSAGES + 1:  # +1 คือ system message
        messages = [messages[0]] + messages[-(MAX_HISTORY_MESSAGES):]
        print(f"⚠️  Chat history truncated to {MAX_HISTORY_MESSAGES} messages to avoid Token Limit")

    # ─── ยิง API ด้วย httpx.AsyncClient ───
    # ใช้ Async เพื่อไม่บล็อก Event Loop ของ FastAPI
    # timeout ตั้งไว้ที่ REQUEST_TIMEOUT วินาที — โมเดล LLM ขนาดใหญ่
    # ต้องการเวลา Generate คำตอบนานกว่า REST API ทั่วไปมาก
    try:
        print(f"📡 Sending request to Typhoon API (Model: {TYPHOON_MODEL}, messages: {len(messages)}, max_tokens: {MAX_TOKENS_COMPLETION})...")
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                TYPHOON_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       TYPHOON_MODEL,
                    "messages":    messages,
                    "max_tokens":  MAX_TOKENS_COMPLETION,
                    "temperature": 0.7,
                    "top_p":       0.95,
                },
            )
            # ─── Debug: แสดง raw response เสมอ เพื่อตรวจสอบปัญหา ───
            print(f"📡 Typhoon response: status={resp.status_code} body={resp.text[:300]}")
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"].strip()

    except httpx.TimeoutException as e:
        print(f"🔥 Typhoon API Error (Timeout): {str(e)}")
        return (
            "ขออภัยครับ ระบบ AI ตอบสนองช้าในขณะนี้ 🔄\n"
            "กรุณาส่งข้อความมาอีกครั้งได้เลยครับ"
        )
    except httpx.HTTPStatusError as e:
        print(f"🔥 Typhoon API Error (HTTP {e.response.status_code})")
        print(f"❌ Full Response Error: {e.response.text}")
        return (
            f"ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อ AI (HTTP {e.response.status_code})\n"
            "กรุณาลองใหม่ในภายหลังครับ"
        )
    except Exception as e:
        print(f"🔥 Typhoon API Error (Unexpected): {type(e).__name__}: {str(e)}")
        return FALLBACK_RESPONSE
