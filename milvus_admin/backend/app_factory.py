# -*- coding: utf-8 -*-
from flask import Flask
from pymilvus import connections
from pymilvus.exceptions import ConnectionConfigException

from .auth import AdminAuth
from .config import load_config
from .data_routes import bp as data_bp
from .logging_utils import OperationLogService, build_logger
from .public_routes import bp as public_bp
from .review_routes import bp as review_bp
from .services import Services
from .upload_routes import bp as upload_bp
from .user_routes import bp as user_bp



def create_app() -> Flask:
    config = load_config()
    logger = build_logger(config)
    auth = AdminAuth(config, logger)
    op_log = OperationLogService(config, logger)

    try:
        connections.connect(alias="default", host=config.milvus_host, port=config.milvus_port)
    except ConnectionConfigException:
        # unified_app 下可能已由其他子应用初始化 default 连接，这里直接复用已有连接
        logger.warning(
            "Milvus default alias 已存在且配置不一致，复用已建立连接。"
            "建议统一设置环境变量 MILVUS_HOST/MILVUS_PORT。"
        )

    app = Flask(__name__, static_folder=config.static_root, template_folder=".")
    app.extensions["services"] = Services(config=config, logger=logger, auth=auth, op_log=op_log)

    app.register_blueprint(public_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(user_bp)
    return app
