# init_users_db.py
import sqlite3
from passlib.context import CryptContext
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 数据库路径（写入项目根目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DB_PATH = os.path.join(PROJECT_ROOT, "users.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',   -- admin / editor / user
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

#创建默认管理员：密码admin123
c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
          ("admin", pwd_context.hash("admin123"), "admin"))


users = [
    ("user1", "user123", "user"),
    ("user2", "user234", "user"),
    ("user3", "user345", "user"),
    ("user4", "user456", "user"),
    ("user5", "user567", "user"),
    ("user6", "user678", "user"),
    ("user7", "user789", "user")    
]

for u in users:
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
              (u[0], pwd_context.hash(u[1]), u[2]))

conn.commit()
conn.close()
print("用户数据库创建成功！ 默认 admin / admin123")
