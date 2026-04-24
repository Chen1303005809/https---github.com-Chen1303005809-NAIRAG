# -*- coding: utf-8 -*-
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility


# ===== 一次性初始化配置（按需改这里）=====
MILVUS_HOST = "127.0.0.1"
MILVUS_PORT = "19530"
COLLECTION_NAMES = ["TEST"]
DROP_EXISTING = True

TEXT_DIM = 1024
VL_DIM = 2048

# 文本保留 IVF_FLAT，图像改 FLAT（更接近精确检索）
TEXT_INDEX_PARAMS = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 128},
}
VL_INDEX_PARAMS = {
    "metric_type": "COSINE",
    "index_type": "FLAT",
    "params": {},
}


def create_collection_schema() -> CollectionSchema:
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="chunk_id", dtype=DataType.INT64),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="field_type", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="field_text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="text_embedding", dtype=DataType.FLOAT_VECTOR, dim=TEXT_DIM),
        FieldSchema(name="vl_embedding", dtype=DataType.FLOAT_VECTOR, dim=VL_DIM),
        FieldSchema(name="weight", dtype=DataType.FLOAT),
        FieldSchema(name="file_url", dtype=DataType.VARCHAR, max_length=1024),
    ]
    return CollectionSchema(fields=fields, description="RAG collection with text and vision embeddings")


def create_collections() -> None:
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

    for name in COLLECTION_NAMES:
        if DROP_EXISTING and utility.has_collection(name):
            Collection(name).drop()
            print(f"已删除旧集合：{name}")

        if not utility.has_collection(name):
            schema = create_collection_schema()
            collection = Collection(name=name, schema=schema)
            collection.create_index(field_name="text_embedding", index_params=TEXT_INDEX_PARAMS)
            collection.create_index(field_name="vl_embedding", index_params=VL_INDEX_PARAMS)
            collection.create_index(field_name="doc_id", index_name="idx_doc_id")
            collection.create_index(field_name="chunk_id", index_name="idx_chunk_id")
            print(f"创建集合：{name}")
        else:
            print(f"集合 {name} 已存在，跳过创建")

        Collection(name).load()
        print(f"已加载集合：{name}")


if __name__ == "__main__":
    create_collections()
    print("所有集合已创建并加载完成")
