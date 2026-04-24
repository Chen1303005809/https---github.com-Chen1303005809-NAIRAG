# -*- coding: utf-8 -*-
from collections import defaultdict
from typing import Any


def normalize_score(raw_score: float) -> float:
    return round(max(0.0, raw_score) * 100, 2)



def normalize_urls(file_url: Any, base_dir: str) -> list[str]:
    if not file_url or file_url == "N/A":
        return []
    values = file_url if isinstance(file_url, list) else [file_url]
    processed: list[str] = []

    for value in values:
        if not value:
            continue
        if isinstance(value, str) and ";" in value:
            parts = [p.strip() for p in value.split(";") if p.strip()]
        else:
            parts = [value]

        for part in parts:
            if isinstance(part, str) and part.startswith(base_dir):
                processed.append(part.replace(base_dir + "/", "/static/"))
            elif isinstance(part, str):
                processed.append(part)
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
        answer_parts.append("【文本匹配结果】")
        for i, result in enumerate(text_results[:3]):
            part = (
                f"  {i+1}. ({result.get('field_type', '')}) "
                f"{result.get('field_text', '')[:100]} [相似度: {result.get('score', 0)}%]"
            )
            for url in result.get("file_url", []):
                filename = url.split("/")[-1]
                part += f" [📎{filename}]({url})"
            answer_parts.append(part)

    if image_results:
        answer_parts.append("\n【图像匹配结果】")
        for i, result in enumerate(image_results[:3]):
            part = f"  {i+1}. ({result.get('field_type', '')}) 图像文件 [相似度: {result.get('score', 0)}%]"
            for url in result.get("file_url", []):
                filename = url.split("/")[-1]
                part += f" [🖼️{filename}]({url})"
            answer_parts.append(part)

    return "\n".join(answer_parts) if answer_parts else "未找到相关答案"
