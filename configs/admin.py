# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass

from .common import COLLECTION_NAMES, ROOT_DIR, ensure_dirs, env


@dataclass(frozen=True)
class AdminConfig:
    base_dir: str
    static_root: str
    web_admin_dir: str
    review_dir: str
    options_file: str
    users_db_path: str
    operation_log_file: str
    app_log_file: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_hours: int
    milvus_host: str
    milvus_port: str
    collection_names: list[str]


def load_config() -> AdminConfig:
    static_root = os.path.join(ROOT_DIR, "static")
    review_dir = env("REVIEW_DIR", os.path.join(ROOT_DIR, "review_pending"))
    ensure_dirs(
        review_dir,
        os.path.join(review_dir, "rejected"),
        os.path.join(static_root, "images"),
        os.path.join(static_root, "documents"),
    )

    return AdminConfig(
        base_dir=ROOT_DIR,
        static_root=static_root,
        web_admin_dir=os.path.join(ROOT_DIR, "web", "admin"),
        review_dir=review_dir,
        options_file=env("RAG_OPTIONS_FILE", os.path.join(static_root, "rag_options.json")),
        users_db_path=env("USERS_DB_PATH", os.path.join(ROOT_DIR, "users.db")),
        operation_log_file=os.path.join(ROOT_DIR, "operation_logs.json"),
        app_log_file=os.path.join(ROOT_DIR, "milvus_admin", "app.log"),
        jwt_secret=env("FLASK_SECRET", "your_jwt_secret_key_change_in_production_!@#"),
        jwt_algorithm="HS256",
        jwt_expire_hours=24,
        milvus_host=env("MILVUS_HOST", "127.0.0.1"),
        milvus_port=env("MILVUS_PORT", "19530"),
        collection_names=list(COLLECTION_NAMES),
    )
