# -*- coding: utf-8 -*-
from dataclasses import dataclass

from .auth import AdminAuth
from .config import AdminConfig
from .logging_utils import OperationLogService


@dataclass
class Services:
    config: AdminConfig
    logger: any
    auth: AdminAuth
    op_log: OperationLogService



def get_services(app):
    return app.extensions["services"]
