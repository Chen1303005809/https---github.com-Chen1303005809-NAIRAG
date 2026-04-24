# -*- coding: utf-8 -*-
import os

from flask import Blueprint, current_app, jsonify, request

from .services import get_services

bp = Blueprint("uploads", __name__)


@bp.route("/upload_image", methods=["POST"])
def upload_image():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        if "image" not in request.files:
            return jsonify({"error": "未选择文件"}), 400
        file = request.files["image"]
        if not file or file.filename == "":
            return jsonify({"error": "未选择文件"}), 400

        original_name = file.filename
        if not original_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg")):
            return jsonify({"error": "不支持的图片格式"}), 400

        target_path = os.path.join(services.config.static_root, "images", original_name)
        if os.path.exists(target_path):
            return jsonify({"success": True, "url": f"/static/images/{original_name}"})

        file.save(target_path)
        return jsonify({"success": True, "url": f"/static/images/{original_name}"})

    return _handler()


@bp.route("/upload_document", methods=["POST"])
def upload_document():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        if "document" not in request.files:
            return jsonify({"error": "未选择文件"}), 400
        file = request.files["document"]
        if not file or file.filename == "":
            return jsonify({"error": "未选择文件"}), 400

        original_name = file.filename
        if not original_name.lower().endswith((".pdf", ".docx", ".doc", ".zip", ".xlsx", ".xls", ".txt")):
            return jsonify({"error": "不支持的文档格式"}), 400

        target_path = os.path.join(services.config.static_root, "documents", original_name)
        if os.path.exists(target_path):
            return jsonify(
                {
                    "success": True,
                    "url": f"/static/documents/{original_name}",
                    "filename": original_name,
                }
            )

        file.save(target_path)
        return jsonify(
            {
                "success": True,
                "url": f"/static/documents/{original_name}",
                "filename": original_name,
            }
        )

    return _handler()
