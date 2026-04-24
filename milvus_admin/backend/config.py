# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdminConfig:
    base_dir: str
    static_root: str
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



def load_config() -> AdminConfig:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    static_root = os.path.join(base_dir, "static")
    review_dir = os.getenv("REVIEW_DIR", os.path.join(base_dir, "review_pending"))
    os.makedirs(review_dir, exist_ok=True)
    os.makedirs(os.path.join(review_dir, "rejected"), exist_ok=True)
    os.makedirs(os.path.join(static_root, "images"), exist_ok=True)
    os.makedirs(os.path.join(static_root, "documents"), exist_ok=True)

    return AdminConfig(
        base_dir=base_dir,
        static_root=static_root,
        review_dir=review_dir,
        options_file=os.getenv("RAG_OPTIONS_FILE", os.path.join(static_root, "rag_options.json")),
        users_db_path=os.getenv("USERS_DB_PATH", os.path.join(base_dir, "users.db")),
        operation_log_file=os.path.join(base_dir, "operation_logs.json"),
        app_log_file=os.path.join(base_dir, "milvus_admin", "app.log"),
        jwt_secret=os.getenv("FLASK_SECRET", "your_jwt_secret_key_change_in_production_!@#"),
        jwt_algorithm="HS256",
        jwt_expire_hours=24,
        milvus_host=os.getenv("MILVUS_HOST", "192.168.1.100"),
        milvus_port=os.getenv("MILVUS_PORT", "19530"),
    )
