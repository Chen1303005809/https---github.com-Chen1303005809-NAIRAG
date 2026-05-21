# -*- coding: utf-8 -*-
import json
import os
import traceback
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from pymilvus import Collection

from utils.utils import embedding as embedding_func

from .services import get_services

bp = Blueprint("review", __name__)


def _record_ts(rec: dict) -> float:
    raw = str((rec or {}).get("timestamp") or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _sort_rejected_records(records: list[dict]) -> list[dict]:
    return sorted(records or [], key=_record_ts, reverse=True)



def _iter_pending_files(review_dir: str):
    for filename in os.listdir(review_dir):
        if not filename.endswith(".json") or filename.startswith("rejected"):
            continue
        yield filename, os.path.join(review_dir, filename)



def _load_pending_records(
    review_dir: str,
    logger,
    allowed_collections: list[str] | None = None,
    migrate_legacy: bool = False,
) -> list[dict]:
    records = []
    for filename, filepath in _iter_pending_files(review_dir):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                file_records = json.load(f)
            normalized_file_records = []
            file_changed = False
            for rec in file_records:
                selected = []
                for db in rec.get("selected_dbs", []) or []:
                    if db in selected:
                        continue
                    if allowed_collections and db not in allowed_collections:
                        continue
                    selected.append(db)

                source_collection = str(rec.get("source_collection") or "").strip()
                if source_collection and allowed_collections and source_collection not in allowed_collections:
                    source_collection = ""

                targets = [source_collection] if source_collection else selected
                if not targets:
                    targets = [""]
                if len(targets) > 1:
                    file_changed = True

                for db in targets:
                    rec_copy = rec.copy()
                    rec_copy["id"] = str(uuid.uuid4()) if len(targets) > 1 else str(rec.get("id") or uuid.uuid4())
                    rec_copy["selected_dbs"] = [db] if db else []
                    rec_copy["source_collection"] = db
                    rec_copy["data"] = dict(rec.get("data") or {})
                    rec_copy["source_file"] = filename
                    records.append(rec_copy)

                    file_save_copy = rec_copy.copy()
                    file_save_copy.pop("source_file", None)
                    normalized_file_records.append(file_save_copy)

            if migrate_legacy and file_changed:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(normalized_file_records, f, ensure_ascii=False, indent=2)
                logger.info("🔧 已自动拆分历史多库待审记录: %s", filepath)
        except Exception as exc:
            logger.warning("读取审核文件 %s 失败: %s", filename, exc)
    return records


def _cleanup_review_files(review_dir: str, target_ids: set[str], logger):
    if not target_ids:
        return
    for filename, filepath in _iter_pending_files(review_dir):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as exc:
            logger.warning("读取审核文件 %s 失败，跳过清理: %s", filename, exc)
            continue

        remain = [rec for rec in records if str(rec.get("id")) not in target_ids]
        if len(remain) == len(records):
            continue
        if remain:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(remain, f, ensure_ascii=False, indent=2)
            logger.info("🧹 清理审核文件: %s，移除 %s 条记录", filepath, len(records) - len(remain))
        else:
            os.remove(filepath)
            logger.info("🗑️ 删除空审核文件: %s", filepath)


@bp.route("/admin/get_review_data", methods=["GET"])
def get_review_data():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        records = _load_pending_records(
            services.config.review_dir,
            services.logger,
            allowed_collections=services.config.collection_names,
            migrate_legacy=True,
        )
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
        valid_selected_dbs = []
        for db in new_selected_dbs:
            if db in services.config.collection_names and db not in valid_selected_dbs:
                valid_selected_dbs.append(db)
        new_data = payload.get("data", {})
        if not record_id:
            return jsonify({"error": "缺少记录ID"}), 400
        if not valid_selected_dbs:
            return jsonify({"error": "请至少选择一个有效目标数据库"}), 400

        updated = False
        for filename, filepath in _iter_pending_files(services.config.review_dir):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    records = json.load(f)

                for i, rec in enumerate(records):
                    if str(rec.get("id")) != str(record_id):
                        continue
                    old_data = rec.get("data", {})
                    records[i]["selected_dbs"] = [valid_selected_dbs[0]]
                    records[i]["source_collection"] = valid_selected_dbs[0]
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

                    # 如果管理员在编辑时选择了多个目标库，自动拆分为多条独立待审记录。
                    for db in valid_selected_dbs[1:]:
                        cloned_data = records[i]["data"].copy()
                        records.append(
                            {
                                "id": str(uuid.uuid4()),
                                "batch_id": rec.get("batch_id") or rec.get("submission_id") or "",
                                "timestamp": datetime.now().isoformat(),
                                "selected_dbs": [db],
                                "source_collection": db,
                                "uploader": rec.get("uploader") or "anonymous",
                                "data": cloned_data,
                            }
                        )

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
                "details": f"编辑待审核记录 {record_id}，目标库: {', '.join(valid_selected_dbs)}",
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
        if not approved_ids:
            return jsonify({"error": "缺少待通过记录 ID"}), 400

        try:
            pending_records = _load_pending_records(
                services.config.review_dir,
                services.logger,
                allowed_collections=services.config.collection_names,
                migrate_legacy=True,
            )
            records_to_approve = [rec for rec in pending_records if str(rec.get("id")) in approved_ids]
            handled_ids = set()
            approved_doc_ids = []
            approved_uploaders = []
            upload_times = []
            approved_collections = []
            approve_time = datetime.now().isoformat()

            for rec in records_to_approve:
                new_records = embedding_func(rec.get("data", {}))
                if not new_records:
                    continue

                target_collections = []
                source_collection = str(rec.get("source_collection") or "").strip()
                if source_collection in services.config.collection_names:
                    target_collections.append(source_collection)
                for coll_name in rec.get("selected_dbs", []):
                    if coll_name in services.config.collection_names and coll_name not in target_collections:
                        target_collections.append(coll_name)

                if not target_collections:
                    services.logger.warning("待审核记录 %s 缺少有效目标库，已跳过", rec.get("id"))
                    continue

                uploader = str(rec.get("uploader") or "anonymous").strip() or "anonymous"
                for coll_name in target_collections:
                    if coll_name not in approved_collections:
                        approved_collections.append(coll_name)
                    coll = Collection(coll_name)
                    for chunk in new_records:
                        doc_id = str(chunk.get("doc_id") or "").strip()
                        if doc_id and doc_id not in approved_doc_ids:
                            approved_doc_ids.append(doc_id)
                            approved_uploaders.append(uploader)
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
                upload_time = str(rec.get("timestamp") or "").strip()
                if upload_time and upload_time not in upload_times:
                    upload_times.append(upload_time)
                handled_ids.add(str(rec.get("id")))

            _cleanup_review_files(services.config.review_dir, handled_ids, services.logger)
            services.op_log.append(
                {
                    "type": "approve",
                    "user": request.current_user,
                    "details": f"通过 {len(handled_ids)} 条审核记录",
                    "operation_time": approve_time,
                    "approve_time": approve_time,
                    "upload_time": upload_times[0] if len(upload_times) == 1 else "",
                    "upload_times": upload_times,
                    "uploader": approved_uploaders[0] if len(approved_uploaders) == 1 else "",
                    "uploaders": approved_uploaders,
                    "doc_id": approved_doc_ids[0] if len(approved_doc_ids) == 1 else "",
                    "doc_ids": approved_doc_ids,
                    "collection": ",".join(approved_collections),
                }
            )
            return jsonify({"success": True, "message": f"已通过 {len(handled_ids)} 条记录"})
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
        if not rejected_ids:
            return jsonify({"error": "缺少待拒绝记录 ID"}), 400
        reject_reason = data.get("reject_reason", "").strip()

        pending_records = _load_pending_records(
            services.config.review_dir,
            services.logger,
            allowed_collections=services.config.collection_names,
            migrate_legacy=True,
        )
        rejected_by_user = {}
        handled_ids = set()
        upload_times = []
        rejected_collections = []
        reject_time = datetime.now().isoformat()
        for rec in pending_records:
            if str(rec.get("id")) not in rejected_ids:
                continue
            uploader = rec.get("uploader") or "anonymous"
            upload_time = str(rec.get("timestamp") or "").strip()
            if upload_time and upload_time not in upload_times:
                upload_times.append(upload_time)
            source_collection = str(rec.get("source_collection") or "").strip()
            if source_collection and source_collection not in rejected_collections:
                rejected_collections.append(source_collection)
            rejected_by_user.setdefault(uploader, []).append(
                {
                    "id": rec.get("id"),
                    "batch_id": rec.get("batch_id") or rec.get("submission_id") or "",
                    "timestamp": rec.get("timestamp"),
                    "selected_dbs": rec.get("selected_dbs", []),
                    "source_collection": rec.get("source_collection") or "",
                    "data": rec.get("data", {}),
                    "reject_reason": reject_reason or "管理员未填写拒绝原因",
                    "uploader": uploader,
                }
            )
            handled_ids.add(str(rec.get("id")))

        _cleanup_review_files(services.config.review_dir, handled_ids, services.logger)

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
                "details": f"拒绝 {len(handled_ids)} 条审核记录",
                "operation_time": reject_time,
                "reject_time": reject_time,
                "upload_time": upload_times[0] if len(upload_times) == 1 else "",
                "upload_times": upload_times,
                "collection": ",".join(rejected_collections) if rejected_collections else "review_queue",
                "record_ids": list(handled_ids),
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
                    rejected_data[uploader] = _sort_rejected_records(json.load(f))
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
