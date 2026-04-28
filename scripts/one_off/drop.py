from pymilvus import connections, Collection, utility

# 连接 Milvus（按你的实际地址修改）
connections.connect(alias="default", host="127.0.0.1", port="19530")


collection_names = ["rag_bge_m3_structured_v4_1", "rag_bge_m3_structured_v4_2", "rag_bge_m3_structured_v4_3", "rag_bge_m3_structured_v4_4", "rag_bge_m3_structured_v4_5", "TEST"]

for collection_name in collection_names:
    if utility.has_collection(collection_name):
        Collection(collection_name).drop()
        print(f"已删除向量库: {collection_name}")
    else:
        print(f"向量库不存在: {collection_name}")