import json
from cryptography.fernet import Fernet
import os

# For demonstration, use a static key if not set
SECRET_KEY = os.getenv("FERNET_KEY", Fernet.generate_key().decode())
fernet = Fernet(SECRET_KEY.encode())

# In-memory mock database
users_db = {}
messages_db = []
contacts_db = {}

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
