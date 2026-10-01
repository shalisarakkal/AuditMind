import hashlib
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt_sha256 hashes the whole password with SHA-256 first: plain bcrypt
# only reads the first 72 bytes, which in some scripts is 24 characters.
# Hashes from before (plain bcrypt) still verify, and are replaced at the
# next sign-in (needs_rehash).
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def normalize_password(password: str) -> str:
    """One form for characters that can be typed two ways (é as one
    character, or e plus an accent), so a password set on one device works
    on another (NFKC, as NIST SP 800-63B advises)."""
    return unicodedata.normalize("NFKC", password)


def hash_password(password: str) -> str:
    return pwd_context.hash(normalize_password(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if pwd_context.verify(normalize_password(plain_password), hashed_password):
        return True
    # A hash from before normalizing: made from the password as typed.
    return pwd_context.identify(hashed_password) == "bcrypt" and pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    return pwd_context.needs_update(hashed_password)


# Checked against when the email is unknown, so a wrong email takes as long
# as a wrong password and the timing doesn't tell which accounts exist.
_DUMMY_HASH = pwd_context.hash("not-a-real-password")


def waste_a_verify(password: str) -> None:
    pwd_context.verify(normalize_password(password), _DUMMY_HASH)


def create_access_token(
    subject: str, expires_delta: timedelta | None = None, session_id: uuid.UUID | None = None
) -> str:
    """The sign-in token: the user, and the session it belongs to (sid),
    which every request checks (api/deps.py)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"exp": expire, "sub": subject}
    if session_id is not None:
        to_encode["sid"] = str(session_id)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def new_refresh_token() -> tuple[str, str]:
    """A session cookie's value, and the hash stored in its place."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    # Random and long, so a fast hash is enough (no guessing to slow down).
    return hashlib.sha256(raw.encode()).hexdigest()
