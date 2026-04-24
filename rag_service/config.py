# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RagConfig:
    base_dir: str
    static_dir: str
    web_dir: str
    images_dir: str
    documents_dir: str
    milvus_host: str
    milvus_port: str
    collection_names: list[str]



def load_config() -> RagConfig:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static")
    images_dir = os.path.join(static_dir, "images")
    documents_dir = os.path.join(static_dir, "documents")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)
    return RagConfig(
        base_dir=base_dir,
        static_dir=static_dir,
        web_dir=os.path.join(base_dir, "web", "search"),
        images_dir=images_dir,
        documents_dir=documents_dir,
        milvus_host=os.getenv("MILVUS_HOST", "127.0.0.1"),
        milvus_port=os.getenv("MILVUS_PORT", "19530"),
        collection_names=[
            "rag_bge_m3_structured_v4_1",
            "rag_bge_m3_structured_v4_2",
            "rag_bge_m3_structured_v4_3",
            "rag_bge_m3_structured_v4_4",
            "rag_bge_m3_structured_v4_5",
            "TEST",
        ],
    )
