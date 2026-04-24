# -*- coding: utf-8 -*-
from collections import defaultdict
from typing import Any


def normalize_score(raw_score: float) -> float:
    return round(max(0.0, raw_score) * 100, 2)


def _is_invalid_url(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.upper() in {"N/A", "NA", "NONE", "NULL"}


def _normalize_single_url(value: str, base_dir: str) -> str:
    if value.startswith(f"{base_dir}/static/"):
        value = value.replace(f"{base_dir}/static/", "/static/")
    elif value.startswith(base_dir + "/"):
        value = value.replace(base_dir + "/", "/")

    # 兼容历史脏数据：/static/static/xxx -> /static/xxx
    while "/static/static/" in value:
        value = value.replace("/static/static/", "/static/")
    return value



def normalize_urls(file_url: Any, base_dir: str) -> list[str]:
    if _is_invalid_url(file_url):
        return []
    values = file_url if isinstance(file_url, list) else [file_url]
    processed: list[str] = []

    for value in values:
        if _is_invalid_url(value):
            continue
        if isinstance(value, str) and ";" in value:
            parts = [p.strip() for p in value.split(";") if p.strip() and not _is_invalid_url(p)]
        else:
            parts = [value]

        for part in parts:
            if _is_invalid_url(part):
                continue
            if isinstance(part, str):
                normalized = _normalize_single_url(part, base_dir)
                if normalized not in processed:
                    processed.append(normalized)
    return processed



def build_hit(raw: dict, media_type: str, base_dir: str) -> dict:
    return {
        "score": normalize_score(raw.get("score", 0.0)),
        "chunk_id": raw.get("chunk_id", 0),
        "doc_id": raw.get("doc_id", ""),
        "field_type": raw.get("field_type", ""),
        "field_text": raw.get("field_text", ""),
        "file_url": normalize_urls(raw.get("file_url", ""), base_dir),
        "media_type": media_type,
    }



def deduplicate_hits(hits: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for hit in hits:
        identifier = f"{hit.get('doc_id', '')}_{hit.get('chunk_id', '')}_{hit.get('media_type', '')}"
        if identifier not in seen:
            seen.add(identifier)
            unique.append(hit)
    return unique



def filter_and_sort(hits: list[dict], score_threshold: float = 30.0) -> list[dict]:
    filtered = [hit for hit in hits if hit.get("score", 0.0) >= score_threshold]
    filtered.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return filtered



def group_hits_by_docid(hits: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for hit in hits:
        doc_id = hit.get("doc_id") or "UNKNOWN_DOC"
        grouped[doc_id].append(hit)

    docs = []
    for doc_id, chunks in grouped.items():
        chunks.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        field_types = sorted({c.get("field_type", "") for c in chunks if c.get("field_type")})
        files = []
        for chunk in chunks:
            for url in chunk.get("file_url", []):
                if url and url not in files:
                    files.append(url)

        docs.append(
            {
                "doc_id": doc_id,
                "best_score": chunks[0].get("score", 0.0),
                "chunk_count": len(chunks),
                "field_types": field_types,
                "file_urls": files,
                "chunks": chunks,
            }
        )

    docs.sort(key=lambda x: x.get("best_score", 0.0), reverse=True)
    return docs



def build_answer(text_results: list[dict], image_results: list[dict]) -> str:
    answer_parts = []
    if text_results:
        answer_parts.append("【文本匹配】")
        for i, result in enumerate(text_results[:3]):
            field_type = result.get("field_type") or "text"
            field_text = (result.get("field_text") or "").strip().replace("\n", " ")
            score = result.get("score", 0)
            part = (
                f"{i+1}. 类型: {field_type} | 相似度: {score}%"
            )
            if field_text:
                part += f" | 内容: {field_text[:90]}"
            file_names = [url.split("/")[-1] for url in result.get("file_url", []) if url]
            if file_names:
                part += f" | 附件: {', '.join(file_names[:2])}"
            answer_parts.append(part)

    if image_results:
        answer_parts.append("\n【图像匹配】")
        for i, result in enumerate(image_results[:3]):
            score = result.get("score", 0)
            part = f"{i+1}. 图像匹配 | 相似度: {score}%"
            file_names = [url.split("/")[-1] for url in result.get("file_url", []) if url]
            if file_names:
                part += f" | 文件: {', '.join(file_names[:3])}"
            answer_parts.append(part)

    return "\n".join(answer_parts) if answer_parts else "未找到相关答案"
