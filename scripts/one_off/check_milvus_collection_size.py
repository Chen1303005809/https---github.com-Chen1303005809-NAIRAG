from pymilvus import connections, Collection

# 1. 连接到 Milvus 服务
connections.connect(host='localhost', port='19530')  # 根据你的部署修改 host 和 port

# 2. 获取已存在的集合（确保集合名正确）
collection_name = "rag_bge_m3_structured_v4_1"
collection = Collection(collection_name)

# 3. 刷新数据（可选但推荐，确保统计信息是最新的）
collection.flush()

# 4. 获取实体总数
total_count = collection.num_entities

print(f"集合 '{collection_name}' 中共有 {total_count} 条数据。")