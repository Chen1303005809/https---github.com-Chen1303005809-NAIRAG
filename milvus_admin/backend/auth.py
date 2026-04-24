# -*- coding: utf-8 -*-
import datetime as dt
import sqlite3
from functools import wraps

import jwt
from flask import jsonify, request
from passlib.context import CryptContext

from .config import AdminConfig

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AdminAuth:
    def __init__(self, config: AdminConfig, logger):
        self.config = config
        self.logger = logger

    def get_user_from_db(self, username: str):
        try:
            conn = sqlite3.connect(self.config.users_db_path)
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
            self.logger.error("数据库连接失败: %s", exc)
            return None

    def login(self, username: str, password: str):
        user = self.get_user_from_db(username)
        if not user:
            return {"error": "用户不存在"}, 401
        if not pwd_context.verify(password, user["password_hash"]):
            return {"error": "密码错误"}, 401

        token = jwt.encode(
            {
                "username": user["username"],
                "role": user["role"],
                "exp": dt.datetime.utcnow() + dt.timedelta(hours=self.config.jwt_expire_hours),
            },
            self.config.jwt_secret,
            algorithm=self.config.jwt_algorithm,
        )
        return {
            "success": True,
            "token": token,
            "username": user["username"],
            "role": user["role"],
        }, 200

    def decode_header_token(self):
        token = request.headers.get("Authorization")
        if not token:
            return None, {"error": "未提供认证令牌"}, 401

        if token.startswith("Bearer "):
            token = token[7:]

        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm],
            )
            return payload, None, None
        except jwt.ExpiredSignatureError:
            return None, {"error": "令牌已过期"}, 401
        except jwt.InvalidTokenError:
            return None, {"error": "无效令牌"}, 401

    def require_login(self, fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            payload, err, status = self.decode_header_token()
            if err:
                return jsonify(err), status
            request.current_user = payload["username"]
            request.current_role = payload.get("role", "user")
            return fn(*args, **kwargs)

        return wrapper

    def require_role(self, required_role: str):
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                payload, err, status = self.decode_header_token()
                if err:
                    return jsonify(err), status
                request.current_user = payload["username"]
                request.current_role = payload.get("role", "user")
                if required_role == "admin" and request.current_role != "admin":
                    return jsonify({"error": "需要管理员权限"}), 403
                return fn(*args, **kwargs)

            return wrapper

        return decorator
