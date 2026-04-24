# -*- coding: utf-8 -*-
import json
import logging
import os
from datetime import datetime
from typing import Any

from flask import request

from .config import AdminConfig



def build_logger(config: AdminConfig) -> logging.Logger:
    os.makedirs(os.path.dirname(config.app_log_file), exist_ok=True)
    logger = logging.getLogger("milvus_admin")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(config.app_log_file)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class OperationLogService:
    def __init__(self, config: AdminConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        if not os.path.exists(self.config.operation_log_file):
            with open(self.config.operation_log_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _read_logs(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.config.operation_log_file):
            return []
        try:
            with open(self.config.operation_log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_logs(self, logs: list[dict[str, Any]]):
        with open(self.config.operation_log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def append(self, data: dict[str, Any]):
        try:
            logs = self._read_logs()
            entry = {
                "id": len(logs) + 1,
                "timestamp": data.get("operation_time", datetime.now().isoformat()),
                "user": getattr(request, "current_user", data.get("user", "system")),
                "type": data.get("type", "operation"),
                "collection": data.get("collection", ""),
                "record_id": data.get("record_id", None),
                "record_ids": data.get("record_ids", []),
                "details": data.get("details", ""),
            }
            logs.append(entry)
            self._write_logs(logs[-1000:])
            self.logger.info("📝 已记录操作日志: %s", entry)
        except Exception as exc:
            self.logger.error("❌ 记录日志失败: %s", exc)

    def list_all(self) -> list[dict[str, Any]]:
        return self._read_logs()
