# -*- coding: utf-8 -*-
import json
import os
import traceback
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from pymilvus import Collection

from utils.utils import embedding as embedding_func

from .data_utils import group_by_doc_id, parse_file_urls, serialize_item
from .services import get_services

bp = Blueprint("data", __name__)



def _delete_old_files(static_root: str, old_urls: list[str], logger):
    for url in old_urls or []:
        if not url or url == "N/A":
            continue
        rel_path = url.strip()
        if rel_path.startswith("/admin/static/"):
            rel_path = rel_path[len("/admin/static/"):]
        elif rel_path.startswith("/upload/static/"):
            rel_path = rel_path[len("/upload/static/"):]
        elif rel_path.startswith("/static/"):
            rel_path = rel_path[len("/static/"):]
        elif rel_path.startswith("/"):
            rel_path = rel_path[1:]
        file_path = os.path.join(static_root, rel_path)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("🗑️ 已删除旧文件: %s", file_path)


@bp.route("/admin/get_data_paginated", methods=["GET"])
def get_data_paginated():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        collection_name = request.args.get("collection")
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 13683))
        if not collection_name:
            return jsonify({"error": "缺少 collection 参数"}), 400

        try:
            collection = Collection(collection_name)
            collection.load()
            expr = "id >= 0"
            total_results = collection.query(expr=expr, output_fields=["id"], limit=13683)
            total = len(total_results)
            offset = (page - 1) * page_size
            results = collection.query(expr=expr, output_fields=["*"], limit=page_size, offset=offset)
            rows = [serialize_item(item) for item in results]
            grouped = group_by_doc_id(rows)
            return jsonify(
                {
                    "data": rows,
                    "grouped_data": grouped,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
            )
        except Exception as exc:
            services.logger.error("❌ 查询异常: %s", exc)
            traceback.print_exc()
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/update_record", methods=["POST"])
def update_record():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        collection_name = request.args.get("collection")
        data = request.get_json() or {}
        if not collection_name or "id" not in data:
            return jsonify({"error": "缺少必要参数"}), 400

        try:
            collection = Collection(collection_name)
            old_id = int(data["id"])
            old_results = collection.query(expr=f"id == {old_id}", output_fields=["doc_id", "file_url"])
            if not old_results:
                raise ValueError(f"原记录 ID={old_id} 不存在")

            old_doc_id = str(old_results[0].get("doc_id") or "").strip()
            if not old_doc_id:
                raise ValueError(f"原记录 ID={old_id} 缺少 doc_id")

            old_doc_rows = collection.query(
                expr=f'doc_id == "{old_doc_id}"',
                output_fields=["file_url"],
                limit=13683,
            )
            old_urls = []
            for row in old_doc_rows:
                for u in parse_file_urls(row.get("file_url", "")):
                    if u not in old_urls:
                        old_urls.append(u)

            # 按 doc_id 整体替换，避免只删单个 chunk 导致脏数据残留
            collection.delete(f'doc_id == "{old_doc_id}"')
            collection.flush()

            payload = dict(data)
            payload["doc_id"] = old_doc_id
            new_records = embedding_func(payload)
            if not new_records:
                raise ValueError("未生成任何embedding记录")

            for chunk in new_records:
                insert_data = [
                    [chunk["chunk_id"]],
                    [chunk["doc_id"]],
                    [chunk["field_type"]],
                    [chunk["field_text"]],
                    [chunk["text_embedding"]],
                    [chunk["vl_embedding"]],
                    [chunk["weight"]],
                    [chunk["file_url"]],
                ]
                collection.insert(insert_data)

            collection.flush()
            _delete_old_files(services.config.static_root, old_urls, services.logger)
            try:
                collection.compact()
                collection.wait_for_compaction_completed()
            except Exception as exc:
                services.logger.warning("⚠️ compact 触发失败（不影响功能）: %s", exc)

            services.op_log.append(
                {
                    "type": "update",
                    "collection": collection_name,
                    "record_id": old_id,
                    "details": f"修改对象: {data.get('object', '')}, 生成 {len(new_records)} 个分片",
                    "operation_time": datetime.now().isoformat(),
                }
            )
            return jsonify({"success": True, "message": f"更新成功！生成 {len(new_records)} 个分片"})
        except Exception as exc:
            services.logger.error("❌ 更新失败: %s", exc)
            services.logger.error(traceback.format_exc())
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/delete_record", methods=["DELETE"])
def delete_single_record():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        collection_name = request.args.get("collection")
        record_id = request.args.get("id")
        if not collection_name or not record_id:
            return jsonify({"error": "缺少必要参数"}), 400

        try:
            collection = Collection(collection_name)
            query_results = collection.query(expr=f"id == {int(record_id)}", output_fields=["doc_id"])
            if not query_results:
                return jsonify({"error": f"记录 ID={record_id} 不存在"}), 404

            doc_id = query_results[0].get("doc_id")
            collection.delete(f'doc_id == "{doc_id}"')
            collection.flush()
            try:
                collection.compact()
                collection.wait_for_compaction_completed()
            except Exception as exc:
                services.logger.warning("⚠️ compact 触发失败（不影响功能）: %s", exc)

            services.op_log.append(
                {
                    "type": "delete",
                    "collection": collection_name,
                    "record_id": int(record_id),
                    "details": f"删除了doc_id={doc_id}的所有分片",
                    "operation_time": datetime.now().isoformat(),
                }
            )
            return jsonify({"success": True, "message": f"已成功删除 doc_id={doc_id} 的所有分片"})
        except Exception as exc:
            services.logger.error("❌ 删除失败: %s", exc)
            services.logger.error(traceback.format_exc())
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/delete_records", methods=["POST"])
def delete_multiple_records():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        collection_name = request.args.get("collection")
        ids = (request.get_json() or {}).get("ids", [])
        if not collection_name or not ids:
            return jsonify({"error": "缺少必要参数"}), 400

        try:
            collection = Collection(collection_name)
            doc_ids_to_delete = set()
            for id_str in ids:
                try:
                    result = collection.query(expr=f"id == {int(id_str)}", output_fields=["doc_id"])
                    if result:
                        doc_ids_to_delete.add(result[0].get("doc_id"))
                except Exception:
                    continue

            deleted_count = 0
            for doc_id in doc_ids_to_delete:
                try:
                    collection.delete(f'doc_id == "{doc_id}"')
                    deleted_count += 1
                except Exception:
                    continue

            collection.flush()
            try:
                collection.compact()
                collection.wait_for_compaction_completed()
            except Exception as exc:
                services.logger.warning("⚠️ compact 触发失败: %s", exc)

            services.op_log.append(
                {
                    "type": "batch_delete",
                    "collection": collection_name,
                    "record_ids": ids,
                    "details": f"批量删除了 {deleted_count} 个doc_id的所有分片",
                    "operation_time": datetime.now().isoformat(),
                }
            )
            return jsonify(
                {
                    "success": True,
                    "deleted": deleted_count,
                    "message": f"成功删除 {deleted_count} 个doc_id的所有分片",
                }
            )
        except Exception as exc:
            services.logger.error("❌ 批量删除失败: %s", exc)
            services.logger.error(traceback.format_exc())
            return jsonify({"error": str(exc)}), 500

    return _handler()


@bp.route("/admin/get_logs", methods=["GET"])
def get_logs():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        return jsonify(services.op_log.list_all())

    return _handler()


@bp.route("/admin/get_rag_options", methods=["GET"])
def get_rag_options():
    services = get_services(current_app)

    @services.auth.require_login
    def _handler():
        try:
            if os.path.exists(services.config.options_file):
                with open(services.config.options_file, "r", encoding="utf-8") as f:
                    options = json.load(f)
            else:
                options = {
                    "type": ["解释概念", "操作步骤", "故障排查", "权限说明", "数据查询"],
                    "object": ["净头寸", "订单管理", "用户权限", "报表导出", "风控设置"],
                    "purpose": ["用户咨询", "内部培训", "系统帮助", "客户支持", "审计合规"],
                    "customer_type": ["个人客户", "机构客户", "内部员工", "合作伙伴", "系统管理员"],
                }
            return jsonify({"success": True, "options": options})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    return _handler()
