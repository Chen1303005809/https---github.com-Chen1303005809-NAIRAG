# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta

import jwt
from passlib.context import CryptContext

from .config import PortalConfig

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PortalAuthService:
    def __init__(self, config: PortalConfig):
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
        except Exception as exc:
            print(f"【门户】数据库连接失败: {exc}")
            return None

    def verify_user(self, username: str, password: str):
        user = self.get_user_from_db(username)
        if not user:
            return None
        if not pwd_context.verify(password, user["password_hash"]):
            return None
        return user

    def build_tokens(self, user: dict) -> tuple[str, str]:
        now = datetime.utcnow()
        exp = now + timedelta(hours=24)
        fastapi_token = jwt.encode(
            {
                "sub": user["username"],
                "username": user["username"],
                "role": user["role"],
                "exp": exp,
            },
            self.config.fastapi_secret,
            algorithm=self.config.algorithm,
        )
        flask_token = jwt.encode(
            {
                "username": user["username"],
                "role": user["role"],
                "exp": exp,
            },
            self.config.flask_secret,
            algorithm=self.config.algorithm,
        )
        return fastapi_token, flask_token
