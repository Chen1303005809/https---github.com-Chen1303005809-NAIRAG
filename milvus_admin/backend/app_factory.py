# -*- coding: utf-8 -*-
from flask import Flask
from pymilvus import connections

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

    connections.connect(host=config.milvus_host, port=config.milvus_port)

    app = Flask(__name__, static_folder=config.static_root, template_folder=".")
    app.extensions["services"] = Services(config=config, logger=logger, auth=auth, op_log=op_log)

    app.register_blueprint(public_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(user_bp)
    return app
