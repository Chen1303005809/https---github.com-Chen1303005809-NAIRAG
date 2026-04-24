# -*- coding: utf-8 -*-
# 文件名: portal.py  （直接覆盖原文件）
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import jwt
import sqlite3
from passlib.context import CryptContext
import os

app = FastAPI(title="RAG 系统统一登录门户（已接入 users.db）")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 挂载 static（图片、上传界面等）
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "portal_templates"))

# ============ 关键：接入 users.db ============
DB_PATH = "/home/RohonDev1/naiRAG/users.db"   # ← 和其他服务完全一致！
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_from_db(username: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT username, password_hash, role FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"username": row["username"], "password_hash": row["password_hash"], "role": row["role"]}
        return None
    except Exception as e:
        print(f"【门户】数据库连接失败: {e}")
        return None

# ============ 统一密钥（必须和两个后端完全一致！）============
FASTAPI_SECRET = "your-secret-key-change-in-production"          # 上传端用的
FLASK_SECRET   = "your_jwt_secret_key_change_in_production_!@#"  # 管理端用的
ALGORITHM = "HS256"

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.get_template("login.html").render({"request": request})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_user_from_db(username)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")

    # 同时生成两个后端都能吃的 token
    fastapi_token = jwt.encode({
        "sub": username,
        "username": username,
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, FASTAPI_SECRET, algorithm=ALGORITHM)

    flask_token = jwt.encode({
        "username": username,
        "role": user["role"],        # 管理端也需要 role
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, FLASK_SECRET, algorithm=ALGORITHM)

    html = f"""
    <!DOCTYPE html><html><body><script>
    localStorage.setItem('authToken', '{fastapi_token}');     // 上传端用
    localStorage.setItem('flaskToken', '{flask_token}');      // 管理端用
    localStorage.setItem('authUsername', '{username}');
    localStorage.setItem('authRole', '{user["role"]}');
    alert('登录成功！角色：{user["role"]}');
    location.href = '/home';
    </script></body></html>
    """
    return HTMLResponse(html)

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    return templates.get_template("home.html").render({"request": request})

@app.get("/logout")
async def logout():
    return HTMLResponse("<script>localStorage.clear();alert('已登出');location.href='/';</script>")

if __name__ == "__main__":
    import uvicorn
    print("RAG 统一登录门户已启动 → http://192.168.1.100:8000")
    print("已接入 users.db，所有账号统一管理！")
    uvicorn.run(app, host="0.0.0.0", port=8000)