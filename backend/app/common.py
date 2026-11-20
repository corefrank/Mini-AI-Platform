import logging
import os
import time
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from .db import CallLog, Session, User, utcnow

logger = logging.getLogger("mini_ai")
passwords = PasswordHash.recommended()
dummy_hash = passwords.hash("local-dummy-verification")
bearer = HTTPBearer(auto_error=False)


def jwt_secret():
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32 or secret.startswith("replace"):
        raise RuntimeError("请配置至少 32 个字符的 JWT_SECRET")
    return secret


def issue_token(user_id):
    now = utcnow()
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=8), "aud": "mini-ai"},
        jwt_secret(), algorithm="HS256",
    )


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    """只信任签名后的用户 ID，每次从数据库读取角色。"""
    denied = HTTPException(401, "请重新登录", headers={"WWW-Authenticate": "Bearer"})
    if not credentials:
        raise denied
    try:
        claims = jwt.decode(credentials.credentials, jwt_secret(), algorithms=["HS256"],
                            audience="mini-ai", options={"require": ["sub", "exp", "iat", "aud"]})
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise denied from None
    if not 0 < user_id <= 2_147_483_647:
        raise denied
    with Session() as db:
        user = db.get(User, user_id)
    if user is None:
        raise denied
    return user


Identity = Annotated[User, Depends(current_user)]


def admin_user(user: Identity):
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


Admin = Annotated[User, Depends(admin_user)]


def owned(db, table, object_id, user_id):
    item = db.get(table, object_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(404, "资源不存在")
    return item


def record_call(request_id, user_id, kind, requested_at, start, status, *,
                model=None, error=None, usage=None):
    """仅保存受控错误与 Token 数值，日志故障不覆盖业务结果。"""
    duration_ms = round((time.monotonic() - start) * 1000)
    try:
        with Session.begin() as db:
            db.add(CallLog(request_id=request_id, user_id=user_id, kind=kind,
                           requested_at=requested_at, duration_ms=duration_ms, status=status,
                           model=model, error=error, usage=usage))
    except Exception as exc:
        logger.error("call_log_write_failed request_id=%s type=%s", request_id, type(exc).__name__)
