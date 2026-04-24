# -*- coding: utf-8 -*-
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import PortalAuthService
from .config import load_config


def _login_success_html(username: str, role: str, fastapi_token: str, flask_token: str) -> str:
    return f"""
    <!DOCTYPE html><html><body><script>
    localStorage.setItem('authToken', '{fastapi_token}');
    localStorage.setItem('flaskToken', '{flask_token}');
    localStorage.setItem('authUsername', '{username}');
    localStorage.setItem('authRole', '{role}');
    alert('登录成功！角色：{role}');
    location.href = '/home';
    </script></body></html>
    """



def create_app() -> FastAPI:
    config = load_config()
    auth = PortalAuthService(config)

    app = FastAPI(title="RAG 系统统一登录门户（已接入 users.db）")
    app.mount("/static", StaticFiles(directory=config.static_dir), name="static")
    templates = Jinja2Templates(directory=config.templates_dir)

    @app.get("/", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.get_template("login.html").render({"request": request})

    @app.post("/login")
    async def login(username: str = Form(...), password: str = Form(...)):
        user = auth.verify_user(username, password)
        if not user:
            raise HTTPException(401, "用户名或密码错误")
        fastapi_token, flask_token = auth.build_tokens(user)
        return HTMLResponse(
            _login_success_html(
                username=user["username"],
                role=user["role"],
                fastapi_token=fastapi_token,
                flask_token=flask_token,
            )
        )

    @app.get("/home", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.get_template("home.html").render({"request": request})

    @app.get("/logout")
    async def logout():
        return HTMLResponse("<script>localStorage.clear();alert('已登出');location.href='/';</script>")

    return app
