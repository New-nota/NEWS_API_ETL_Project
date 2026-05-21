from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from config.config import settings

from .db import get_session
from .models import UsersKeys

import requests


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
    stmt = (
        select(UsersKeys.encrypted_key, UsersKeys.iv, UsersKeys.auth_tag)
        .where(UsersKeys.user_id == user_id, UsersKeys.service == "news_api")
        .limit(1)
    )

    with get_session() as session:
        row = session.execute(stmt).first()

    if row is None:
        return None

    return decrypt_news_api_key(
        EncryptedNewsApiKey(
            encrypted_key=row.encrypted_key,
            iv=row.iv,
            auth_tag=row.auth_tag,
        )
    )

_NEWSAPI_PING_URL = "https://newsapi.org/v2/top-headlines"
_VALIDATION_TIMEOUT = 10.0

class KeyValidationResult:
    __slots__ = ("status", "error")

    def __init__(self, status: str, error: str | None) -> None:
        self.status = status # valid invalid exhausted
        self.error = error
    def __repr__(self):
        return f"KeyValidationResult(status={self.status!r}, error={self.error!r})"
    
def validate_news_api_key(key: str) -> KeyValidationResult:
    try:
        resp = requests.get(_NEWSAPI_PING_URL, params={"country":"us", "pageSize":1},
                            headers={"X-Api-Key": key}, timeout=_VALIDATION_TIMEOUT)
    except requests.Timeout as exc:
        raise RuntimeError("Время ожидания провеки NewaAPI истекло") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"NewsApi ошибка сети: {exc}") from exc
    if resp.status_code == 200:
        return KeyValidationResult(status="valid", error=None)
    if resp.status_code == 401:
        try:
            body = resp.json()
            code = body.get("code", "")
            message = body.get("message", "Invalid API key")
        except ValueError:
            code, message = "", "Invalid API key"
        if code == "apiKeyExhausted":
            return KeyValidationResult(status="exhausted", error=None)
        return KeyValidationResult(status="invalid", error=message)
    if resp.status_code == 429:
        return KeyValidationResult(status="invalid", error=None)
    raise RuntimeError(f"Неожиданный ответ от NewsApi: {resp.status_code}")