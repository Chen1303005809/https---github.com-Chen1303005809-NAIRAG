# -*- coding: utf-8 -*-
import os

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from .services import get_services

bp = Blueprint("public", __name__)


@bp.route("/", methods=["GET"])
def home():
    return "✅ Milvus 管理后台运行中... 请访问 /admin_dashboard.html"


@bp.route("/login", methods=["POST"])
def login():
    services = get_services(current_app)
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    payload, status = services.auth.login(username=username, password=password)
    return jsonify(payload), status


@bp.route("/admin/whoami", methods=["GET"])
def whoami():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        return jsonify({"username": request.current_user})

    return _handler()


@bp.route("/admin_dashboard.html", methods=["GET"])
@bp.route("/app_reject_928_2.html", methods=["GET"])  # 兼容旧路径
def serve_admin_html():
    services = get_services(current_app)
    admin_dir = os.path.join(services.config.base_dir, "milvus_admin")
    return send_from_directory(admin_dir, "admin_dashboard.html")


@bp.route("/user_management.html", methods=["GET"])
def serve_user_management():
    services = get_services(current_app)
    admin_dir = os.path.join(services.config.base_dir, "milvus_admin")
    return send_from_directory(admin_dir, "user_management.html")


@bp.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename: str):
    services = get_services(current_app)
    return send_from_directory(services.config.static_root, filename)
