# -*- coding: utf-8 -*-
import os
import shutil
from typing import List

from fastapi import UploadFile

from .config import UploadConfig


class FileService:
    def __init__(self, config: UploadConfig):
        self.config = config

    async def upload_images(self, files: List[UploadFile]) -> dict:
        image_paths = []
        for img_file in files:
            if not (img_file.content_type or "").startswith("image/"):
                continue
            original_name = img_file.filename
            if not original_name:
                continue
            target_path = os.path.join(self.config.images_dir, original_name)
            if os.path.exists(target_path):
                image_paths.append(f"/static/images/{original_name}")
                continue
            with open(target_path, "wb") as f:
                shutil.copyfileobj(img_file.file, f)
            image_paths.append(f"/static/images/{original_name}")
        return {"image_paths": image_paths}

    async def upload_documents(self, files: List[UploadFile]) -> dict:
        document_paths = []
        allowed_types = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "application/zip",
            "application/x-zip-compressed",
        }
        for doc_file in files:
            if not doc_file.filename:
                continue
            ext_ok = doc_file.filename.lower().endswith((".pdf", ".docx", ".doc", ".zip"))
            type_ok = doc_file.content_type in allowed_types
            if not ext_ok and not type_ok:
                continue

            original_name = doc_file.filename
            target_path = os.path.join(self.config.documents_dir, original_name)
            if os.path.exists(target_path):
                document_paths.append(f"/static/documents/{original_name}")
                continue
            with open(target_path, "wb") as f:
                shutil.copyfileobj(doc_file.file, f)
            document_paths.append(f"/static/documents/{original_name}")
        return {"document_paths": document_paths}
