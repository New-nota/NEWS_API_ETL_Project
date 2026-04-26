from __future__ import annotations
import base64
import hashlib
from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config.config import settings
from .db import get_cursor

@dataclass(frozen=True, slots=True)
class EncryptedNewsApiKey:
    encrypted_key: str
    iv: str 
    auth_tag: str 

def _get_encryption_key() -> bytes:
    secret = settings.news_api_key_encryption_secret.strip()
    if not secret:
        raise RuntimeError("NEWS_API_KEY_ENCRYPTION_SECRET is not in config")
    return hashlib.sha256(secret.encode("utf-8")).digest()

def decrypt_news_api_key(row: EncryptedNewsApiKey) -> str:
    aesgcm = AESGCM(_get_encryption_key())
    ciphertext = base64.b64decode(row.encrypted_key)
    iv = base64.b64decode(row.iv)
    auth_tag = base64.b64decode(row.auth_tag)
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    return plaintext.decode("utf-8")

def get_decrypted_news_api_key_for_user(user_id: int) -> str | None:
    query = """
            SELECT encrypted_key, iv, auth_tag
            FROM users_keys
            WHERE user_id = %s AND service = %s
            LIMIT 1
            """
    with get_cursor(settings.news_db, autocommit=True) as (_, cur):
        cur.execute(query, (user_id, "news_api"))
        row = cur.fetchone()
    if not row:
        return None
    
    return decrypt_news_api_key(
        EncryptedNewsApiKey(
        encrypted_key = row["encrypted_key"],
        iv = row["iv"],
        auth_tag = row["auth_tag"],)
    )