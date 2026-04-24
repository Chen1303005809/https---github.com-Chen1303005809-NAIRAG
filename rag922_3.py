# -*- coding: utf-8 -*-
import os
import numpy as np  # 🚨 新增：用于向量归一化
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List, Dict
import io
from PIL import Image
import logging
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 初始化 FastAPI 应用
app = FastAPI(title="RAG 服务 (支持OCR查询)")

# 挂载静态目录
static_dir = os.path.join(BASE_DIR, 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 挂载图片目录（确保与上传时保存路径一致）
images_dir = os.path.join(BASE_DIR, 'static', 'images')
documents_dir = os.path.join(BASE_DIR, 'static', 'documents')
os.makedirs(images_dir, exist_ok=True)
os.makedirs(documents_dir, exist_ok=True)

app.mount("/images", StaticFiles(directory=images_dir), name="images")
app.mount("/documents", StaticFiles(directory=documents_dir), name="documents")

# OCR 引擎初始化
from paddleocr import PaddleOCR
ocr_engine = PaddleOCR(
    lang="ch",
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu"
)

# 连接 Milvus
from pymilvus import connections, Collection
from utils.search_engine import MilvusSearchEngine
connections.connect("default", host="127.0.0.1", port="19530")

# ✅ 修正拼写错误：beg → bge
COLLECTION_NAMES = [
    "rag_bge_m3_structured_v4_1",
    "rag_bge_m3_structured_v4_2",
    "rag_bge_m3_structured_v4_3",
    "rag_bge_m3_structured_v4_4",
    "rag_bge_m3_structured_v4_5",
    "TEST"
]

# 加载已有集合
collections = {}
for name in COLLECTION_NAMES:
    try:
        collection = Collection(name)
        collections[name] = collection
        collection.load()
        logger.info(f"✅ 成功加载集合: {name}")
    except Exception as e:
        logger.error(f"❌ 加载集合 {name} 失败：{str(e)}")
        continue

# 初始化 MilvusSearchEngine 实例
search_engine = MilvusSearchEngine(
    milvus_uri="http://127.0.0.1:19530"
)

async def extract_query_from_images(files: List[UploadFile]) -> str:
    """从图片中提取文字（仅用于查询）"""
    ocr_texts: List[str] = []
    for file in files:
        if not file.content_type.startswith("image/"):
            continue
        try:
            image_bytes = await file.read()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            np_img = np.array(img)
            results = ocr_engine.predict(np_img)
            logger.info(f"OCR结果：{results}")
            for res in results:
                texts = res.get("rec_texts", [])
                scores = res.get("rec_scores", [])
                for text, confidence in zip(texts, scores):
                    if confidence > 0.5:
                        ocr_texts.append(text.strip())
        except Exception as e:
            logger.error(f"处理文件 {file.filename} 时出错：{str(e)}")
            continue
    image_text = "\n".join(ocr_texts) if ocr_texts else ""
    logger.info(f"提取的文字：{image_text}")
    return image_text

# 使用 MilvusSearchEngine 进行嵌入生成，不再需要单独的 bge_m3_embedding 函数

@app.post("/query")
async def handle_query(
    session_id: str = Form(...),
    query: Optional[str] = Form(None),
    selected_dbs: str = Form(default=""),
    files: List[UploadFile] = File(default=[])
):
    logger.info(f"Received: session_id={session_id}, query={query}, selected_dbs={selected_dbs}, files={len(files)}")

    # 清空历史
    if query and query.strip().lower() == "clear":
        return JSONResponse({
            "answer": "历史上下文已清空",
            "text_results": [],
            "image_results": []
        })

    # 提取图片文字
    image_text = await extract_query_from_images(files)
    logger.info(f"Extracted image text: {image_text}")

    # 构建最终查询
    parts = []
    if query and query.strip():
        parts.append(query.strip())
    if image_text:
        parts.append(f"图片内容：{image_text}")
    if not parts and not files:
        raise HTTPException(400, detail="需要输入文字或图片")
    final_query = "\n".join(parts)
    logger.info(f"Final query: {final_query}")

    # 解析选中的数据库
    selected_collections = [name.strip() for name in selected_dbs.split(",") if name.strip() in COLLECTION_NAMES]
    if not selected_collections:
        logger.warning("selected_dbs 为空，使用所有可用集合")
        selected_collections = [name for name in COLLECTION_NAMES if name in collections]
    logger.info(f"Selected collections: {selected_collections}")

    # 使用 MilvusSearchEngine 进行检索
    text_hits = []
    image_hits = []
    
    for coll_name in selected_collections:
        if coll_name not in collections:
            logger.warning(f"集合 {coll_name} 未加载，跳过")
            continue
        
        # 检索文本向量
        try:
            results = search_engine.search_rag(
                collection_name=coll_name,
                query=final_query,
                embedding_field="text_embedding",
                top_k=50
            )
            
            for hit in results:
                raw_score = hit.get("score", 0.0)
                logger.info(f"文本余弦相似度: {raw_score:.4f}")
                normalized_percent = max(0.0, raw_score) * 100
                rounded_percent = round(normalized_percent, 2)

                field_text = hit.get("field_text", "")
                field_type = hit.get("field_type", "")
                file_url = hit.get("file_url", "N/A")
                chunk_id = hit.get("chunk_id", 0)
                doc_id = hit.get("doc_id", "")
                
                text_hits.append({
                    "score": rounded_percent,
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "field_type": field_type,
                    "field_text": field_text,
                    "file_url": file_url,
                    "media_type": "text"
                })
        except Exception as e:
            logger.error(f"搜索集合 {coll_name} 文本向量失败：{str(e)}")
            
        # 检索图像向量
        try:
            results = search_engine.search_rag(
                collection_name=coll_name,
                query=final_query,
                embedding_field="vl_embedding",
                top_k=5
            )
            
            for hit in results:
                raw_score = hit.get("score", 0.0)
                logger.info(f"图像余弦相似度: {raw_score:.4f}")
                normalized_percent = max(0.0, raw_score) * 100
                rounded_percent = round(normalized_percent, 2)

                field_text = hit.get("field_text", "")
                field_type = hit.get("field_type", "")
                file_url = hit.get("file_url", "N/A")
                chunk_id = hit.get("chunk_id", 0)
                doc_id = hit.get("doc_id", "")
                
                image_hits.append({
                    "score": rounded_percent,
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "field_type": field_type,
                    "field_text": field_text,
                    "file_url": file_url,
                    "media_type": "image"
                })
        except Exception as e:
            logger.error(f"搜索集合 {coll_name} 图像向量失败：{str(e)}")

    # 分别去重文本和图像结果
    def deduplicate_hits(hits):
        seen = set()
        unique = []
        for hit in hits:
            identifier = f"{hit.get('doc_id', '')}_{hit.get('chunk_id', '')}"
            if identifier not in seen:
                seen.add(identifier)
                unique.append(hit)
        return unique

    text_hits = deduplicate_hits(text_hits)
    image_hits = deduplicate_hits(image_hits)
    
    # 过滤低分数结果
    score_threshold = 30.0  # 设置分数阈值
    filtered_text_hits = [hit for hit in text_hits if hit["score"] >= score_threshold]
    filtered_image_hits = [hit for hit in image_hits if hit["score"] >= score_threshold]
    
    # 分别排序
    filtered_text_hits.sort(key=lambda x: x["score"], reverse=True)
    filtered_image_hits.sort(key=lambda x: x["score"], reverse=True)
    
    # 处理 file_url 路径转换
    def process_file_urls(hits):
        for hit in hits:
            file_url = hit.get("file_url", "")
            if file_url and file_url != "N/A":
                if isinstance(file_url, list):
                    processed_urls = []
                    for url in file_url:
                        if url and '/home/RohonDev1/naiRAG/' in url:
                            processed_urls.append(url.replace('/home/RohonDev1/naiRAG/', '/static/'))
                        else:
                            processed_urls.append(url)
                    hit["file_url"] = processed_urls
                elif isinstance(file_url, str) and '/home/RohonDev1/naiRAG/' in file_url:
                    hit["file_url"] = file_url.replace('/home/RohonDev1/naiRAG/', '/static/')
        return hits
    
    top_text_results = process_file_urls(filtered_text_hits[:50])
    top_image_results = process_file_urls(filtered_image_hits[:50])

    # 生成综合答案
    answer_parts = []
    
    # 添加文本结果
    if top_text_results:
        answer_parts.append("【文本匹配结果】")
        for i, result in enumerate(top_text_results[:3]):
            field_text = result.get('field_text', '')
            field_type = result.get('field_type', '')
            score = result.get('score', 0)
            part = f"  {i+1}. ({field_type}) {field_text[:100]} [相似度: {score}%]"
            
            file_url = result.get("file_url", [])
            if file_url and isinstance(file_url, list) and len(file_url) > 0:
                for url in file_url:
                    if url:
                        filename = url.split('/')[-1]
                        if '/home/RohonDev1/naiRAG/' in url:
                            url = url.replace('/home/RohonDev1/naiRAG/', '/static/')
                        doc_link = f"[📎{filename}]({url})"
                        part += f" {doc_link}"
            
            answer_parts.append(part)
    
    # 添加图像结果
    if top_image_results:
        answer_parts.append("\n【图像匹配结果】")
        for i, result in enumerate(top_image_results[:3]):
            field_text = result.get('field_text', '')
            field_type = result.get('field_type', '')
            score = result.get('score', 0)
            part = f"  {i+1}. ({field_type}) 图像文件 [相似度: {score}%]"
            
            file_url = result.get("file_url", [])
            if file_url and isinstance(file_url, list) and len(file_url) > 0:
                for url in file_url:
                    if url:
                        filename = url.split('/')[-1]
                        if '/home/RohonDev1/naiRAG/' in url:
                            url = url.replace('/home/RohonDev1/naiRAG/', '/static/')
                        doc_link = f"[🖼️{filename}]({url})"
                        part += f" {doc_link}"
            
            answer_parts.append(part)
    
    final_answer = "\n".join(answer_parts) if answer_parts else "未找到相关答案"

    return JSONResponse({
        "answer": final_answer,
        "query": final_query,
        "extracted_text": image_text,
        "text_results": top_text_results,
        "image_results": top_image_results
    })

@app.get("/")
async def serve_front():
    html_path = os.path.join(static_dir, 'chat922_2.html')
    if os.path.exists(html_path):
        return FileResponse(html_path)
    else:
        return {"message": "前端页面未找到，请确保 chat922_2.html 存在于 static 目录"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 服务启动中...")
    print(f"📁 静态文件目录: {static_dir}")
    print(f"🖼️ 图片目录: {images_dir}")
    print(f"📄 文档目录: {documents_dir}")
    print(f"🔗 访问地址: http://localhost:8005")
    uvicorn.run(app, host="0.0.0.0", port=8005)
