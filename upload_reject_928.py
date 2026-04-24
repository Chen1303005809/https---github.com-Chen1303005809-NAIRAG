# -*- coding: utf-8 -*-
import os
import shutil
import json
from typing import Dict, List, Optional
import uuid
import base64
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, Header  # ✅ 新增 Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from passlib.context import CryptContext
from pymilvus import connections, Collection, utility
import ollama
from fastapi import Body

# 初始化应用
app = FastAPI(title="RAG Milvus 服务")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OPTIONS_FILE = os.path.join(BASE_DIR,'static','rag_options.json')
static_dir = os.path.join(BASE_DIR, 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")
REVIEW_DIR = os.path.join(BASE_DIR, 'review_pending')
os.makedirs(REVIEW_DIR, exist_ok=True)
BEIJING_TZ = timezone(timedelta(hours=8))
now_beijing = datetime.now(BEIJING_TZ)
# 在 app 初始化后添加
os.makedirs(os.path.join(REVIEW_DIR, 'rejected'), exist_ok=True)
# 在 upload_reject_928.py 最上面加入
import sqlite3
from passlib.context import CryptContext

DB_PATH = "/home/RohonDev1/naiRAG/users.db"
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
    except:
        pass
    return None


# Milvus 连接和初始化
MILVUS_HOST = '127.0.0.1'
MILVUS_PORT = '19530'
COLLECTION_NAMES = [
    "rag_bge_m3_structured_v4_1",
    "rag_bge_m3_structured_v4_2", 
    "rag_bge_m3_structured_v4_3",
    "rag_bge_m3_structured_v4_4",
    "rag_bge_m3_structured_v4_5",
    "TEST"
]
connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
collections = {}
for name in COLLECTION_NAMES:
    if not utility.has_collection(name):
        raise RuntimeError(f"Milvus collection '{name}' 不存在，请先初始化")
    collections[name] = Collection(name)

# 文件存储目录
images_dir = os.path.join(static_dir, 'images')
documents_dir = os.path.join(static_dir, 'documents')
os.makedirs(images_dir, exist_ok=True)
os.makedirs(documents_dir, exist_ok=True)

# 历史上下文存储
history_store: Dict[str, List] = {}

# 导入现有函数（需确保 rag_ollama_api_616.py 存在）
## from rag_ollama_api_616 import generate_chunk_text, bge_m3_embedding, end_to_end_answer_with_history

# 🔐 认证配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
'''
# 简单用户数据库（生产环境请用数据库）
USERS_DB = {
    "admin": {
        "password_hash": pwd_context.hash("admin123"),  # 默认密码: admin123
        "role": "admin"
    },
    "user1":{
        "password_hash": pwd_context.hash("user123"),
        "role": "user"
    },
    "user2":{
        "password_hash": pwd_context.hash("user234"),
        "role": "user"
    }

}
'''


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_current_user(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="无效凭证")
        return {"username": username, "role": role}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="认证失败")

# 选项存储（内存，重启丢失）
DEFAULT_OPTIONS = {
    "type": ["解释概念", "操作步骤", "故障排查", "权限说明", "数据查询"],
    "object": ["净头寸", "订单管理", "用户权限", "报表导出", "风控设置"],
    "purpose": ["用户咨询", "内部培训", "系统帮助", "客户支持", "审计合规"],
    "customer_type": ["个人客户", "机构客户", "内部员工", "合作伙伴", "系统管理员"]
}

# 从文件加载选项（不存在则创建默认）
def load_options():
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保所有 key 都存在，防止管理员误删
                for k in DEFAULT_OPTIONS:
                    if k not in data:
                        data[k] = DEFAULT_OPTIONS[k]
                return data
        except:
            pass  # 文件损坏就用默认
    return DEFAULT_OPTIONS.copy()

