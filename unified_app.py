# -*- coding: utf-8 -*-
from fastapi.responses import RedirectResponse
from starlette.middleware.wsgi import WSGIMiddleware

from milvus_admin.backend.app_factory import create_app as create_admin_app
from portal_service.app_factory import create_app as create_portal_app
from rag_service.app_factory import create_app as create_search_app
from upload_service.app_factory import create_app as create_upload_app


def create_app():
    app = create_portal_app()

    # 子系统统一挂载：只启动一个进程即可访问全部后端能力
    app.mount("/upload", create_upload_app())
    app.mount("/search", create_search_app())
    app.mount("/admin", WSGIMiddleware(create_admin_app()))

    @app.get("/upload_dashboard.html", include_in_schema=False)
    async def legacy_upload_redirect():
        return RedirectResponse(url="/upload/", status_code=307)

    @app.get("/search_dashboard.html", include_in_schema=False)
    async def legacy_search_redirect():
        return RedirectResponse(url="/search/", status_code=307)

    @app.get("/admin_dashboard.html", include_in_schema=False)
    async def legacy_admin_redirect():
        return RedirectResponse(url="/admin/admin_dashboard.html", status_code=307)

    @app.get("/user_management.html", include_in_schema=False)
    async def legacy_user_mgmt_redirect():
        return RedirectResponse(url="/admin/user_management.html", status_code=307)

    return app
