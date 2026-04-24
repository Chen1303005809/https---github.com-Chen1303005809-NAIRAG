# -*- coding: utf-8 -*-
from unified_app import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("RAG 统一服务已启动 → http://127.0.0.1:8000")
    print("门户: / | 采集端: /upload/ | 检索端: /search/ | 管理端: /admin/admin_dashboard.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