def save_options():
    with open(OPTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(OPTIONS, f, ensure_ascii=False, indent=2)

# 程序启动时加载
OPTIONS = load_options()

# Pydantic 模型
class LoginRequest(BaseModel):
    username: str
    password: str

class Record(BaseModel):
    object: str
    type: str
    purpose: str
    customer_type: str
    reply_logic: str          # 回复逻辑框架
    feature_explanation: str  # 说明功能
    example: str = ""         # 举例说明（选填）
    notes: str = ""           # 注意事项（选填）
    keyword: str = None
    problem: List[str]
    image_url: List[str] = []
    file_url: List[str] = []

class QueryRequest(BaseModel):
    query: str
    session_id: str

# ✅ 登录接口
'''
@app.post("/login")
async def login(request: LoginRequest):
    user = USERS_DB.get(request.username)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    access_token = jwt.encode(
        {
            "sub": request.username,
            "role": user["role"],
            "exp": datetime.utcnow() + timedelta(hours=24)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"]
    }
    '''
@app.post("/login")
async def login(request: LoginRequest):
    user = get_user_from_db(request.username)
    if not user or not pwd_context.verify(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    access_token = jwt.encode({
        "sub": user["username"],
        "role": user["role"],
        "exp": datetime.now(BEIJING_TZ) + timedelta(hours=24)
    }, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"]
    }

# ✅ 获取选项
@app.get("/options")
async def get_options():
    return OPTIONS

# ✅ 更新选项（仅 admin）✅ 修复点：使用 Header(...)
@app.post("/options/{category}")
async def update_options(
    category: str,
    items: List[str] = Body(...),
    authorization: str = Header(...)  # ✅ 关键修复：正确从 Header 读取
):
    # 从 Authorization: Bearer <token> 提取 token
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "无效认证头")
    token = authorization[7:]
    user = get_current_user(token)
    if user["role"] != "admin":
        raise HTTPException(403, "仅管理员可修改选项")
    if category not in OPTIONS:
        raise HTTPException(400, "无效分类")
    OPTIONS[category] = [item.strip() for item in items if item.strip()]
    
    # 保存到磁盘
    save_options()
    return {"status": "success"}

# ✅ 上传图片
@app.post("/upload_images")
async def upload_images(files: List[UploadFile] = File(default=[])):
    image_paths = []
    for img_file in files:
        if not img_file.content_type.startswith('image/'):
            continue

        original_name = img_file.filename
        target_path = os.path.join(images_dir, original_name)

        # 关键：如果同名文件已存在 → 直接复用，不再保存
        if os.path.exists(target_path):
            relative_path = f"/static/images/{original_name}"
            image_paths.append(relative_path)
            continue  # 跳过实际写入

        # 不存在才保存（此时 original_name 一定是唯一的）
        with open(target_path, 'wb') as f:
            shutil.copyfileobj(img_file.file, f)
        relative_path = f"/static/images/{original_name}"
        image_paths.append(relative_path)

    return {"image_paths": image_paths}

# ✅ 上传文档
@app.post("/upload_documents")
async def upload_documents(files: List[UploadFile] = File(default=[])):
    document_paths = []
    for doc_file in files:
        # 支持更多常见文档类型
        allowed_types = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
            'application/zip',
            'application/x-zip-compressed'
        ]
        if doc_file.content_type not in allowed_types and not doc_file.filename.lower().endswith(('.pdf', '.docx', '.doc', '.zip')):
            continue

        original_name = doc_file.filename
        target_path = os.path.join(documents_dir, original_name)

        # 关键：同名文件已存在 → 直接复用
        if os.path.exists(target_path):
            relative_path = f"/static/documents/{original_name}"
            document_paths.append(relative_path)
            continue

        # 不存在才保存（保持原文件名）
        with open(target_path, 'wb') as f:
            shutil.copyfileobj(doc_file.file, f)

        relative_path = f"/static/documents/{original_name}"
        document_paths.append(relative_path)

    return {"document_paths": document_paths}

def get_uploader_from_token(token: str):
    try:
        # 处理Bearer前缀
        if token.startswith("Bearer "):
            token = token[7:]
        
        # 检查token是否为空
        if not token:
            raise ValueError("Token为空")
        
        # 解析token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        
        # 检查用户名是否存在
        if not username:
            raise ValueError("Token中缺少用户名")
            
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的Token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"认证失败: {str(e)}")


