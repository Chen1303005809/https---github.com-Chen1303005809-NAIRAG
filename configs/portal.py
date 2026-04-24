# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass

from .common import ROOT_DIR, env


@dataclass(frozen=True)
class PortalConfig:
    base_dir: str
    static_dir: str
    templates_dir: str
    db_path: str
    fastapi_secret: str
    flask_secret: str
    algorithm: str = "HS256"


def load_config() -> PortalConfig:
    default_db = os.path.join(ROOT_DIR, "users.db")
    return PortalConfig(
        base_dir=ROOT_DIR,
        static_dir=os.path.join(ROOT_DIR, "static"),
        templates_dir=os.path.join(ROOT_DIR, "web", "portal"),
        db_path=env("USERS_DB_PATH", default_db),
        fastapi_secret=env("FASTAPI_SECRET", "your-secret-key-change-in-production"),
        flask_secret=env("FLASK_SECRET", "your_jwt_secret_key_change_in_production_!@#"),
    )

