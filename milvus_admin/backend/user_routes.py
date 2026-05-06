# -*- coding: utf-8 -*-
import sqlite3

from flask import Blueprint, current_app, jsonify, request
from passlib.context import CryptContext

from .services import get_services

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

bp = Blueprint("users", __name__)
VALID_ROLES = {"admin", "editor", "user"}
MIN_PASSWORD_LENGTH = 6


def _validate_password(password: str):
    if not password:
        return "密码不能为空"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位"
    return None


@bp.route("/admin/users", methods=["GET"])
def get_all_users():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        try:
            conn = sqlite3.connect(services.config.users_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
            users = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify({"success": True, "users": users})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/users/create", methods=["POST"])
def create_user():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        role = data.get("role", "user")

        if not username or not password:
            return jsonify({"error": "用户名和密码不能为空"}), 400
        password_error = _validate_password(password)
        if password_error:
            return jsonify({"error": password_error}), 400
        if role not in VALID_ROLES:
            return jsonify({"error": "无效的角色"}), 400

        conn = sqlite3.connect(services.config.users_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "用户名已存在"}), 400

        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pwd_context.hash(password), role),
        )
        conn.commit()
        conn.close()
        services.op_log.append(
            {"type": "create_user", "details": f"创建用户 {username} ({role})", "user": request.current_user}
        )
        return jsonify({"success": True, "message": "用户创建成功"})

    return _handler()


@bp.route("/admin/users/update", methods=["POST"])
def update_user():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        user_id = data.get("id")
        username = data.get("username")
        role = data.get("role")
        password = (data.get("password") or "").strip()

        if not user_id or not username or not role:
            return jsonify({"error": "参数不完整"}), 400
        if role not in VALID_ROLES:
            return jsonify({"error": "无效的角色"}), 400
        if password:
            password_error = _validate_password(password)
            if password_error:
                return jsonify({"error": password_error}), 400

        conn = sqlite3.connect(services.config.users_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "用户名已存在"}), 400

        if password:
            cursor.execute(
                "UPDATE users SET username = ?, password_hash = ?, role = ? WHERE id = ?",
                (username, pwd_context.hash(password), role, user_id),
            )
        else:
            cursor.execute("UPDATE users SET username = ?, role = ? WHERE id = ?", (username, role, user_id))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    return _handler()


@bp.route("/admin/users/change_password", methods=["POST"])
def change_user_password():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        user_id = data.get("id")
        password = (data.get("password") or "").strip()

        if not user_id:
            return jsonify({"error": "缺少用户ID"}), 400
        password_error = _validate_password(password)
        if password_error:
            return jsonify({"error": password_error}), 400

        conn = sqlite3.connect(services.config.users_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "用户不存在"}), 404

        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pwd_context.hash(password), user_id),
        )
        conn.commit()
        conn.close()
        services.op_log.append(
            {"type": "change_user_password", "details": f"修改用户 {row['username']} 的密码", "user": request.current_user}
        )
        return jsonify({"success": True, "message": "密码修改成功"})

    return _handler()


@bp.route("/admin/users/delete", methods=["POST"])
def delete_user():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        user_id = data.get("id")
        if not user_id:
            return jsonify({"error": "缺少用户ID"}), 400
        if str(user_id) == "1":
            return jsonify({"error": "禁止删除默认管理员"}), 400

        conn = sqlite3.connect(services.config.users_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        services.op_log.append(
            {"type": "delete_user", "details": f"删除用户 ID={user_id}", "user": request.current_user}
        )
        return jsonify({"success": True})

    return _handler()
