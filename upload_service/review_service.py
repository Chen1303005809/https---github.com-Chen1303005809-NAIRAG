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

    def _sort_rejected_records(self, records: list[dict]) -> list[dict]:
        def _ts(rec: dict) -> float:
            raw = str((rec or {}).get("timestamp") or "").strip()
            if not raw:
                return 0.0
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0

        return sorted(records or [], key=_ts, reverse=True)

    @staticmethod
    def _record_target_dbs(record: dict) -> set[str]:
        targets = set()
        source_collection = str((record or {}).get("source_collection") or "").strip()
        if source_collection:
            targets.add(source_collection)
        for db in (record or {}).get("selected_dbs", []) or []:
            clean = str(db or "").strip()
            if clean:
                targets.add(clean)
        return targets

    @staticmethod
    def _comparable_rejected_data(record: dict) -> dict:
        data = dict((record or {}).get("data") or {})
        data.pop("image_url", None)
        data.pop("file_url", None)
        return data

    @staticmethod
    def _find_rejected_record(records: list[dict], record_id: str) -> Optional[dict]:
        for record in records or []:
            if str((record or {}).get("id")) == str(record_id):
                return record
        return None

    @staticmethod
    def _record_batch_id(record: dict) -> str:
        return str(
            (record or {}).get("batch_id")
            or (record or {}).get("submission_id")
            or ""
        ).strip()

    @classmethod
    def _same_batch_rejected_ids(
        cls,
        records: list[dict],
        source_record: dict,
        selected_dbs: list[str],
    ) -> set[str]:
        selected = {str(db or "").strip() for db in selected_dbs if str(db or "").strip()}
        source_batch_id = cls._record_batch_id(source_record)
        source_reason = str((source_record or {}).get("reject_reason") or "").strip()
        source_uploader = str((source_record or {}).get("uploader") or "").strip()
        source_data = cls._comparable_rejected_data(source_record)

        cleanup_ids = set()
        for record in records or []:
            record_id = str((record or {}).get("id") or "").strip()
            if not record_id:
                continue
            if source_uploader and str((record or {}).get("uploader") or "").strip() != source_uploader:
                continue
            if str((record or {}).get("reject_reason") or "").strip() != source_reason:
                continue
            if not source_batch_id or cls._record_batch_id(record) != source_batch_id:
                continue
            if cls._comparable_rejected_data(record) != source_data:
                continue
            if not (cls._record_target_dbs(record) & selected):
                continue
            cleanup_ids.add(record_id)

        source_id = str((source_record or {}).get("id") or "").strip()
        if source_id:
            cleanup_ids.add(source_id)
        return cleanup_ids

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
            batch_id = str(uuid.uuid4())
            for coll_name in selected:
                review_records.append(
                    {
                        "id": str(uuid.uuid4()),
                        "batch_id": batch_id,
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

    def _delete_rejected_by_ids(self, uploader: str, record_ids: set[str]):
        if not record_ids:
            return
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return
        records = self._load_json(rejected_file, [])
        cleaned = [r for r in records if str(r.get("id")) not in record_ids]
        if cleaned:
            self._save_json(rejected_file, cleaned)
        else:
            os.remove(rejected_file)

    def get_rejected_records(self, uploader: str) -> dict:
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return {"rejected": []}
        records = self._load_json(rejected_file, [])
        return {"rejected": self._sort_rejected_records(records)}

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

        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            raise HTTPException(status_code=404, detail="记录不存在")
        rejected_records = self._load_json(rejected_file, [])
        source_rejected = self._find_rejected_record(rejected_records, old_record_id)
        if not source_rejected:
            raise HTTPException(status_code=404, detail="记录未找到，可能已被处理")

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
        batch_id = str(uuid.uuid4())
        for coll_name in selected:
            final_records.append(
                {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
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
        cleanup_ids = self._same_batch_rejected_ids(
            records=rejected_records,
            source_record=source_rejected,
            selected_dbs=selected,
        )
        self._delete_rejected_by_ids(uploader=uploader, record_ids=cleanup_ids)

        return {
            "status": "success",
            "message": "修改成功，已重新提交审核，同批被拒记录已自动清除",
            "new_pending_file": filename,
        }
