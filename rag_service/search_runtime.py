# -*- coding: utf-8 -*-
import logging

from pymilvus import Collection, connections

from utils.search_engine import MilvusSearchEngine

from .config import RagConfig

logger = logging.getLogger(__name__)


class SearchRuntime:
    def __init__(self, config: RagConfig):
        self.config = config
        self.collections: dict[str, Collection] = {}
        self.engine = MilvusSearchEngine(milvus_uri=f"http://{config.milvus_host}:{config.milvus_port}")
        self._load_collections()

    def _load_collections(self):
        connections.connect("default", host=self.config.milvus_host, port=self.config.milvus_port)
        for name in self.config.collection_names:
            try:
                collection = Collection(name)
                collection.load()
                self.collections[name] = collection
                logger.info("✅ 成功加载集合: %s", name)
            except Exception as exc:
                logger.error("❌ 加载集合 %s 失败：%s", name, exc)

    def available_collections(self, selected: str) -> list[str]:
        selected_collections = [
            name.strip()
            for name in selected.split(",")
            if name.strip() in self.config.collection_names
        ]
        if selected_collections:
            return selected_collections
        logger.warning("selected_dbs 为空，使用所有可用集合")
        return [name for name in self.config.collection_names if name in self.collections]

    def search_collection(self, coll_name: str, query: str):
        text_hits = self.engine.search_rag(
            collection_name=coll_name,
            query=query,
            embedding_field="text_embedding",
            top_k=50,
        )
        image_hits = self.engine.search_rag(
            collection_name=coll_name,
            query=query,
            embedding_field="vl_embedding",
            top_k=5,
        )
        return text_hits, image_hits
