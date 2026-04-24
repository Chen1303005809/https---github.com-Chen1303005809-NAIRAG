# Configs Directory

本目录集中管理所有应用的配置与环境变量读取逻辑：

- `portal.py`：统一门户配置
- `upload.py`：上传端配置
- `rag.py`：检索端配置
- `admin.py`：管理端配置
- `common.py`：共享常量与工具函数
- `.env.example`：环境变量示例

兼容性说明：

- 旧路径 `portal_service/config.py`、`upload_service/config.py`、`rag_service/config.py`、`milvus_admin/backend/config.py` 仍可继续 import。
- 这些旧文件现在是转发层，实际配置逻辑已迁移到本目录。