# 上传 JSON
@app.post("/upload_json")
async def upload_json(
    rejected_id: Optional[str] = Form(None),
    records_json: str = Form(...),
    selected_dbs: List[str] = Form(default=[]),
    files: List[UploadFile] = File(default=[]),
    doc_files: List[UploadFile] = File(default=[]),
    authorization: Optional[str] = Header(None)
):
    # ✅ 强制检查认证信息
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息，请先登录")
    
    # ✅ 解析token获取用户名，不再使用默认值
    try:
        uploader = get_uploader_from_token(authorization)
        if not uploader or uploader == "anonymous":
            raise HTTPException(status_code=401, detail="无效的认证信息，请重新登录")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"认证失败: {str(e)}")
    
    try:
        parsed = json.loads(records_json)
        dicts = [parsed] if isinstance(parsed, dict) else parsed
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"无效的 JSON 数据: {str(e)}")

    if not dicts:
        raise HTTPException(400, "JSON 列表不能为空")
    if not isinstance(dicts, list):
        raise HTTPException(400, "JSON 数据必须是数组或单个对象")

    # 校验必填字段（新结构）
    for d in dicts:
        if not d.get('reply_logic', '').strip():
            raise HTTPException(400, "每条记录必须包含非空 '回复逻辑框架'")
        if not d.get('feature_explanation', '').strip():
            raise HTTPException(400, "每条记录必须包含非空 '说明功能'")
        if 'problem' in d and not isinstance(d['problem'], list):
            raise HTTPException(400, f"'problem' 必须是字符串数组")

    selected_collections = [name for name in selected_dbs if name in COLLECTION_NAMES]
    if not selected_collections:
        raise HTTPException(400, f"至少选择一个有效的数据库，可用: {', '.join(COLLECTION_NAMES)}")

        # 彻底删除重复保存逻辑，改用已修复的独立上传接口（保留原始文件名）
    image_url_list = []
    file_url_list  = []

    if files:
        result = await upload_images(files=[f for f in files if f.content_type and f.content_type.startswith('image/')])
        image_url_list = result.get("image_paths", [])

    if doc_files:
        result = await upload_documents(files=doc_files)
        file_url_list = result.get("document_paths", [])



    # ✅ 使用解析出的用户名，不再有默认值
    uploader = uploader  # 确保使用解析出的用户名

    # ✅ 关键变更：不生成嵌入！不写入 Milvus！
    review_records = []
    for d in dicts:
        record = {
            "id": str(uuid.uuid4()),  # 审核ID
            "timestamp": datetime.now(BEIJING_TZ).isoformat(),
            "selected_dbs": selected_collections,  # 记住用户选的库
            "uploader": uploader,  # 使用实际用户名
            "data": {
                "type": d.get('type', ''),
                "object": d.get('object', ''),
                "purpose": d.get('purpose', ''),
                "customer_type": d.get('customer_type', ''),
                "keyword": d.get('keyword', ''),
                "problem": d.get('problem', []),
                "reply_logic": d.get('reply_logic', ''),
                "feature_explanation": d.get('feature_explanation', ''),
                "example": d.get('example', ''),
                "notes": d.get('notes', ''),
                "image_url": image_url_list,
                "file_url": file_url_list
            }
        }
        review_records.append(record)

    # 保存为独立文件（避免并发冲突）
    # 格式：user1_2025-11-28_15-30-45.json
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{uploader}_{timestamp}.json"
    review_file = os.path.join(REVIEW_DIR, filename)
    with open(review_file, 'w', encoding='utf-8') as f:
        json.dump(review_records, f, ensure_ascii=False, indent=2)

    # ========== 新增：自动清除已重新提交的被拒记录 ==========
    if rejected_id:  # ← 重点：改用 Form 传过来的 rejected_id
        rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
        if os.path.exists(rejected_file):
            try:
                with open(rejected_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                
                original_count = len(records)
                # 删除 id 匹配的那一条
                records = [r for r in records if str(r.get("id")) != str(rejected_id)]
                
                if len(records) < original_count:  # 说明确实删掉了
                    if records:
                        with open(rejected_file, 'w', encoding='utf-8') as f:
                            json.dump(records, f, ensure_ascii=False, indent=2)
                    else:
                        os.remove(rejected_file)  # 空了就删文件
                    print(f"用户 {uploader} 重新提交，已自动清除被拒记录 ID: {rejected_id}")
                else:
                    print(f"未找到被拒记录 ID: {rejected_id}，可能是已删除")
            except Exception as e:
                print(f"自动清除被拒记录失败: {e}")
    # =============================================

    return {"status": "pending_review", "message": "已提交审核，被拒记录已自动清除"}

# ========== 被拒数据查询 ==========
@app.get("/rejected_records")
async def get_rejected_records(authorization: Optional[str] = Header(default=None)):
    # ✅ 强制检查认证信息
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息，请先登录")
    
    # ✅ 解析token获取用户名
    try:
        uploader = get_uploader_from_token(authorization)
        if not uploader or uploader == "anonymous":
            raise HTTPException(status_code=401, detail="无效的认证信息，请重新登录")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"认证失败: {str(e)}")

    rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
    if not os.path.exists(rejected_file):
        return {"rejected": []}
    
    try:
        with open(rejected_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"rejected": data}
    except:
        return {"rejected": []}






