# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass
from datetime import timezone, timedelta


@dataclass(frozen=True)
class UploadConfig:
    base_dir: str
    static_dir: str
    options_file: str
    review_dir: str
    rejected_dir: str
    images_dir: str
    documents_dir: str
    db_path: str
    log_file_path: str
    secret_key: str
    algorithm: str
    beijing_tz: timezone
    collection_names: list[str]


DEFAULT_OPTIONS = {
    "type": ["解释概念", "操作步骤", "故障排查", "权限说明", "数据查询"],
    "object": ["净头寸", "订单管理", "用户权限", "报表导出", "风控设置"],
    "purpose": ["用户咨询", "内部培训", "系统帮助", "客户支持", "审计合规"],
    "customer_type": ["个人客户", "机构客户", "内部员工", "合作伙伴", "系统管理员"],
}


def load_config() -> UploadConfig:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    review_dir = os.path.join(base_dir, "review_pending")
    rejected_dir = os.path.join(review_dir, "rejected")
    static_dir = os.path.join(base_dir, "static")
    db_path = os.getenv("USERS_DB_PATH", os.path.join(base_dir, "users.db"))
    log_file = os.getenv("UPLOAD_LOG_PATH", os.path.join(base_dir, "upload.log"))
    cfg = UploadConfig(
        base_dir=base_dir,
        static_dir=static_dir,
        options_file=os.path.join(static_dir, "rag_options.json"),
        review_dir=review_dir,
        rejected_dir=rejected_dir,
        images_dir=os.path.join(static_dir, "images"),
        documents_dir=os.path.join(static_dir, "documents"),
        db_path=db_path,
        log_file_path=log_file,
        secret_key=os.getenv("SECRET_KEY", "your-secret-key-change-in-production"),
        algorithm="HS256",
        beijing_tz=timezone(timedelta(hours=8)),
        collection_names=[
            "rag_bge_m3_structured_v4_1",
            "rag_bge_m3_structured_v4_2",
            "rag_bge_m3_structured_v4_3",
            "rag_bge_m3_structured_v4_4",
            "rag_bge_m3_structured_v4_5",
            "TEST",
        ],
    )
    os.makedirs(cfg.review_dir, exist_ok=True)
    os.makedirs(cfg.rejected_dir, exist_ok=True)
    os.makedirs(cfg.images_dir, exist_ok=True)
    os.makedirs(cfg.documents_dir, exist_ok=True)
    os.makedirs(os.path.dirname(cfg.log_file_path), exist_ok=True)
    return cfg
