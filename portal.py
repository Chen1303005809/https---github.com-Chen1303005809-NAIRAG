# -*- coding: utf-8 -*-
from portal_service.app_factory import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("RAG 统一登录门户已启动 → http://192.168.1.100:8000")
    print("已接入 users.db，所有账号统一管理！")
    uvicorn.run(app, host="0.0.0.0", port=8000)
