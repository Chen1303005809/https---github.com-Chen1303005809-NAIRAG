# -*- coding: utf-8 -*-
import logging
import os
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config
from .formatters import (
    build_answer,
    build_hit,
    deduplicate_hits,
    filter_and_sort,
    group_hits_by_docid,
)
from .ocr_service import OCRService
from .search_runtime import SearchRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    config = load_config()
    ocr_service = OCRService()
    runtime = SearchRuntime(config)

    app = FastAPI(title="RAG 服务 (支持OCR查询)")
    app.mount("/static", StaticFiles(directory=config.static_dir), name="static")
    app.mount("/images", StaticFiles(directory=config.images_dir), name="images")
    app.mount("/documents", StaticFiles(directory=config.documents_dir), name="documents")

    @app.post("/query")
    async def handle_query(
        session_id: str = Form(...),
        query: Optional[str] = Form(None),
        selected_dbs: str = Form(default=""),
        files: List[UploadFile] = File(default=[]),
    ):
        logger.info(
            "Received: session_id=%s, query=%s, selected_dbs=%s, files=%s",
            session_id,
            query,
            selected_dbs,
            len(files),
        )

        if query and query.strip().lower() == "clear":
            return JSONResponse({"answer": "历史上下文已清空", "text_results": [], "image_results": []})

        image_text = await ocr_service.extract_query_from_images(files)
        parts = []
        if query and query.strip():
            parts.append(query.strip())
        if image_text:
            parts.append(f"图片内容：{image_text}")
        if not parts and not files:
            raise HTTPException(400, detail="需要输入文字或图片")

        final_query = "\n".join(parts)
        selected_collections = runtime.available_collections(selected_dbs)

        text_hits: list[dict] = []
        image_hits: list[dict] = []
        for coll_name in selected_collections:
            if coll_name not in runtime.collections:
                continue
            try:
                text_results, image_results = runtime.search_collection(coll_name, final_query)
                text_hits.extend(build_hit(hit, "text", config.base_dir, coll_name) for hit in text_results)
                image_hits.extend(build_hit(hit, "image", config.base_dir, coll_name) for hit in image_results)
            except Exception as exc:
                logger.error("搜索集合 %s 失败：%s", coll_name, exc)

        filtered_text_hits = filter_and_sort(
            deduplicate_hits(text_hits),
            score_threshold=config.text_score_threshold,
        )[:50]
        # For image retrieval, keep pure Top-K behavior (no score threshold filtering).
        filtered_image_hits = deduplicate_hits(image_hits)
        filtered_image_hits.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        filtered_image_hits = filtered_image_hits[:50]

        grouped_text_results = group_hits_by_docid(filtered_text_hits)
        grouped_image_results = group_hits_by_docid(filtered_image_hits)
        final_answer = build_answer(filtered_text_hits, filtered_image_hits)

        return JSONResponse(
            {
                "answer": final_answer,
                "query": final_query,
                "extracted_text": image_text,
                "text_results": filtered_text_hits,
                "image_results": filtered_image_hits,
                "grouped_text_results": grouped_text_results,
                "grouped_image_results": grouped_image_results,
            }
        )

    @app.get("/")
    async def serve_front():
        html_path = os.path.join(config.web_dir, "search_dashboard.html")
        if os.path.exists(html_path):
            return FileResponse(html_path)
        return {"message": "前端页面未找到，请确保 search_dashboard.html 存在于 web/search 目录"}

    return app
