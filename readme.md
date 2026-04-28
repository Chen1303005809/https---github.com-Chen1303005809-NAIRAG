# nairag 运行说明

本项目是一个统一 RAG 服务，包含：
- 门户登录（`/`）
- 上传端（`/upload/`）
- 检索端（`/search/`）
- 管理端（`/admin/admin_dashboard.html`）

推荐使用统一入口 `portal.py`，一次启动全部子服务。

## 1. 环境要求

- Python `3.12`
- Docker（用于启动 Milvus）
- Ollama（用于 `bge-m3` 文本向量）

## 2. 创建虚拟环境（Python 3.12）

在项目根目录执行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

## 3. 安装依赖

项目未提供统一 `requirements.txt`，可先按当前代码安装：

```bash
pip install \
  fastapi uvicorn flask starlette jinja2 \
  pydantic python-multipart \
  pymilvus numpy pillow \
  passlib[bcrypt] pyjwt ollama \
  torch transformers qwen-vl-utils
```

> 说明：`rag_service` 导入链会直接使用 `torch/transformers`，建议一并安装。

## 4. 配置环境变量（可选）

项目配置默认会回落到仓库内路径（例如 `users.db`、`static/`），不配也可启动。

如需自定义，可参考 `configs/.env.example`，例如：

```bash
export USERS_DB_PATH="$(pwd)/users.db"
export MILVUS_HOST="127.0.0.1"
export MILVUS_PORT="19530"
export FASTAPI_SECRET="change-me"
export FLASK_SECRET="change-me"
export SECRET_KEY="change-me"
```

## 5. 启动 Milvus

```bash
docker compose up -d
```

检查是否正常：

```bash
docker ps | grep milvus-standalone
```

## 6. 初始化数据（首次运行）

### 6.1 初始化用户库

```bash
python scripts/one_off/init_users_db.py
```

默认账号：
- 管理员：`admin / admin123`
- 普通用户：`user1 / user123`（及脚本中其他 `user*`）

### 6.2 初始化 Milvus 集合

```bash
python scripts/one_off/init_milvus_collections.py
```

> 注意：脚本里当前写死了 `COLLECTION_NAMES=["TEST"]` 且 `DROP_EXISTING=True`，会先删后建。生产数据请先改这两个变量。

## 7. 启动应用（统一入口）

```bash
python portal.py
```

启动后访问：
- [http://127.0.0.1:8000](http://127.0.0.1:8000)（登录门户）
- [http://127.0.0.1:8000/upload/](http://127.0.0.1:8000/upload/)
- [http://127.0.0.1:8000/search/](http://127.0.0.1:8000/search/)
- [http://127.0.0.1:8000/admin/admin_dashboard.html](http://127.0.0.1:8000/admin/admin_dashboard.html)

## 8. Ollama 模型准备

如果检索或入库阶段提示 embedding 失败，先确认：

```bash
ollama pull bge-m3
```

并确保 Ollama 服务在本机可用。

## 9. 常见问题

1. `ModuleNotFoundError`：确认已激活 `rag_env` 且完成依赖安装。
2. 无法连接 Milvus：确认 `docker compose up -d` 成功，且端口 `19530` 可达。
3. 登录失败：先执行 `python scripts/one_off/init_users_db.py` 初始化 `users.db`。
4. 检索结果为空：确认 Milvus 中有数据（只建空集合不会返回有效结果）。
