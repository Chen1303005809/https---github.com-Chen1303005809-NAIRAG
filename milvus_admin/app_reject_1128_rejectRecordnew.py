from flask import Flask, request, jsonify, send_from_directory
from pymilvus import connections, Collection
import json
import os
from datetime import datetime
import numpy as np
import ollama
import jwt
import datetime as dt
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import glob
import threading
import time
import sqlite3
from passlib.context import CryptContext
import traceback
import logging

from typing import List
import sys
sys.path.append('/home/RohonDev1/naiRAG')
from utils.utils import embedding as embedding_func

# === 配置日志 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/RohonDev1/naiRAG/milvus_admin/app.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

DB_PATH = "/home/RohonDev1/naiRAG/users.db"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def await_log_operation(log_data):
    try:
        LOG_FILE = "operation_logs.json"
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []

        log_entry = {
            "id": len(logs) + 1,
            "timestamp": log_data.get("operation_time", datetime.now().isoformat()),
            "user": getattr(request, 'current_user', log_data.get("user", "system")),
            "type": log_data.get("type", "operation"),
            "collection": log_data.get("collection", ""),
            "record_id": log_data.get("record_id", None),
            "record_ids": log_data.get("record_ids", []),
            "details": log_data.get("details", "")
        }
        logs.append(log_entry)
        logs = logs[-1000:]

        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        log.info(f"📝 已记录操作日志: {log_entry}")
    except Exception as e:
        log.error(f"❌ 记录日志失败: {e}")

STATIC_ROOT = '/home/RohonDev1/naiRAG/static'

REVIEW_DIR = os.environ.get('REVIEW_DIR', '/home/RohonDev1/naiRAG/review_pending')
if not os.path.exists(REVIEW_DIR):
    os.makedirs(REVIEW_DIR)


app = Flask(__name__, 
            static_folder=STATIC_ROOT,
            template_folder='.')

