# -*- coding: utf-8 -*-
from rag_service.app_factory import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("🚀 服务启动中...")
    print("🔗 访问地址: http://localhost:8005")
    uvicorn.run(app, host="0.0.0.0", port=8005)
