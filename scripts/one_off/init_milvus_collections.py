# -*- coding: utf-8 -*-
import os
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 定义4个向量数据库集合名称
COLLECTION_NAMES = [
    "TEST"
]

# 定义集合的 schema
def create_collection_schema():
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),  # 主键，自增
        FieldSchema(name="chunk_id", dtype=DataType.INT64),  # 聚合主键
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=255),  # 聚合键
        FieldSchema(name="field_type", dtype=DataType.VARCHAR, max_length=255),  # 例如 keyword/problem/background/solution
        FieldSchema(name="field_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="text_embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema(name="vl_embedding", dtype=DataType.FLOAT_VECTOR, dim=2048),
        FieldSchema(name="weight", dtype=DataType.FLOAT),  # 可选，字段先验权重
        FieldSchema(name="file_url", dtype=DataType.VARCHAR, max_length=1024)
    ]
    return CollectionSchema(fields=fields, description="RAG collection with text and vision embeddings")

def create_collections():
    # 连接 Milvus
    connections.connect("default", host="127.0.0.1", port="19530")

    # 创建或加载集合
    for name in COLLECTION_NAMES:
        if not utility.has_collection(name):
            schema = create_collection_schema()
            collection = Collection(name=name, schema=schema)
            
            # 为文本向量创建索引
            text_index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index(field_name="text_embedding", index_params=text_index_params)
            
            # 为视觉向量创建索引
            vl_index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index(field_name="vl_embedding", index_params=vl_index_params)
            
            # 为聚合键创建索引（doc_id + chunk_id 联合唯一）
            collection.create_index(field_name="doc_id", index_name="idx_doc_id")
            collection.create_index(field_name="chunk_id", index_name="idx_chunk_id")
            
            print(f"创建集合：{name}")
        else:
            print(f"集合 {name} 已存在，跳过创建")
        
        # 加载集合
        collection = Collection(name)
        collection.load()

if __name__ == "__main__":
    create_collections()
    print("所有集合已创建并加载完成")