JWT_SECRET = "your_jwt_secret_key_change_in_production_!@#"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
'''
USERS = {
    "admin": generate_password_hash("admin123"),
    "user1": generate_password_hash("user123"),
    "editor": generate_password_hash("edit456")
}
'''
def get_user_from_db(username: str):
    """从 users.db 查询用户"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT username, password_hash, role FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "username": row["username"],
                "password_hash": row["password_hash"],
                "role": row["role"]
            }
    except Exception as e:
        log.error(f"数据库连接失败: {e}")
    return None


def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "未提供认证令牌"}), 401

        try:
            if token.startswith("Bearer "):
                token = token[7:]
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.current_user = payload['username']
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "令牌已过期"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "无效令牌"}), 401

        return f(*args, **kwargs)
    return decorated_function


def require_role(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return jsonify({"error": "未提供认证令牌"}), 401

            try:
                if token.startswith("Bearer "):
                    token = token[7:]
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                request.current_user = payload['username']
                request.current_role = payload.get('role', 'user')  # 默认 user
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "令牌已过期"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "无效令牌"}), 401

            if required_role == "admin" and request.current_role != "admin":
                return jsonify({"error": "需要管理员权限"}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user = get_user_from_db(username)
    if not user:
        return jsonify({"error": "用户不存在"}), 401

    if not pwd_context.verify(password, user["password_hash"]):
        return jsonify({"error": "密码错误"}), 401

    # 生成 JWT（注意：payload 要包含 role！否则前端不知道权限）
    token = jwt.encode({
        'username': user["username"],
        'role': user["role"],           # 关键！加上 role
        'exp': dt.datetime.utcnow() + dt.timedelta(hours=JWT_EXPIRE_HOURS)
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return jsonify({
        "success": True,
        "token": token,
        "username": user["username"],
        "role": user["role"]             # 前端需要这个来显示权限
    })

@app.route('/admin/whoami', methods=['GET'])
@require_login
def whoami():
    return jsonify({
        "username": request.current_user
    })

connections.connect(host='192.168.1.100', port='19530')

LOG_FILE = "operation_logs.json"
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

@app.route('/')
def home():
    return "✅ Milvus 管理后台运行中... 请访问 /app_reject_928_2.html"

@app.route('/app_reject_928_2.html')
def serve_html():
    return send_from_directory('.', 'app_reject_928_2.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_ROOT, filename)


# 加到你的 app_reject_1128_rejectRecord.py 任意位置（靠前一点）
@app.route('/user_management.html')
def serve_user_management():
    return send_from_directory('.', 'user_management.html')


# ================== 审核端终极防重名上传 ==================

@app.route('/upload_image', methods=['POST'])
@require_login
def upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({"error": "未选择文件"}), 400

    # secure_filename 只做安全过滤，不加 UUID
    original_name = file.filename
    if not original_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg')):
        return jsonify({"error": "不支持的图片格式"}), 400

    target_path = os.path.join(STATIC_ROOT, 'images', original_name)

    # 核心：同名文件已存在 → 直接复用
    if os.path.exists(target_path):
        url = f"/static/images/{original_name}"
        return jsonify({"success": True, "url": url})

    # 不存在才保存
    file.save(target_path)
    url = f"/static/images/{original_name}"
    return jsonify({"success": True, "url": url})


@app.route('/upload_document', methods=['POST'])
@require_login
def upload_document():
    if 'document' not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files['document']
    if not file or file.filename == '':
        return jsonify({"error": "未选择文件"}), 400

    original_name = file.filename
    allowed = ('.pdf', '.docx', '.doc', '.zip', '.xlsx', '.xls', '.txt')
    if not original_name.lower().endswith(allowed):
        return jsonify({"error": "不支持的文档格式"}), 400

    target_path = os.path.join(STATIC_ROOT, 'documents', original_name)

    # 核心：同名直接复用
    if os.path.exists(target_path):
        url = f"/static/documents/{original_name}"
        return jsonify({"success": True, "url": url, "filename": original_name})

    file.save(target_path)
    url = f"/static/documents/{original_name}"
    return jsonify({"success": True, "url": url, "filename": original_name})

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

import uuid
import os

# 把原来的 allowed_document_file 函数改成支持 zip
def allowed_document_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'zip'}  # 新增 zip
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 新增：安全的中文文件名生成函数（保留原名，只防止同名覆盖）
# ============= 彻底修复版：安全的中文文件名函数 =============
import uuid

def safe_chinese_filename(original_filename, upload_type='image'):
    """
    生成安全的中文文件名，自动处理重名
    upload_type: 'image' 或 'document'
    """
    name, ext = os.path.splitext(original_filename)
    # 保留中文、字母、数字和常见符号
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-()[]【】（）")
    safe_name = safe_name.strip() or "unnamed"
    ext = ext.lower()

    # 根据类型选择上传目录
    if upload_type == 'image':
        upload_dir = os.path.join(STATIC_ROOT, 'images')
    else:
        upload_dir = os.path.join(STATIC_ROOT, 'documents')
    
    os.makedirs(upload_dir, exist_ok=True)

    final_name = f"{safe_name}{ext}"
    final_path = os.path.join(upload_dir, final_name)

    # 重名处理：加8位uuid
    if os.path.exists(final_path):
        unique_id = str(uuid.uuid4())[:8]
        final_name = f"{safe_name}_{unique_id}{ext}"
        final_path = os.path.join(upload_dir, final_name)

    return final_name, f"/static/{upload_type}s/{final_name}"

# ========== 新增：删除旧文件函数 ==========
def delete_old_files(old_image_urls, old_file_urls):
    """删除旧的图片和文档文件（物理删除）"""
    try:
        # 删除旧图片
        for url in old_image_urls or []:
            if url and url != "N/A":
                if url.startswith('/'):
                    rel_path = url[1:]
                else:
                    rel_path = url
                file_path = os.path.join(STATIC_ROOT, rel_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    log.info(f"🗑️ 已删除旧图片: {file_path}")

        # 删除旧文档
        for url in old_file_urls or []:
            if url and url != "N/A":
                if url.startswith('/'):
                    rel_path = url[1:]
                else:
                    rel_path = url
                file_path = os.path.join(STATIC_ROOT, rel_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    log.info(f"🗑️ 已删除旧文档: {file_path}")
    except Exception as e:
        log.error(f"❌ 删除旧文件失败: {e}")

# ========== 数据管理接口 ==========

@app.route('/admin/get_data_paginated', methods=['GET'])
@require_login
def get_data_paginated():
    collection_name = request.args.get('collection')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 13683))

    if not collection_name:
        return jsonify({"error": "缺少 collection 参数"}), 400

    try:
        collection = Collection(collection_name)
        collection.load()

        expr = "id >= 0"
        total_results = collection.query(expr=expr, output_fields=["id"], limit=13683)
        total = len(total_results)

        offset = (page - 1) * page_size
        results = collection.query(
            expr=expr,
            output_fields=["*"], 
            limit=page_size,
            offset=offset
        )

        serializable_results = []
        for item in results:
            clean_item = {}
            for key, value in item.items():
                if isinstance(value, np.ndarray):
                    clean_item[key] = value.tolist()
                else:
                    clean_item[key] = value
                if key == 'text':
                    clean_item[key] = json.loads(value)
            clean_item['id'] = str(clean_item['id'])
            if 'updated_at' not in clean_item:
                clean_item['updated_at'] = datetime.now().isoformat()
            serializable_results.append(clean_item)

        return jsonify({
            "data": serializable_results,
            "total": total,
            "page": page,
            "page_size": page_size
        })
    except Exception as e:
        log.error(f"❌ 查询异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ========== 重构：使用embedding函数的 update_record ==========
@app.route('/admin/update_record', methods=['POST'])
@require_login
def update_record():
    collection_name = request.args.get('collection')
    data = request.get_json()

    if not collection_name or not data or 'id' not in data:
        return jsonify({"error": "缺少必要参数"}), 400

    try:
        log.info(f"✅ 开始更新记录: collection={collection_name}, id={data['id']}")
        collection = Collection(collection_name)
        old_id = int(data['id'])

        # === 查询旧记录以获取旧文件 URL ===
        old_results = collection.query(expr=f"id == {old_id}", output_fields=["file_url"])
        if not old_results:
            raise ValueError(f"原记录 ID={old_id} 不存在")
        
        old_item = old_results[0]
        old_file_urls = old_item.get("file_url", "")
        
        # 解析旧文件URL
        try:
            old_urls = json.loads(old_file_urls) if isinstance(old_file_urls, str) else old_file_urls
            old_urls = [u for u in old_urls if u and u != "N/A"] if isinstance(old_urls, list) else []
        except:
            old_urls = []

        # 删除旧记录
        collection.delete(f"id == {old_id}")
        collection.flush()
        log.info(f"✅ 旧记录删除操作已落盘")

        # === 使用embedding函数生成分片记录 ===
        new_records = embedding_func(data)
        
        if not new_records:
            raise ValueError("未生成任何embedding记录")

        # 批量插入新记录
        for chunk in new_records:
            insert_data = [
                [chunk['chunk_id']],
                [chunk['doc_id']],
                [chunk['field_type']],
                [chunk['field_text']],
                [chunk['text_embedding']],
                [chunk['vl_embedding']],
                [chunk['weight']],
                [chunk['file_url']]
            ]
            collection.insert(insert_data)
        
        collection.flush()
        log.info(f"✅ 新数据插入成功，共 {len(new_records)} 条分片")

        # === 删除旧文件（物理删除）===
        delete_old_files(old_urls, [])

        try:
            collection.compact()
            collection.wait_for_compaction_completed()
            collection.release()
            collection.load()
            log.info(f"🔄 已触发 compact")
        except Exception as e:
            log.warning(f"⚠️ compact 触发失败（不影响功能）: {e}")

        await_log_operation({
            "type": "update",
            "collection": collection_name,
            "record_id": old_id,
            "details": f"修改了对象: {data.get('object', '')}, 生成 {len(new_records)} 个分片",
            "operation_time": datetime.now().isoformat(),
        })

        return jsonify({
            "success": True, 
            "message": f"更新成功！生成 {len(new_records)} 个分片"
        })

    except Exception as e:
        log.error(f"❌ 更新失败: {e}")
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/admin/delete_record', methods=['DELETE'])
@require_login
def delete_single_record():
    collection_name = request.args.get('collection')
    record_id = request.args.get('id')
    
    if not collection_name or not record_id:
        return jsonify({"error": "缺少必要参数"}), 400

    try:
        collection = Collection(collection_name)
        record_id = int(record_id)
        
        # === 查询该ID对应的doc_id ===
        query_results = collection.query(expr=f"id == {record_id}", output_fields=["doc_id"])
        if not query_results:
            return jsonify({"error": f"记录 ID={record_id} 不存在"}), 404
        
        doc_id = query_results[0].get("doc_id")
        
        # === 按doc_id删除所有相关分片 ===
        expr = f'doc_id == "{doc_id}"'
        log.info(f"🗑️ 准备按doc_id删除: {expr}")
        collection.delete(expr)
        collection.flush()
        log.info(f"✅ 删除操作已落盘")

        try:
            collection.compact()
            collection.wait_for_compaction_completed()
            log.info(f"🔄 已触发 compact")
        except Exception as e:
            log.warning(f"⚠️ compact 触发失败（不影响功能）: {e}")

        await_log_operation({
            "type": "delete",
            "collection": collection_name,
            "record_id": record_id,
            "details": f"删除了doc_id={doc_id}的所有分片（通过ID={record_id}定位）",
            "operation_time": datetime.now().isoformat(),
        })

        return jsonify({
            "success": True, 
            "message": f"已成功删除 doc_id={doc_id} 的所有分片"
        })
    except Exception as e:
        log.error(f"❌ 删除失败: {e}")
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/admin/delete_records', methods=['POST'])
@require_login
def delete_multiple_records():
    collection_name = request.args.get('collection')
    data = request.get_json()
    ids = data.get('ids', [])

    if not collection_name or not ids:
        return jsonify({"error": "缺少必要参数"}), 400

    try:
        collection = Collection(collection_name)

        # === 收集所有doc_id ===
        doc_ids_to_delete = set()
        for id_str in ids:
            try:
                record_id = int(id_str)
                query_results = collection.query(expr=f"id == {record_id}", output_fields=["doc_id"])
                if query_results:
                    doc_id = query_results[0].get("doc_id")
                    doc_ids_to_delete.add(doc_id)
                    log.info(f"✅ 查询到 ID={record_id} 对应 doc_id={doc_id}")
            except Exception as e:
                log.warning(f"⚠️ 查询 ID={id_str} 失败: {e}")
                continue

        # === 按doc_id批量删除所有分片 ===
        deleted_count = 0
        for doc_id in doc_ids_to_delete:
            try:
                expr = f'doc_id == "{doc_id}"'
                log.info(f"🗑️ 删除分片: {expr}")
                collection.delete(expr)
                deleted_count += 1
            except Exception as e:
                log.warning(f"⚠️ 删除 doc_id={doc_id} 失败: {e}")
                continue

        collection.flush()
        log.info(f"✅ 批量删除完成，共删除 {deleted_count} 个doc_id的所有分片")

        try:
            collection.compact()
            collection.wait_for_compaction_completed()
            log.info(f"🔄 已触发 compact")
        except Exception as e:
            log.warning(f"⚠️ compact 触发失败: {e}")

        await_log_operation({
            "type": "batch_delete",
            "collection": collection_name,
            "record_ids": ids,
            "details": f"批量删除了 {deleted_count} 个doc_id的所有分片",
            "operation_time": datetime.now().isoformat(),
        })

        return jsonify({
            "success": True,
            "deleted": deleted_count,
            "message": f"成功删除 {deleted_count} 个doc_id的所有分片"
        })

    except Exception as e:
        log.error(f"❌ 批量删除失败: {e}")
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/admin/get_logs', methods=['GET'])
@require_login
def get_logs():
    try:
        if not os.path.exists(LOG_FILE):
            return jsonify([])

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


REVIEW_DIR = '/home/RohonDev1/naiRAG/review_pending'

@app.route('/admin/get_review_data', methods=['GET'])
@require_login
def get_review_data():
    records = []
    for filename in os.listdir(REVIEW_DIR):
        if not filename.endswith(".json") or filename.startswith("rejected"):
            continue
        filepath = os.path.join(REVIEW_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_records = json.load(f)
                for rec in file_records:
                    # 关键！把 selected_dbs 暴露给前端
                    rec_copy = rec.copy()
                    rec_copy["selected_dbs"] = rec.get("selected_dbs", [])
                    rec_copy["source_file"] = filename
                    records.append(rec_copy)
        except Exception as e:
            print(f"读取审核文件 {filename} 失败: {e}")
            continue

    return jsonify(records)

# ================== 终极修复版：审核端编辑保存（保证 selected_dbs 一定写入）==================
@app.route('/admin/update_review_record', methods=['POST'])
@require_login
def update_review_record():
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    record_id = data.get("id")
    new_selected_dbs = data.get("selected_dbs", [])
    new_data = data.get("data", {})

    if not record_id:
        return jsonify({"error": "缺少记录ID"}), 400

    updated = False
    updated_file = None

    # 遍历所有 pending 文件，找到包含该 ID 的记录
    for filename in os.listdir(REVIEW_DIR):
        if not filename.endswith(".json") or "rejected" in filename:
            continue

        filepath = os.path.join(REVIEW_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                records = json.load(f)

            found = False
            for i, rec in enumerate(records):
                if str(rec.get("id")) == str(record_id):
                    # 关键！直接修改这条记录
                    records[i]["selected_dbs"] = new_selected_dbs
                    records[i]["data"] = {
                        "type": new_data.get("type", rec["data"].get("type", "")),
                        "object": new_data.get("object", rec["data"].get("object", "")),
                        "purpose": new_data.get("purpose", rec["data"].get("purpose", "")),
                        "customer_type": new_data.get("customer_type", rec["data"].get("customer_type", "")),
                        "keyword": new_data.get("keyword", rec["data"].get("keyword", "")),
                        "problem": new_data.get("problem", rec["data"].get("problem", [])),
                        "text": new_data.get("text", rec["data"].get("text", "")),
                        "image_url": new_data.get("image_url", rec["data"].get("image_url", ["N/A"])),
                        "file_url": new_data.get("file_url", rec["data"].get("file_url", ["N/A"])),
                    }
                    found = True
                    updated = True
                    updated_file = filename
                    break

            if found:
                # 写回原文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                log.info(f"已成功更新待审核记录 {record_id}，文件: {updated_file}")
                break

        except Exception as e:
            log.error(f"处理文件 {filename} 时出错: {e}")
            continue

    if not updated:
        return jsonify({"error": "未找到该记录，可能已被处理"}), 404

    # 记录日志
    await_log_operation({
        "type": "update_review_record",
        "details": f"编辑待审核记录 {record_id}，目标库: {', '.join(new_selected_dbs)}",
        "user": request.current_user
    })

    return jsonify({"success": True, "message": "保存成功"})

# ========== 重构：使用embedding函数的 approve_records ==========
@app.route('/admin/approve_records', methods=['POST'])
@require_role("admin")
def approve_records():
    if request.current_user != 'admin':
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    approved_ids = data.get('ids', [])
    review_records = data.get('records', [])

    try:
        # 按selected_dbs分组写入Milvus
        for rec in review_records:
            if rec['id'] not in approved_ids:
                continue
            
            rec_data = rec['data']
            selected_dbs = rec['selected_dbs']
            
            # === 使用embedding函数生成分片记录 ===
            new_records = embedding_func(rec_data)
            
            if not new_records:
                log.warning(f"⚠️ 记录 {rec['id']} 未生成任何分片，跳过")
                continue
            
            # 为每个选中的数据库插入分片
            for coll_name in selected_dbs:
                try:
                    coll = Collection(coll_name)
                    
                    for chunk in new_records:
                        insert_data = [
                            [chunk['chunk_id']],
                            [chunk['doc_id']],
                            [chunk['field_type']],
                            [chunk['field_text']],
                            [chunk['text_embedding']],
                            [chunk['vl_embedding']],
                            [chunk['weight']],
                            [chunk['file_url']]
                        ]
                        coll.insert(insert_data)
                    
                    coll.flush()
                    log.info(f"✅ 已向 {coll_name} 插入 {len(new_records)} 个分片")
                except Exception as e:
                    log.error(f"❌ 向 {coll_name} 插入失败: {e}")
                    raise

        # 删除审核文件
        _cleanup_review_files(review_records, approved_ids)

        await_log_operation({
            "type": "approve",
            "user": request.current_user,
            "details": f"通过 {len(approved_ids)} 条审核记录",
            "operation_time": datetime.now().isoformat(),
        })

        return jsonify({"success": True, "message": f"已通过 {len(approved_ids)} 条记录"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# 批量拒绝审核
@app.route('/admin/reject_records', methods=['POST'])
@require_role("admin")
def reject_records():
    if request.current_user != 'admin':
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    rejected_ids = set(data.get('ids', []))
    review_records = data.get('records', [])
    reject_reason = data.get('reject_reason', '').strip()  # 新增：接收批注

    # ✅ 按 uploader 分组被拒数据
    # 正确写法（重点：优先使用原来的 uploader，绝不降级成 anonymous）
    rejected_by_user = {}
    for rec in review_records:
        if rec['id'] not in rejected_ids:
            continue
            
        # 关键修复：如果原文件有 uploader 就用原值，没有才 fallback
        uploader = rec.get('uploader') or 'anonymous'   # 改这里！！！
        
        if uploader not in rejected_by_user:
            rejected_by_user[uploader] = []
            
        rejected_by_user[uploader].append({
            "id": rec['id'],
            "timestamp": rec['timestamp'],
            "selected_dbs": rec['selected_dbs'],
            "data": rec['data'],
            "reject_reason": reject_reason or "管理员未填写拒绝原因",
        })


    # 删除审核文件
    _cleanup_review_files(review_records, rejected_ids)

    # ✅ 保存被拒数据到用户专属目录
    REJECTED_DIR = os.path.join(REVIEW_DIR, 'rejected')
    os.makedirs(REJECTED_DIR, exist_ok=True)
    
    for uploader, items in rejected_by_user.items():
        user_file = os.path.join(REJECTED_DIR, f"{uploader}.json")
        # 把 uploader 字段也写进去（冗余但极度安全）
        for item in items:
            item['uploader'] = uploader   # ← 加上这行！万无一失
        # 追加到现有被拒数据
        existing = []
        if os.path.exists(user_file):
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass
        existing.extend(items)
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    await_log_operation({
        "type": "reject",
        "user": request.current_user,  # ✅ 不要传 set
        "details": f"拒绝 {len(rejected_ids)} 条审核记录",
        "operation_time": datetime.now().isoformat(),
        "collection": "review_queue",  # 审核队列无具体 collection
        "record_ids": list(rejected_ids)  # 转为 list
    })

    # 返回分组数据（供前端下载）
    return jsonify({"rejected_by_user": rejected_by_user})

@app.route('/admin/get_all_rejected', methods=['GET'])
@require_login
def get_all_rejected():
    if request.current_user != 'admin':
        return jsonify({"error": "权限不足"}), 403
    
    rejected_data = {}
    rejected_dir = os.path.join(REVIEW_DIR, 'rejected')
    
    if os.path.exists(rejected_dir):
        for file in os.listdir(rejected_dir):
            if file.endswith('.json'):
                uploader = file.replace('.json', '')
                filepath = os.path.join(rejected_dir, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        records = json.load(f)
                        rejected_data[uploader] = records
                except:
                    continue
    
    return jsonify({"rejected": rejected_data})

# 增加后端接口中的删除函数
@app.route('/admin/delete_rejected', methods=['POST'])
@require_role("admin")
def delete_rejected():
    if request.current_user != 'admin':
        return jsonify({"error": "权限不足"}), 403
    
    data = request.get_json()
    uploader = data.get('uploader')
    record_id = data.get('id')
    
    file_path = os.path.join(REVIEW_DIR, 'rejected', f"{uploader}.json")
    if not os.path.exists(file_path):
        return jsonify({"success": True, "message": "文件已不存在"})
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
        
        records = [r for r in records if str(r.get('id')) != str(record_id)]
        
        if len(records) == 0:
            os.remove(file_path)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/clear_all_rejected', methods=['POST'])
@require_role("admin")
def clear_all_rejected():
    if request.current_user != 'admin':
        return jsonify({"error": "权限不足"}), 403
    
    rejected_dir = os.path.join(REVIEW_DIR, 'rejected')
    if os.path.exists(rejected_dir):
        import shutil
        shutil.rmtree(rejected_dir)
        os.makedirs(rejected_dir, exist_ok=True)
    
    return jsonify({"success": True})


# 修改 _cleanup_review_files 函数
def _cleanup_review_files(review_records, target_ids):
    """删除包含目标ID的审核文件"""
    files_to_delete = set()
    for rec in review_records:
        if rec['id'] in target_ids:
            # 检查 source_file 是否存在，如果不存在则使用默认值
            source_file = rec.get('source_file', f"review_{rec['id']}.json")
            files_to_delete.add(source_file)
    
    for filename in files_to_delete:
        filepath = os.path.join(REVIEW_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            log.info(f"🗑️ 删除审核文件: {filepath}")
# ========== 【新增】用户管理接口 ==========
import hashlib

@app.route('/admin/users', methods=['GET'])
@require_role("admin")
def get_all_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
        rows = c.fetchall()
        users = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/users/create', methods=['POST'])
@require_role("admin")
def create_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if role not in ['admin', 'editor', 'user']:
        return jsonify({"error": "无效的角色"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "用户名已存在"}), 400

        hashed = pwd_context.hash(password)
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                  (username, hashed, role))
        conn.commit()
        conn.close()
        await_log_operation({
            "type": "create_user",
            "details": f"创建用户 {username} ({role})",
            "user": request.current_user
        })
        return jsonify({"success": True, "message": "用户创建成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/users/update', methods=['POST'])
@require_role("admin")
def update_user():
    data = request.get_json()
    user_id = data.get('id')
    username = data.get('username')
    password = data.get('password', '').strip()
    role = data.get('role')

    if not user_id or not username or not role:
        return jsonify({"error": "参数不完整"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 检查新用户名是否重复（排除自己）
        c.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "用户名已存在"}), 400

        if password:
            hashed = pwd_context.hash(password)
            c.execute("UPDATE users SET username = ?, password_hash = ?, role = ? WHERE id = ?",
                      (username, hashed, role, user_id))
        else:
            c.execute("UPDATE users SET username = ?, role = ? WHERE id = ?",
                      (username, role, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/users/delete', methods=['POST'])
@require_role("admin")
def delete_user():
    data = request.get_json()
    user_id = data.get('id')
    if not user_id:
        return jsonify({"error": "缺少用户ID"}), 400
    if str(user_id) == "1":  # 假设 id=1 是默认 admin，防止自毁
        return jsonify({"error": "禁止删除默认管理员"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        await_log_operation({
            "type": "delete_user",
            "details": f"删除用户 ID={user_id}",
            "user": request.current_user
        })
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== 新增：获取动态选项（供编辑页面使用）==========
import json

OPTIONS_FILE = "/home/RohonDev1/naiRAG/static/rag_options.json"

@app.route('/admin/get_rag_options', methods=['GET'])
@require_login
def get_rag_options():
    try:
        if os.path.exists(OPTIONS_FILE):
            with open(OPTIONS_FILE, 'r', encoding='utf-8') as f:
                options = json.load(f)
        else:
            # 如果文件不存在，返回一个合理的默认值（防止前端崩溃）
            options = {
                "type": ["解释概念", "操作步骤", "故障排查", "权限说明", "数据查询"],
                "object": ["净头寸", "订单管理", "用户权限", "报表导出", "风控设置"],
                "purpose": ["用户咨询", "内部培训", "系统帮助", "客户支持", "审计合规"],
                "customer_type": ["个人客户", "机构客户", "内部员工", "合作伙伴", "系统管理员"]
            }
        return jsonify({"success": True, "options": options})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
          
if __name__ == '__main__':
    log.info(f"🚀 正在启动 Milvus 数据管理后台...")
    log.info(f"🌐 访问地址: http://192.168.1.100:5000/app_reject_928_2.html")
    log.info(f"📁 图片保存目录: {os.path.join(STATIC_ROOT, 'images')}")
    log.info(f"📁 文档保存目录: {os.path.join(STATIC_ROOT, 'documents')}")
    log.info(f"🛑 按 Ctrl+C 停止服务")
    app.run(host='0.0.0.0', port=5000, debug=True)
