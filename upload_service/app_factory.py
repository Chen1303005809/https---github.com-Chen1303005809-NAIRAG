# -*- coding: utf-8 -*-
from datetime import datetime
from typing import List, Optional

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import UploadAuthService
from .config import load_config
from .file_service import FileService
from .models import LoginRequest
from .options_service import OptionsService
from .review_service import ReviewService


def create_app() -> FastAPI:
    config = load_config()
    auth = UploadAuthService(config)
    files = FileService(config)
    options = OptionsService(config)
    review = ReviewService(config, auth, files)

    app = FastAPI(title="RAG Milvus 服务")
    app.mount("/static", StaticFiles(directory=config.static_dir), name="static")

    @app.post("/login")
    async def login(request: LoginRequest):
        return auth.login(request.username, request.password)

    @app.get("/options")
    async def get_options():
        return options.get_options()

    @app.post("/options/{category}")
    async def update_options(
        category: str,
        items: List[str] = Body(...),
        authorization: str = Header(...),
    ):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "无效认证头")
        user = auth.decode_token(authorization[7:])
        if user["role"] != "admin":
            raise HTTPException(403, "仅管理员可修改选项")
        return options.update_options(category, items)

    @app.post("/upload_images")
    async def upload_images(files_upload: List[UploadFile] = File(default=[])):
        return await files.upload_images(files_upload)

    @app.post("/upload_documents")
    async def upload_documents(files_upload: List[UploadFile] = File(default=[])):
        return await files.upload_documents(files_upload)

    @app.post("/upload_json")
    async def upload_json(
        rejected_id: Optional[str] = Form(None),
        records_json: str = Form(...),
        selected_dbs: List[str] = Form(default=[]),
        files_upload: List[UploadFile] = File(default=[], alias="files"),
        doc_files: List[UploadFile] = File(default=[], alias="doc_files"),
        authorization: Optional[str] = Header(None),
    ):
        uploader = auth.parse_uploader(authorization)
        return await review.submit_upload_json(
            uploader=uploader,
            records_json=records_json,
            selected_dbs=selected_dbs,
            files=files_upload,
            doc_files=doc_files,
            rejected_id=rejected_id,
        )

    @app.get("/rejected_records")
    async def get_rejected_records(authorization: Optional[str] = Header(default=None)):
        uploader = auth.parse_uploader(authorization)
        return review.get_rejected_records(uploader)

    @app.post("/clear_rejected")
    async def clear_rejected(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="未提供认证信息")
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        user = auth.decode_token(token)
        if user.get("role") != "admin":
            return {"status": "warning", "message": "普通用户无权清除被拒记录"}

        rejected_file = f"{config.rejected_dir}/{user['username']}.json"
        import os

        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        return {"status": "cleared"}

    @app.post("/delete_rejected_record")
    async def delete_rejected_record(
        uploader: str = Form(...),
        record_id: str = Form(...),
        authorization: Optional[str] = Header(None),
    ):
        current_user = auth.parse_uploader(authorization)
        return review.delete_rejected_record(current_user, uploader, record_id)

    @app.post("/log")
    async def log_operation(request: dict):
        timestamp = request.get("time", datetime.now(config.beijing_tz).strftime("%Y-%m-%d %H:%M:%S"))
        message = request.get("message", "无内容")
        with open(config.log_file_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        return {"status": "success", "message": "日志已记录"}

    @app.get("/rejected_record/{uploader}/{record_id}")
    async def get_rejected_record(
        uploader: str,
        record_id: str,
        authorization: Optional[str] = Header(None),
    ):
        current_user = auth.parse_uploader(authorization)
        return review.get_rejected_record(current_user, uploader, record_id)

    @app.post("/resubmit_rejected")
    async def resubmit_rejected(
        old_record_id: str = Form(...),
        uploader: str = Form(...),
        selected_dbs: List[str] = Form(...),
        record_data: str = Form(...),
        keep_image_urls: List[str] = Form(default=[]),
        keep_file_urls: List[str] = Form(default=[]),
        new_images: List[UploadFile] = File(default=[]),
        new_docs: List[UploadFile] = File(default=[]),
        authorization: Optional[str] = Header(None),
    ):
        current_user = auth.parse_uploader(authorization)
        return await review.resubmit_rejected(
            current_user=current_user,
            old_record_id=old_record_id,
            uploader=uploader,
            selected_dbs=selected_dbs,
            record_data=record_data,
            keep_image_urls=keep_image_urls,
            keep_file_urls=keep_file_urls,
            new_images=new_images,
            new_docs=new_docs,
        )

    @app.get("/")
    async def index():
        return FileResponse(f"{config.web_dir}/upload_dashboard.html")

    return app
