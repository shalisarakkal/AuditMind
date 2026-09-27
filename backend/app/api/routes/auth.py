from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Token:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    org = Organization(name=payload.org_name)
    db.add(org)
    db.flush()

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(OrgMembership(user_id=user.id, org_id=org.id, role=UserRole.admin))
    db.commit()

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


_LOGIN_BODY_DOCS = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": LoginRequest.model_json_schema()},
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "required": ["username", "password"],
                    "properties": {
                        "username": {"type": "string", "description": "Your email address"},
                        "password": {"type": "string", "format": "password"},
                    },
                }
            },
        },
    }
}


@router.post("/login", response_model=Token, openapi_extra=_LOGIN_BODY_DOCS)
async def login(request: Request, db: Session = Depends(get_db)) -> Token:
    """JSON {email, password}, or an OAuth2 password form (username = email),
    which is what Swagger's Authorize button sends."""
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")
    else:
        form = await request.form()
        data = {"email": form.get("username"), "password": form.get("password")}
    try:
        payload = LoginRequest.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False))

    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)
