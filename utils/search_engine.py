import os, torch
from typing import Any, Dict, List, Optional
from .qwen3_embedding import Qwen3VLEmbedder


from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility


class MilvusSearchEngine:
    """Embed multimodal inputs and store/search vectors in Milvus."""

    def __init__(
        self,
        milvus_uri: str = "http://127.0.0.1:19530",
        milvus_token: Optional[str] = None,
        metric_type: str = "IP",
        consistency_level: str = "Strong",
    ):
        self.metric_type = metric_type
        self.consistency_level = consistency_level
        self.device = "cpu"

        self._init_embedders()
        self._connect_milvus(milvus_uri, milvus_token)

    def _init_embedders(self) -> None:
        """Initialize both text and visual embedders."""
        # Text embedder: bge-m3
        self.text_embedder = {
            "family": "bge_m3",
            "dimension": 1024
        }

        # Visual embedder: Qwen3-VL-Embedding-2B
        try:
            self.visual_embedder = {
                "family": "qwen3_vl",
                "dimension": 2048,
                "model": Qwen3VLEmbedder("Qwen/Qwen3-VL-Embedding-2B")
            }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to initialize Qwen3-VL embedder: {str(e)}")
            # Fallback to dummy visual embedder
            self.visual_embedder = {
                "family": "dummy",
                "dimension": 2048
            }

    def _connect_milvus(self, milvus_uri: str, milvus_token: Optional[str]) -> None:
        # 检查是否已经存在连接，如果存在则先断开
        if connections.has_connection("default"):
            try:
                connections.disconnect("default")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Disconnect existing connection failed: {str(e)}")
        
        kwargs: Dict[str, Any] = {"alias": "default", "uri": milvus_uri}
        if milvus_token:
            kwargs["token"] = milvus_token
        connections.connect(**kwargs)


    def _embed_images(self, image_paths: List[str]) -> List[Optional[List[float]]]:
        """Embed images using Qwen3-VL model."""
        if self.visual_embedder["family"] == "qwen3_vl":
            import logging
            from PIL import Image, ImageOps
            logger = logging.getLogger(__name__)

            outputs: List[Optional[List[float]]] = []

            def _load_safe_image(path: str):
                with Image.open(path) as img:
                    rgb = ImageOps.exif_transpose(img).convert("RGB")
                    max_side = 1536
                    if max(rgb.size) > max_side:
                        scale = max_side / float(max(rgb.size))
                        new_w = max(28, int(rgb.size[0] * scale))
                        new_h = max(28, int(rgb.size[1] * scale))
                        rgb = rgb.resize((new_w, new_h), Image.Resampling.BICUBIC)
                    return rgb

            # Process images one by one to avoid occasional batch shape conflicts.
            for image_path in image_paths:
                try:
                    result = self.visual_embedder["model"].process([{"image": image_path}], normalize=True)
                    if torch is not None:
                        vec = result.detach().cpu().float().numpy().tolist()[0]
                    else:
                        vec = result[0]
                    outputs.append(vec)
                except Exception as exc:
                    logger.warning("Image embedding failed for %s, retry with safe PIL image: %s", image_path, exc)
                    try:
                        safe_img = _load_safe_image(image_path)
                        result = self.visual_embedder["model"].process([{"image": safe_img}], normalize=True)
                        if torch is not None:
                            vec = result.detach().cpu().float().numpy().tolist()[0]
                        else:
                            vec = result[0]
                        outputs.append(vec)
                    except Exception as exc2:
                        logger.error("Image embedding failed for %s after retry: %s", image_path, exc2)
                        outputs.append(None)
            return outputs

        # Fallback: visual embedder unavailable
        return [None for _ in image_paths]

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using bge-m3 model."""
        import ollama
        import numpy as np
        embeddings = []
        for text in texts:
            try:
                emb = ollama.embeddings(model="bge-m3", prompt=text)["embedding"]
                emb = np.array(emb)
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                embeddings.append(emb.tolist())
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"生成嵌入失败: {str(e)}")
                embeddings.append(np.zeros(1024).tolist())
        return embeddings

    def search_rag(self, collection_name: str, query: str = None, image_path: str = None,
                   embedding_field: str = "text_embedding", top_k: int = 5, nprobe: int = 32) -> List[Dict[str, Any]]:
        """
        Unified search function for RAG collections (compatible with standard RAG schema)
        
        Args:
            collection_name: Name of the RAG collection
            query: Text query (used if embedding_field="text_embedding")
            image_path: Image path (used if embedding_field="vl_embedding")
            embedding_field: "text_embedding" or "vl_embedding" for polymorphic search
            top_k: Number of top results to return
            
        Returns:
            List of search results with metadata
        """
        try:
            rag_collection = Collection(collection_name)
            
            # Generate appropriate embedding based on field type
            if embedding_field == "text_embedding":
                if not query:
                    raise ValueError("query is required for text_embedding search")
                query_embedding = self._embed_texts([query])[0]
            elif embedding_field == "vl_embedding":
                if not image_path and not query:
                    raise ValueError("Either image_path or query is required for vl_embedding search")
                
                # For vl_embedding, always use visual embedder
                if image_path:
                    query_embedding = self._embed_images([image_path])[0]
                    if query_embedding is None:
                        raise ValueError(f"Image embedding failed for query image: {image_path}")
                else:
                    # If no image, use Qwen3-VL to embed the text query
                    if self.visual_embedder["family"] == "qwen3_vl":
                        # Use Qwen3-VL to embed the text query
                        inputs = [{"text": query}]
                        result = self.visual_embedder["model"].process(inputs, normalize=True)
                        query_embedding = result.detach().cpu().float().numpy().tolist()[0]
                    else:
                        # Fallback to text embedding if Qwen3-VL is not available
                        text_emb = self._embed_texts([query])[0]
                        import numpy as np
                        # Pad or truncate to visual embedder dimension
                        visual_dim = self.visual_embedder["dimension"]
                        if len(text_emb) < visual_dim:
                            # Pad with zeros
                            query_embedding = text_emb + [0.0] * (visual_dim - len(text_emb))
                        else:
                            # Truncate
                            query_embedding = text_emb[:visual_dim]
            else:
                raise ValueError(f"embedding_field must be 'text_embedding' or 'vl_embedding', got {embedding_field}")
            
            search_expr = None
            if embedding_field == "vl_embedding":
                # Exclude text chunks with placeholder visual vectors.
                search_expr = 'field_type == "image"'

            search_params: Dict[str, Any] = {"metric_type": "COSINE", "params": {"nprobe": nprobe}}

            results = rag_collection.search(
                data=[query_embedding],
                anns_field=embedding_field,
                limit=top_k,
                output_fields=[
                    "chunk_id",
                    "doc_id",
                    "type",
                    "object",
                    "purpose",
                    "customer_type",
                    "field_type",
                    "field_text",
                    "file_url",
                    "weight",
                ],
                param=search_params,
                expr=search_expr,
            )
            
            hits = []
            for hit in results[0]:
                hits.append(
                    {
                        "id": int(hit.id),
                        "score": float(hit.score),
                        "chunk_id": hit.entity.get("chunk_id"),
                        "doc_id": hit.entity.get("doc_id"),
                        "type": hit.entity.get("type"),
                        "object": hit.entity.get("object"),
                        "purpose": hit.entity.get("purpose"),
                        "customer_type": hit.entity.get("customer_type"),
                        "field_type": hit.entity.get("field_type"),
                        "field_text": hit.entity.get("field_text"),
                        "file_url": hit.entity.get("file_url"),
                        "weight": hit.entity.get("weight"),
                    }
                )
            return hits
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"RAG search failed: {str(e)}")
            return []