# ========== 清除被拒数据（用户查看后）==========
@app.post("/clear_rejected")
async def clear_rejected(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")
    
    user = get_uploader_from_token(authorization)
    if user["role"] != "admin":  # 关键！只有 admin 能清
        return {"status": "warning", "message": "普通用户无权清除被拒记录"}
    
    # 只有 admin 才能走到这里
    rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{user['username']}.json")
    if os.path.exists(rejected_file):
        os.remove(rejected_file)
    
    return {"status": "cleared"}


# ========== 新增：删除单条被拒记录（用户自己或管理员可用）==========
@app.post("/delete_rejected_record")
async def delete_rejected_record(
    uploader: str = Form(...),           # 被拒记录所属用户
    record_id: str = Form(...),          # 要删除的记录 ID
    authorization: Optional[str] = Header(None)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        current_user = get_uploader_from_token(authorization)
        user_info = get_user_from_db(current_user)
        is_admin = user_info.get("role") == "admin" if user_info else False

        # 权限校验：只能删自己的，或者管理员删任意
        if current_user != uploader and not is_admin:
            raise HTTPException(status_code=403, detail="无权删除他人被拒记录")
    except:
        raise HTTPException(status_code=401, detail="认证失败")

    rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
    if not os.path.exists(rejected_file):
        return {"success": True, "message": "记录已不存在"}

    try:
        with open(rejected_file, 'r', encoding='utf-8') as f:
            records = json.load(f)

        original_count = len(records)
        records = [r for r in records if str(r.get("id")) != str(record_id)]

        if len(records) < original_count:
            if records:
                with open(rejected_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
            else:
                os.remove(rejected_file)
            print(f"用户 {current_user} 删除了 {uploader} 的被拒记录 {record_id}")
            return {"success": True, "message": "已删除该条被拒记录"}
        else:
            return {"success": False, "message": "记录未找到"}
    except Exception as e:
        print(f"删除被拒记录失败: {e}")
        raise HTTPException(status_code=500, detail="删除失败")
# 操作日志
LOG_FILE_PATH = "/home/RohonDev1/naiRAG/upload.log"
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

@app.post("/log")
async def log_operation(request: dict):
    try:
        timestamp = request.get("time", datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"))
        message = request.get("message", "无内容")
        log_line = f"[{timestamp}] {message}\n"
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(log_line)
        return {"status": "success", "message": "日志已记录"}
    except Exception as e:
        print(f"❌ 写入日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"日志写入失败: {str(e)}")

# ========== 新增：获取单条被拒记录（用于编辑）==========
@app.get("/rejected_record/{uploader}/{record_id}")
async def get_rejected_record(uploader: str, record_id: str, authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    
    try:
        current_user = get_uploader_from_token(authorization)
        if current_user != uploader and get_user_from_db(current_user)["role"] != "admin":
            raise HTTPException(status_code=403, detail="只能编辑自己的被拒记录")
    except:
        raise HTTPException(status_code=401, detail="认证失败")

    rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
    if not os.path.exists(rejected_file):
        raise HTTPException(status_code=404, detail="记录不存在")
    
    try:
        with open(rejected_file, 'r', encoding='utf-8') as f:
            records = json.load(f)
        for rec in records:
            if rec.get("id") == record_id:
                return rec
        raise HTTPException(status_code=404, detail="记录未找到")
    except:
        raise HTTPException(status_code=500, detail="读取失败")
    
    
# ================== 新增：专用于“修改被拒记录”重新提交 ==================
@app.post("/resubmit_rejected")
async def resubmit_rejected(
    old_record_id: str = Form(...),                    # 被拒记录的 id
    uploader: str = Form(...),                         # 记录所属用户（防越权）
    selected_dbs: List[str] = Form(...),               # 重新选择的库
    record_data: str = Form(...),                      # 新的结构化数据（JSON 字符串）
    keep_image_urls: List[str] = Form(default=[]),     # 用户勾选保留的图片URL
    keep_file_urls: List[str] = Form(default=[]),    # 用户勾选保留的文档URL
    new_images: List[UploadFile] = File(default=[]),   # 新增的图片
    new_docs: List[UploadFile] = File(default=[]),     # 新增的文档
    authorization: Optional[str] = Header(None)
):
    # ============ 认证 ============
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        current_user = get_uploader_from_token(authorization)
        user_info = get_user_from_db(current_user)
        is_admin = user_info.get("role") == "admin" if user_info else False
        if current_user != uploader and not is_admin:
            raise HTTPException(status_code=403, detail="只能修改自己的被拒记录")
    except:
        raise HTTPException(status_code=401, detail="认证失败")

    # ============ 解析新数据 ============
    try:
        new_data = json.loads(record_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="record_data 不是有效JSON")

    # ============ 处理新增图片 ============
    final_image_urls = list(keep_image_urls)  # 先保留用户勾选的旧图片
    if new_images:
        img_result = await upload_images(files=new_images)  # 复用你已改好的防重名上传接口
        final_image_urls.extend(img_result.get("image_paths", []))

    if not final_image_urls:
        final_image_urls = []

    # ============ 处理新增文档 ============
    final_file_urls = list(keep_file_urls)    # 先保留用户勾选的旧文档
    if new_docs:
        doc_result = await upload_documents(files=new_docs)
        final_file_urls.extend(doc_result.get("document_paths", []))

    if not final_file_urls:
        final_file_urls = []

    # ============ 组装最终记录 ============
    final_record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(BEIJING_TZ).isoformat(),
        "selected_dbs": [db for db in selected_dbs if db in COLLECTION_NAMES],
        "uploader": current_user,
        "data": {
            "type": new_data.get("type", ""),
            "object": new_data.get("object", ""),
            "purpose": new_data.get("purpose", ""),
            "customer_type": new_data.get("customer_type", ""),
            "keyword": new_data.get("keyword", ""),
            "problem": new_data.get("problem", []),
            "reply_logic": new_data.get("reply_logic", ""),
            "feature_explanation": new_data.get("feature_explanation", ""),
            "example": new_data.get("example", ""),
            "notes": new_data.get("notes", ""),
            "image_url": final_image_urls,
            "file_url": final_file_urls
        }
    }

    # ============ 保存到待审核目录 ============
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{current_user}_{timestamp}_resubmit.json"
    review_file = os.path.join(REVIEW_DIR, filename)
    with open(review_file, 'w', encoding='utf-8') as f:
        json.dump([final_record], f, ensure_ascii=False, indent=2)

    # ============ 自动删除原被拒记录 ============
    rejected_file = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
    if os.path.exists(rejected_file):
        try:
            with open(rejected_file, 'r', encoding='utf-8') as f:
                records = json.load(f)
            records = [r for r in records if r.get("id") != old_record_id]
            if records:
                with open(rejected_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
            else:
                os.remove(rejected_file)
        except Exception as e:
            print(f"清理被拒记录失败: {e}")
    return{
        "status": "success",
        "message": "修改成功，已重新提交审核，原被拒记录已清除",
        "new_pending_file": filename
        }

# 静态首页
@app.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, 'uploadReject929_3.html'))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8001)
