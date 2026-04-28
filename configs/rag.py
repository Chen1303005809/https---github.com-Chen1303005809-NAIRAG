# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass

from .common import COLLECTION_NAMES, ROOT_DIR, ensure_dirs, env


@dataclass(frozen=True)
class RagConfig:
    base_dir: str
    static_dir: str
    web_dir: str
    images_dir: str
    documents_dir: str
    milvus_host: str
    milvus_port: str
    device: str 
    collection_names: list[str]


def load_config() -> RagConfig:
    static_dir = os.path.join(ROOT_DIR, "static")
    images_dir = os.path.join(static_dir, "images")
    documents_dir = os.path.join(static_dir, "documents")
    ensure_dirs(images_dir, documents_dir)

    return RagConfig(
        base_dir=ROOT_DIR,
        static_dir=static_dir,
        web_dir=os.path.join(ROOT_DIR, "web", "search"),
        images_dir=images_dir,
        documents_dir=documents_dir,
        milvus_host=env("MILVUS_HOST", "127.0.0.1"),
        milvus_port=env("MILVUS_PORT", "19530"),
        collection_names=list(COLLECTION_NAMES),
        device=env("DEVICE", "cuda:1") if os.getenv("CUDA_AVAILABLE", "false").lower() == "true" else "cpu",
    )

