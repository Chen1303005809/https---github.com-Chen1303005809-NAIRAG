# -*- coding: utf-8 -*-
import os


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLLECTION_NAMES = [
    "rag_bge_m3_structured_v4_1",
    "rag_bge_m3_structured_v4_2",
    "rag_bge_m3_structured_v4_3",
    "rag_bge_m3_structured_v4_4",
    "rag_bge_m3_structured_v4_5",
    "TEST",
]


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def ensure_dirs(*paths: str) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)

