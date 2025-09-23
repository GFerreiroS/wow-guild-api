"""Security utilities for authentication and authorization."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from . import db

# OAuth2 configuration ------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token", auto_error=False
)

# Password hashing ---------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# JWT helpers ---------------------------------------------------------------

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def create_access_token(*, subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# User retrieval ------------------------------------------------------------


def authenticate_user(username: str, password: str, session: Session) -> Optional[db.User]:
    user = session.exec(select(db.User).where(db.User.username == username)).first()
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user


CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    session: Session = Depends(db.get_session), token: str = Depends(oauth2_scheme)
) -> db.User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError as exc:  # pragma: no cover - explicit for clarity
        raise CREDENTIALS_EXCEPTION from exc

    user = session.exec(select(db.User).where(db.User.username == username)).first()
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user


def get_optional_user(
    session: Session = Depends(db.get_session),
    token: Optional[str] = Depends(optional_oauth2_scheme),
) -> Optional[db.User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    return session.exec(select(db.User).where(db.User.username == username)).first()


def require_authenticated_user(
    current_user: db.User = Depends(get_current_user),
) -> db.User:
    return current_user


def ensure_roles(user: db.User, allowed_roles: Iterable[str]) -> None:
    if user.role not in allowed_roles:
        allowed = ", ".join(sorted(allowed_roles))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: requires one of the following roles: {allowed}",
        )


def require_roles(*roles: str) -> Callable[[db.User], db.User]:
    if not roles:
        raise ValueError("At least one role must be provided")

    def dependency(current_user: db.User = Depends(get_current_user)) -> db.User:
        ensure_roles(current_user, roles)
        return current_user

    return dependency


def users_exist(session: Session) -> bool:
    return session.exec(select(db.User)).first() is not None


def ensure_authenticated_or_bootstrap(
    session: Session,
    current_user: Optional[db.User],
    required_roles: Optional[Iterable[str]] = None,
) -> Optional[db.User]:
    """Require authentication only after at least one user exists."""

    if not users_exist(session):
        return current_user

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if required_roles:
        ensure_roles(current_user, required_roles)

    return current_user
