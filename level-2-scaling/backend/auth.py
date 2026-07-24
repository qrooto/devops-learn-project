"""
JWT-авторизация.

Почему JWT, а не сессии?
  Сессии хранят состояние на сервере (в памяти или Redis).
  JWT — токен содержит всю информацию о пользователе, подписан секретом.
  Сервер не хранит ничего — он только проверяет подпись.
  Это делает JWT идеальным для горизонтального масштабирования:
  любой инстанс бэкенда может проверить токен без обращения к общему хранилищу.

Почему это важно для DevOps?
  Stateless auth = нет привязки к конкретному инстансу.
  Можно добавлять и убирать инстансы в любой момент.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# SECRET_KEY должен быть одинаковым на всех инстансах бэкенда.
# Передаётся через переменную окружения — никогда не хардкодить!
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Возвращает пользователя если токен валиден, None если токена нет."""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {"id": int(payload["sub"]), "username": payload["username"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")


def require_user(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Обязательная авторизация — 401 если токена нет."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
