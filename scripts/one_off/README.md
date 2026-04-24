# one_off scripts

一次性初始化/排障脚本统一放在这里：

- `init_users_db.py`：初始化 `users.db` 并写入默认账号
- `init_milvus_collections.py`：创建并加载 Milvus 集合与索引
- `check_milvus_collection_size.py`：查看指定集合数据量

使用时请在项目根目录执行，避免路径混乱。
