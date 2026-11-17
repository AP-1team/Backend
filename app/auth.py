from datetime import datetime, timedelta
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

TOKEN_EXPIRE_DAYS = 7
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_token(db: Session, user: models.User) -> str:
    token_value = secrets.token_urlsafe(48)
    db.add(models.Token(
        token=token_value,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    ))
    return token_value


def get_current_user_and_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": "인증되지 않은 요청입니다."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    token = db.query(models.Token).filter(models.Token.token == credentials.credentials).first()
    if token is None:
        raise unauthorized
    if token.expires_at <= datetime.utcnow():
        db.delete(token)
        db.commit()
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_EXPIRED", "message": "인증 토큰이 만료되었습니다."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.id == token.user_id).first()
    if user is None:
        raise unauthorized
    return user, token.token


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    if credentials is None:
        return None
    token = db.query(models.Token).filter(models.Token.token == credentials.credentials).first()
    if token is None or token.expires_at <= datetime.utcnow():
        return None
    return db.query(models.User).filter(models.User.id == token.user_id).first()
