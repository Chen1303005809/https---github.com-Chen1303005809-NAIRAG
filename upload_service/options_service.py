# -*- coding: utf-8 -*-
import json
import os
from typing import List

from fastapi import HTTPException

from .config import DEFAULT_OPTIONS, UploadConfig


class OptionsService:
    def __init__(self, config: UploadConfig):
        self.config = config
        self.options = self.load_options()

    def load_options(self) -> dict:
        if os.path.exists(self.config.options_file):
            try:
                with open(self.config.options_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, values in DEFAULT_OPTIONS.items():
                    if key not in data:
                        data[key] = values
                return data
            except Exception:
                pass
        return DEFAULT_OPTIONS.copy()

    def save_options(self):
        with open(self.config.options_file, "w", encoding="utf-8") as f:
            json.dump(self.options, f, ensure_ascii=False, indent=2)

    def get_options(self) -> dict:
        return self.options

    def update_options(self, category: str, items: List[str]):
        if category not in self.options:
            raise HTTPException(400, "无效分类")
        self.options[category] = [item.strip() for item in items if item.strip()]
        self.save_options()
        return {"status": "success"}
