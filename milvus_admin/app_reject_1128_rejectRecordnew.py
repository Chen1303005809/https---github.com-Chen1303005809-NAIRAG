# -*- coding: utf-8 -*-
from milvus_admin.backend.app_factory import create_app

app = create_app()


if __name__ == '__main__':
    services = app.extensions["services"]
    services.logger.info("🚀 正在启动 Milvus 数据管理后台...")
    services.logger.info("🌐 访问地址: http://192.168.1.100:5000/app_reject_928_2.html")
    services.logger.info("🛑 按 Ctrl+C 停止服务")
    app.run(host='0.0.0.0', port=5000, debug=True)
