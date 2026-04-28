# -*- coding: utf-8 -*-
import json
import os
import traceback
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from pymilvus import Collection

from utils.utils import embedding as embedding_func

from .services import get_services

bp = Blueprint("review", __name__)



def _iter_pending_files(review_dir: str):
    for filename in os.listdir(review_dir):
        if not filename.endswith(".json") or filename.startswith("rejected"):
            continue
        yield filename, os.path.join(review_dir, filename)



def _cleanup_review_files(review_dir: str, review_records: list[dict], target_ids: set[str], logger):
    files_to_delete = set()
    for rec in review_records:
        if str(rec.get("id")) in target_ids:
            files_to_delete.add(rec.get("source_file", f"review_{rec['id']}.json"))

    for filename in files_to_delete:
        filepath = os.path.join(review_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info("🗑️ 删除审核文件: %s", filepath)


@bp.route("/admin/get_review_data", methods=["GET"])
def get_review_data():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        records = []
        for filename, filepath in _iter_pending_files(services.config.review_dir):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    file_records = json.load(f)
                for rec in file_records:
                    rec_copy = rec.copy()
                    rec_copy["selected_dbs"] = rec.get("selected_dbs", [])
                    rec_copy["source_file"] = filename
                    records.append(rec_copy)
            except Exception as exc:
                services.logger.warning("读取审核文件 %s 失败: %s", filename, exc)
        return jsonify(records)

    return _handler()


@bp.route("/admin/update_review_record", methods=["POST"])
def update_review_record():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        payload = request.get_json() or {}
        record_id = payload.get("id")
        new_selected_dbs = payload.get("selected_dbs", [])
        new_data = payload.get("data", {})
        if not record_id:
            return jsonify({"error": "缺少记录ID"}), 400

        updated = False
        for filename, filepath in _iter_pending_files(services.config.review_dir):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    records = json.load(f)

                for i, rec in enumerate(records):
                    if str(rec.get("id")) != str(record_id):
                        continue
                    old_data = rec.get("data", {})
                    records[i]["selected_dbs"] = new_selected_dbs
                    records[i]["data"] = {
                        "type": new_data.get("type", old_data.get("type", "")),
                        "object": new_data.get("object", old_data.get("object", "")),
                        "purpose": new_data.get("purpose", old_data.get("purpose", "")),
                        "customer_type": new_data.get("customer_type", old_data.get("customer_type", "")),
                        "keyword": new_data.get("keyword", old_data.get("keyword", "")),
                        "problem": new_data.get("problem", old_data.get("problem", [])),
                        "web_links": new_data.get("web_links", old_data.get("web_links", [])),
                        "reply_logic": new_data.get("reply_logic", old_data.get("reply_logic", "")),
                        "feature_explanation": new_data.get(
                            "feature_explanation", old_data.get("feature_explanation", "")
                        ),
                        "example": new_data.get("example", old_data.get("example", "")),
                        "notes": new_data.get("notes", old_data.get("notes", "")),
                        "image_url": new_data.get("image_url", old_data.get("image_url", ["N/A"])),
                        "file_url": new_data.get("file_url", old_data.get("file_url", ["N/A"])),
                    }
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(records, f, ensure_ascii=False, indent=2)
                    updated = True
                    break
                if updated:
                    break
            except Exception as exc:
                services.logger.error("处理文件 %s 时出错: %s", filename, exc)

        if not updated:
            return jsonify({"error": "未找到该记录，可能已被处理"}), 404

        services.op_log.append(
            {
                "type": "update_review_record",
                "details": f"编辑待审核记录 {record_id}，目标库: {', '.join(new_selected_dbs)}",
                "user": request.current_user,
            }
        )
        return jsonify({"success": True, "message": "保存成功"})

    return _handler()


@bp.route("/admin/approve_records", methods=["POST"])
def approve_records():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        approved_ids = set(map(str, data.get("ids", [])))
        review_records = data.get("records", [])

        try:
            for rec in review_records:
                if str(rec.get("id")) not in approved_ids:
                    continue
                new_records = embedding_func(rec.get("data", {}))
                if not new_records:
                    continue

                for coll_name in rec.get("selected_dbs", []):
                    coll = Collection(coll_name)
                    for chunk in new_records:
                        coll.insert(
                            [
                                [chunk["chunk_id"]],
                                [chunk["doc_id"]],
                                [chunk.get("type", "")],
                                [chunk.get("object", "")],
                                [chunk.get("purpose", "")],
                                [chunk.get("customer_type", "")],
                                [chunk["field_type"]],
                                [chunk["field_text"]],
                                [chunk["text_embedding"]],
                                [chunk["vl_embedding"]],
                                [chunk["weight"]],
                                [chunk["file_url"]],
                                [chunk.get("web_links", "")],
                            ]
                        )
                    coll.flush()

            _cleanup_review_files(services.config.review_dir, review_records, approved_ids, services.logger)
            services.op_log.append(
                {
                    "type": "approve",
                    "user": request.current_user,
                    "details": f"通过 {len(approved_ids)} 条审核记录",
                    "operation_time": datetime.now().isoformat(),
                }
            )
            return jsonify({"success": True, "message": f"已通过 {len(approved_ids)} 条记录"})
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/reject_records", methods=["POST"])
def reject_records():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        rejected_ids = set(map(str, data.get("ids", [])))
        review_records = data.get("records", [])
        reject_reason = data.get("reject_reason", "").strip()

        rejected_by_user = {}
        for rec in review_records:
            if str(rec.get("id")) not in rejected_ids:
                continue
            uploader = rec.get("uploader") or "anonymous"
            rejected_by_user.setdefault(uploader, []).append(
                {
                    "id": rec.get("id"),
                    "timestamp": rec.get("timestamp"),
                    "selected_dbs": rec.get("selected_dbs", []),
                    "data": rec.get("data", {}),
                    "reject_reason": reject_reason or "管理员未填写拒绝原因",
                    "uploader": uploader,
                }
            )

        _cleanup_review_files(services.config.review_dir, review_records, rejected_ids, services.logger)

        rejected_dir = os.path.join(services.config.review_dir, "rejected")
        os.makedirs(rejected_dir, exist_ok=True)
        for uploader, items in rejected_by_user.items():
            user_file = os.path.join(rejected_dir, f"{uploader}.json")
            existing = []
            if os.path.exists(user_file):
                try:
                    with open(user_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.extend(items)
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        services.op_log.append(
            {
                "type": "reject",
                "user": request.current_user,
                "details": f"拒绝 {len(rejected_ids)} 条审核记录",
                "operation_time": datetime.now().isoformat(),
                "collection": "review_queue",
                "record_ids": list(rejected_ids),
            }
        )
        return jsonify({"rejected_by_user": rejected_by_user})

    return _handler()


@bp.route("/admin/get_all_rejected", methods=["GET"])
def get_all_rejected():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        if request.current_user != "admin":
            return jsonify({"error": "权限不足"}), 403
        rejected_data = {}
        rejected_dir = os.path.join(services.config.review_dir, "rejected")
        if os.path.exists(rejected_dir):
            for file in os.listdir(rejected_dir):
                if not file.endswith(".json"):
                    continue
                uploader = file.replace(".json", "")
                with open(os.path.join(rejected_dir, file), "r", encoding="utf-8") as f:
                    rejected_data[uploader] = json.load(f)
        return jsonify({"rejected": rejected_data})

    return _handler()


@bp.route("/admin/delete_rejected", methods=["POST"])
def delete_rejected():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        data = request.get_json() or {}
        uploader = data.get("uploader")
        record_id = data.get("id")
        file_path = os.path.join(services.config.review_dir, "rejected", f"{uploader}.json")
        if not os.path.exists(file_path):
            return jsonify({"success": True, "message": "文件已不存在"})

        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        records = [r for r in records if str(r.get("id")) != str(record_id)]
        if records:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        else:
            os.remove(file_path)
        return jsonify({"success": True})

    return _handler()


@bp.route("/admin/clear_all_rejected", methods=["POST"])
def clear_all_rejected():
    services = get_services(current_app)

    @services.auth.require_role("admin")
    def _handler():
        rejected_dir = os.path.join(services.config.review_dir, "rejected")
        if os.path.exists(rejected_dir):
            import shutil

            shutil.rmtree(rejected_dir)
            os.makedirs(rejected_dir, exist_ok=True)
        return jsonify({"success": True})

    return _handler()
