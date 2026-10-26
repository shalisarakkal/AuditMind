import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import jwt
from jwt import InvalidTokenError as JWTError

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id


def test_expired_access_token_fails_to_decode():
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_access_token_preserves_session_identifier():
    user_id = str(uuid.uuid4())
    session_id = uuid.uuid4()
    payload = decode_access_token(create_access_token(user_id, session_id=session_id))
    assert payload["sub"] == user_id
    assert payload["sid"] == str(session_id)
    assert isinstance(payload["exp"], int)


def test_access_token_rejects_wrong_signature():
    token = jwt.encode(
        {"sub": str(uuid.uuid4())},
        "different-signing-key-for-regression-test",
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_access_token_rejects_unsigned_token():
    def encoded(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    token = f'{encoded({"alg": "none", "typ": "JWT"})}.{encoded({"sub": str(uuid.uuid4())})}.'
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_access_token_accepts_existing_hs256_format(monkeypatch):
    """Build a legacy-format JWT independently, so encode/decode cannot hide drift."""
    key = "legacy-format-regression-signing-key"
    monkeypatch.setattr(settings, "SECRET_KEY", key)
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    expected = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }

    def encoded(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    message = encoded({"alg": "HS256", "typ": "JWT"}) + b"." + encoded(expected)
    signature = hmac.new(key.encode(), message, hashlib.sha256).digest()
    token = message + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")
    assert decode_access_token(token.decode()) == expected


def test_access_token_rejects_algorithm_outside_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    token = jwt.encode(
        {"sub": str(uuid.uuid4())}, settings.SECRET_KEY, algorithm="HS512"
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


@pytest.mark.parametrize("sid", [None, 123, [], {}, "not-a-uuid"])
def test_invalid_session_claim_is_rejected_without_server_error(sid):
    from app.api.deps import parse_access_token
    token = jwt.encode({"sub": str(uuid.uuid4()), "sid": sid,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert parse_access_token(token) is None
