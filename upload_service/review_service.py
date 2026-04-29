# -*- coding: utf-8 -*-
import json
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile

from .auth import UploadAuthService
from .config import UploadConfig
from .file_service import FileService


class ReviewService:
    def __init__(self, config: UploadConfig, auth: UploadAuthService, files: FileService):
        self.config = config
        self.auth = auth
        self.files = files

    def _validate_records(self, records: list[dict]):
        if not records:
            raise HTTPException(400, "JSON 列表不能为空")
        if not isinstance(records, list):
            raise HTTPException(400, "JSON 数据必须是数组或单个对象")
        for record in records:
            if not str(record.get("reply_logic", "")).strip():
                raise HTTPException(400, "每条记录必须包含非空 '回复逻辑框架'")
            if not str(record.get("feature_explanation", "")).strip():
                raise HTTPException(400, "每条记录必须包含非空 '说明功能'")
            if "problem" in record and not isinstance(record["problem"], list):
                raise HTTPException(400, "'problem' 必须是字符串数组")

    def _load_json(self, path: str, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, path: str, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def submit_upload_json(
        self,
        uploader: str,
        records_json: str,
        selected_dbs: list[str],
        files: list[UploadFile],
        doc_files: list[UploadFile],
        rejected_id: Optional[str] = None,
    ):
        try:
            parsed = json.loads(records_json)
            dicts = [parsed] if isinstance(parsed, dict) else parsed
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"无效的 JSON 数据: {exc}")

        self._validate_records(dicts)
        selected = []
        for name in selected_dbs:
            if name in self.config.collection_names and name not in selected:
                selected.append(name)
        if not selected:
            raise HTTPException(
                400,
                f"至少选择一个有效的数据库，可用: {', '.join(self.config.collection_names)}",
            )

        image_result = await self.files.upload_images(
            [f for f in files if (f.content_type or "").startswith("image/")]
        )
        doc_result = await self.files.upload_documents(doc_files)
        image_url_list = image_result.get("image_paths", [])
        file_url_list = doc_result.get("document_paths", [])

        review_records = []
        for record in dicts:
            for coll_name in selected:
                review_records.append(
                    {
                        "id": str(uuid.uuid4()),
                        "timestamp": datetime.now(self.config.beijing_tz).isoformat(),
                        "selected_dbs": [coll_name],
                        "source_collection": coll_name,
                        "uploader": uploader,
                        "data": {
                            "type": record.get("type", ""),
                            "object": record.get("object", ""),
                            "purpose": record.get("purpose", ""),
                            "customer_type": record.get("customer_type", ""),
                            "keyword": record.get("keyword", ""),
                            "problem": record.get("problem", []),
                            "web_links": record.get("web_links", []),
                            "reply_logic": record.get("reply_logic", ""),
                            "feature_explanation": record.get("feature_explanation", ""),
                            "example": record.get("example", ""),
                            "notes": record.get("notes", ""),
                            "image_url": image_url_list,
                            "file_url": file_url_list,
                        },
                    }
                )

        timestamp = datetime.now(self.config.beijing_tz).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{uploader}_{timestamp}.json"
        review_file = os.path.join(self.config.review_dir, filename)
        self._save_json(review_file, review_records)

        if rejected_id:
            self._delete_rejected_by_id(uploader=uploader, record_id=rejected_id)

        return {"status": "pending_review", "message": "已提交审核，被拒记录已自动清除"}

    def _delete_rejected_by_id(self, uploader: str, record_id: str):
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return
        records = self._load_json(rejected_file, [])
        cleaned = [r for r in records if str(r.get("id")) != str(record_id)]
        if cleaned:
            self._save_json(rejected_file, cleaned)
        else:
            os.remove(rejected_file)

    def get_rejected_records(self, uploader: str) -> dict:
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return {"rejected": []}
        return {"rejected": self._load_json(rejected_file, [])}

    def delete_rejected_record(self, current_user: str, uploader: str, record_id: str):
        current = self.auth.get_user_from_db(current_user)
        is_admin = (current or {}).get("role") == "admin"
        if current_user != uploader and not is_admin:
            raise HTTPException(status_code=403, detail="无权删除他人被拒记录")

        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return {"success": True, "message": "记录已不存在"}

        records = self._load_json(rejected_file, [])
        cleaned = [r for r in records if str(r.get("id")) != str(record_id)]
        if len(cleaned) == len(records):
            return {"success": False, "message": "记录未找到"}
        if cleaned:
            self._save_json(rejected_file, cleaned)
        else:
            os.remove(rejected_file)
        return {"success": True, "message": "已删除该条被拒记录"}

    def get_rejected_record(self, current_user: str, uploader: str, record_id: str):
        user = self.auth.get_user_from_db(current_user)
        if current_user != uploader and (user or {}).get("role") != "admin":
            raise HTTPException(status_code=403, detail="只能编辑自己的被拒记录")

        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            raise HTTPException(status_code=404, detail="记录不存在")
        records = self._load_json(rejected_file, [])
        for rec in records:
            if str(rec.get("id")) == str(record_id):
                return rec
        raise HTTPException(status_code=404, detail="记录未找到")

    async def resubmit_rejected(
        self,
        current_user: str,
        old_record_id: str,
        uploader: str,
        selected_dbs: list[str],
        record_data: str,
        keep_image_urls: list[str],
        keep_file_urls: list[str],
        new_images: list[UploadFile],
        new_docs: list[UploadFile],
    ):
        user = self.auth.get_user_from_db(current_user)
        is_admin = (user or {}).get("role") == "admin"
        if current_user != uploader and not is_admin:
            raise HTTPException(status_code=403, detail="只能修改自己的被拒记录")

        try:
            new_data = json.loads(record_data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="record_data 不是有效JSON")

        image_result = await self.files.upload_images(new_images)
        doc_result = await self.files.upload_documents(new_docs)
        final_image_urls = list(keep_image_urls) + image_result.get("image_paths", [])
        final_file_urls = list(keep_file_urls) + doc_result.get("document_paths", [])

        selected = []
        for db in selected_dbs:
            if db in self.config.collection_names and db not in selected:
                selected.append(db)
        if not selected:
            raise HTTPException(status_code=400, detail="请至少选择一个有效目标数据库")

        final_records = []
        for coll_name in selected:
            final_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now(self.config.beijing_tz).isoformat(),
                    "selected_dbs": [coll_name],
                    "source_collection": coll_name,
                    "uploader": current_user,
                    "data": {
                        "type": new_data.get("type", ""),
                        "object": new_data.get("object", ""),
                        "purpose": new_data.get("purpose", ""),
                        "customer_type": new_data.get("customer_type", ""),
                        "keyword": new_data.get("keyword", ""),
                        "problem": new_data.get("problem", []),
                        "web_links": new_data.get("web_links", []),
                        "reply_logic": new_data.get("reply_logic", ""),
                        "feature_explanation": new_data.get("feature_explanation", ""),
                        "example": new_data.get("example", ""),
                        "notes": new_data.get("notes", ""),
                        "image_url": final_image_urls,
                        "file_url": final_file_urls,
                    },
                }
            )

        timestamp = datetime.now(self.config.beijing_tz).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{current_user}_{timestamp}_resubmit.json"
        self._save_json(os.path.join(self.config.review_dir, filename), final_records)
        self._delete_rejected_by_id(uploader=uploader, record_id=old_record_id)

        return {
            "status": "success",
            "message": "修改成功，已重新提交审核，原被拒记录已清除",
            "new_pending_file": filename,
        }
