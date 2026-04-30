# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass
from datetime import timedelta, timezone

from .common import COLLECTION_NAMES, ROOT_DIR, ensure_dirs, env


@dataclass(frozen=True)
class UploadConfig:
    base_dir: str
    static_dir: str
    web_dir: str
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
    review_dir = env("REVIEW_DIR", os.path.join(ROOT_DIR, "review_pending"))
    rejected_dir = os.path.join(review_dir, "rejected")
    static_dir = os.path.join(ROOT_DIR, "static")
    db_path = env("USERS_DB_PATH", os.path.join(ROOT_DIR, "users.db"))
    log_file = env("UPLOAD_LOG_PATH", os.path.join(ROOT_DIR, "upload.log"))

    cfg = UploadConfig(
        base_dir=ROOT_DIR,
        static_dir=static_dir,
        web_dir=os.path.join(ROOT_DIR, "web", "upload"),
        options_file=os.path.join(static_dir, "rag_options.json"),
        review_dir=review_dir,
        rejected_dir=rejected_dir,
        images_dir=os.path.join(static_dir, "images"),
        documents_dir=os.path.join(static_dir, "documents"),
        db_path=db_path,
        log_file_path=log_file,
        secret_key=env("SECRET_KEY", "your-secret-key-change-in-production"),
        algorithm="HS256",
        beijing_tz=timezone(timedelta(hours=8)),
        collection_names=list(COLLECTION_NAMES),
    )

    ensure_dirs(
        cfg.review_dir,
        cfg.rejected_dir,
        cfg.images_dir,
        cfg.documents_dir,
        os.path.dirname(cfg.log_file_path),
    )
    return cfg
