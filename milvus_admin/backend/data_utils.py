# -*- coding: utf-8 -*-
import json
from collections import defaultdict
from typing import Any

import numpy as np


FIELD_MAP = {
    "keyword": "keyword",
    "keywords": "keyword",
    "problem": "problem",
    "question": "problem",
    "reply_logic": "reply_logic",
    "answer_logic": "reply_logic",
    "feature_explanation": "feature_explanation",
    "explanation": "feature_explanation",
    "example": "example",
    "notes": "notes",
}



def parse_file_urls(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                values = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                values = [raw]
        elif ";" in raw:
            values = [part for part in raw.split(";") if part]
        else:
            values = [raw]
    else:
        values = [str(raw)]

    result = []
    for url in values:
        if url and url != "N/A" and url not in result:
            result.append(url)
    return result



def serialize_item(item: dict) -> dict:
    clean_item = {}
    for key, value in item.items():
        if isinstance(value, np.ndarray):
            clean_item[key] = value.tolist()
        else:
            clean_item[key] = value
    clean_item["id"] = str(clean_item.get("id", ""))
    if "updated_at" not in clean_item:
        from datetime import datetime

        clean_item["updated_at"] = datetime.now().isoformat()
    return clean_item



def group_by_doc_id(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        doc_id = row.get("doc_id") or "UNKNOWN_DOC"
        grouped[doc_id].append(row)

    docs = []
    for doc_id, chunks in grouped.items():
        chunks_sorted = sorted(
            chunks,
            key=lambda x: int(x.get("chunk_id") or 0),
        )
        summary = {
            "object": "",
            "type": "",
            "purpose": "",
            "customer_type": "",
            "keyword": "",
            "problem": [],
            "reply_logic": "",
            "feature_explanation": "",
            "example": "",
            "notes": "",
        }
        file_urls = []

        for chunk in chunks_sorted:
            if not summary["type"]:
                summary["type"] = str(chunk.get("type") or "").strip()
            if not summary["object"]:
                summary["object"] = str(chunk.get("object") or "").strip()
            if not summary["purpose"]:
                summary["purpose"] = str(chunk.get("purpose") or "").strip()
            if not summary["customer_type"]:
                summary["customer_type"] = str(chunk.get("customer_type") or "").strip()

            field_type = str(chunk.get("field_type") or "").strip().lower()
            field_text = str(chunk.get("field_text") or "").strip()
            if field_type in FIELD_MAP:
                key = FIELD_MAP[field_type]
                if key == "problem":
                    if field_text:
                        if field_text not in summary["problem"]:
                            summary["problem"].append(field_text)
                elif not summary.get(key) and field_text:
                    summary[key] = field_text

            for url in parse_file_urls(chunk.get("file_url")):
                if url not in file_urls:
                    file_urls.append(url)

        docs.append(
            {
                "doc_id": doc_id,
                "chunk_count": len(chunks_sorted),
                "record_id": chunks_sorted[0].get("id"),
                "summary": summary,
                "file_urls": file_urls,
                "chunks": [
                    {
                        "id": c.get("id"),
                        "chunk_id": c.get("chunk_id"),
                        "field_type": c.get("field_type"),
                        "field_text": c.get("field_text"),
                        "weight": c.get("weight"),
                        "file_url": parse_file_urls(c.get("file_url")),
                    }
                    for c in chunks_sorted
                ],
            }
        )

    docs.sort(key=lambda x: str(x.get("doc_id")))
    return docs
