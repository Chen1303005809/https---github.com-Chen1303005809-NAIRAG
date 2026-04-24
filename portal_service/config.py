# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass


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
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_db = os.path.join(base_dir, "users.db")
    return PortalConfig(
        base_dir=base_dir,
        static_dir=os.path.join(base_dir, "static"),
        templates_dir=os.path.join(base_dir, "web", "portal"),
        db_path=os.getenv("USERS_DB_PATH", default_db),
        fastapi_secret=os.getenv("FASTAPI_SECRET", "your-secret-key-change-in-production"),
        flask_secret=os.getenv("FLASK_SECRET", "your_jwt_secret_key_change_in_production_!@#"),
    )
