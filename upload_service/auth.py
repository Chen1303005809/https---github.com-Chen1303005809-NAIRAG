# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException
from passlib.context import CryptContext

from .config import UploadConfig

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UploadAuthService:
    def __init__(self, config: UploadConfig):
        self.config = config

    def get_user_from_db(self, username: str):
        try:
            conn = sqlite3.connect(self.config.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, password_hash, role FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return {
                "username": row["username"],
                "password_hash": row["password_hash"],
                "role": row["role"],
            }
        except Exception:
            return None

    def login(self, username: str, password: str) -> dict:
        user = self.get_user_from_db(username)
        if not user or not pwd_context.verify(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        access_token = jwt.encode(
            {
                "sub": user["username"],
                "role": user["role"],
                "exp": datetime.now(self.config.beijing_tz) + timedelta(hours=24),
            },
            self.config.secret_key,
            algorithm=self.config.algorithm,
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": user["role"],
            "username": user["username"],
        }

    def decode_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
            )
            username = payload.get("sub")
            role = payload.get("role")
            if not username:
                raise HTTPException(status_code=401, detail="无效凭证")
            return {"username": username, "role": role}
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token已过期，请重新登录")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="无效的Token")

    def parse_uploader(self, authorization: Optional[str]) -> str:
        if not authorization:
            raise HTTPException(status_code=401, detail="未提供认证信息，请先登录")
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        payload = self.decode_token(token)
        username = payload.get("username")
        if not username:
            raise HTTPException(status_code=401, detail="Token中缺少用户名")
        return username
