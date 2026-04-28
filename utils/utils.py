
import uuid
import ollama
import os
import math
from typing import Optional, List
from pathlib import Path
from utils.search_engine import MilvusSearchEngine


# 全局嵌入器缓存，避免重复初始化
_image_embedder_cache = None


def bge_m3_embedding(texts: List[str]) -> List[List[float]]:
    """
    使用BGE-M3模型生成文本向量
    
    Args:
        texts: 文本列表
        
    Returns:
        向量列表，每个向量维度为1024
    """
    embeddings = []
    for i, text in enumerate(texts):
        try:
            print(f"🧠 正在生成第 {i+1}/{len(texts)} 条文本的向量: {text[:50]}...")
            response = ollama.embeddings(model="bge-m3", prompt=text)
            embedding = response.get("embedding")
            if not embedding:
                raise ValueError(f"第 {i+1} 条文本未返回 embedding")
            if len(embedding) != 1024:
                print(f"⚠️ 向量维度异常: 期望 1024，实际 {len(embedding)}")
            embeddings.append(embedding)
        except Exception as e:
            print(f"❌ 生成第 {i+1} 条文本向量失败: {e}")
            raise
    print(f"✅ 成功生成 {len(embeddings)} 个向量")
    return embeddings


def get_image_embedder():
    """获取或初始化图片嵌入器（缓存）"""
    global _image_embedder_cache
    if _image_embedder_cache is None:
        try:
            _image_embedder_cache = MilvusSearchEngine()
            print("✅ 图片嵌入器初始化成功")
        except Exception as e:
            print(f"⚠️ 无法初始化图片嵌入器: {e}")
            _image_embedder_cache = False  # 标记为不可用
    
    return _image_embedder_cache if _image_embedder_cache is not False else None


def is_image_file(file_path: str) -> bool:
    """检查文件是否是图片文件"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    ext = Path(file_path).suffix.lower()
    return ext in image_extensions


def extract_image_files(file_urls: List[str]) -> List[str]:
    """从文件URL列表中提取可用的本地图片文件"""
    image_files = []
    for url in file_urls:
        # 处理本地图片文件和静态目录中的图片
        if is_image_file(url):
            # 处理绝对路径
            if os.path.isfile(url):
                image_files.append(url)
            # 处理静态目录中的图片（如 /static/images/xxx.jpg）
            elif url.startswith('/static/images/'):
                # 转换为绝对路径
                static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
                absolute_path = os.path.join(static_dir, url[8:])  # 去掉 '/static/' 前缀
                if os.path.isfile(absolute_path):
                    image_files.append(absolute_path)
    return image_files


def create_zero_vector(dim: int) -> List[float]:
    """创建指定维度的零向量，用于替代None值"""
    return [0.0] * dim


def embedding(data: dict) -> list[dict]:
    """
    根据schema生成embedding列表
    
    Args:
        data: 输入数据字典
        
    Returns:
        列表，每个元素是一条Milvus记录
        
    示例：
        data = {
            "type": "1",
            "object": "智能客服",
            "purpose": "提升客户满意度",
            "customer_type": "电商平台用户",
            "keyword": ["智能客服系统", "自然语言处理", "机器学习"],
            "problem": ["客户等待时间长", "客服响应不及时"],
            "reply_logic": "根据客户问题匹配相关知识库内容，提供准确回复",
            "feature_explanation": "智能客服系统通过自然语言处理和机器学习技术...",
            "example": "例如，客户询问订单状态...",
            "notes": "确保知识库内容的准确性...",
            "image_url": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
            "file_url": ["https://example.com/file1.pdf", "https://example.com/file2.pdf"]
        }
    """
    results = []
    
    # 生成/复用 doc_id（编辑重建时复用原 doc_id）
    doc_id = str(data.get("doc_id") or "").strip() or str(uuid.uuid4())
    chunk_id = 0
    
    # 收集所有附件地址
    all_urls = data.get("file_url", []) + data.get("image_url", [])
    final_file_urls = ";".join(all_urls)
    
    meta_type = str(data.get("type") or "").strip()
    meta_object = str(data.get("object") or "").strip()
    meta_purpose = str(data.get("purpose") or "").strip()
    meta_customer_type = str(data.get("customer_type") or "").strip()
    raw_web_links = data.get("web_links", [])
    if isinstance(raw_web_links, str):
        web_link_items = [s.strip() for s in raw_web_links.replace("\n", ";").split(";") if s.strip()]
    elif isinstance(raw_web_links, list):
        web_link_items = [str(s).strip() for s in raw_web_links if str(s).strip()]
    else:
        web_link_items = []
    meta_web_links = ";".join(dict.fromkeys(web_link_items))

    # 收集待嵌入的字段及其权重
    fields_to_embed = []

    if "keyword" in data and data["keyword"]:
        keyword_val = data["keyword"]
        if isinstance(keyword_val, list):
            keyword_text = "，".join([str(x).strip() for x in keyword_val if str(x).strip()])
        else:
            keyword_text = str(keyword_val).strip()
        if keyword_text:
            fields_to_embed.append(("keyword", keyword_text, 1.3))
    
    # 处理problem字段（核心）
    if "problem" in data and data["problem"]:
        problems = data["problem"] if isinstance(data["problem"], list) else [data["problem"]]
        for problem_text in problems:
            if problem_text and isinstance(problem_text, str):
                fields_to_embed.append(("problem", problem_text, 1))
    
    # 处理reply_logic字段
    if "reply_logic" in data and data["reply_logic"]:
        fields_to_embed.append(("reply_logic", data["reply_logic"], 1))
    
    # 处理feature_explanation字段
    if "feature_explanation" in data and data["feature_explanation"]:
        fields_to_embed.append(("feature_explanation", data["feature_explanation"], 1))
    
    # 处理可选的example字段
    if "example" in data and data["example"]:
        fields_to_embed.append(("example", data["example"], 1))

    # 处理可选的notes字段
    if "notes" in data and data["notes"]:
        fields_to_embed.append(("notes", data["notes"],1))
    
    # 一次性生成所有文本的embedding
    if fields_to_embed:
        texts = [field[1] for field in fields_to_embed]
        embeddings = bge_m3_embedding(texts)
        
        # 组合结果
        for (field_type, field_text, weight), text_embedding in zip(fields_to_embed, embeddings):
            chunk_id += 1
            results.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "type": meta_type,
                "object": meta_object,
                "purpose": meta_purpose,
                "customer_type": meta_customer_type,
                "field_type": field_type,
                "field_text": field_text,
                "text_embedding": text_embedding,
                "vl_embedding": create_zero_vector(2048),  # 使用零向量替代None，维度与schema一致
                "weight": weight,
                "file_url": final_file_urls,
                "web_links": meta_web_links,
            })
    
    # 处理图片embedding（多模态支持）
    image_files = extract_image_files(all_urls)
    if image_files:
        embedder = get_image_embedder()
        if embedder:
            try:
                print(f"🖼️ 正在处理 {len(image_files)} 个图片文件...")
                embeddings = embedder._embed_images(image_files)
                
                # 为每个图片生成一个chunk
                skipped_count = 0
                for image_path, vec in zip(image_files, embeddings):
                    if vec is None:
                        skipped_count += 1
                        print(f"⚠️ 跳过图片（嵌入失败）: {image_path}")
                        continue

                    chunk_id += 1
                    # 检查 vec 是否已经是列表格式
                    if isinstance(vec, list):
                        vec_list = vec
                    else:
                        # 处理可能的张量情况
                        vec_list = vec.detach().cpu().float().numpy().tolist() if hasattr(vec, 'detach') else vec.tolist()

                    # 不允许零向量/近零向量入库
                    norm = math.sqrt(sum(float(x) * float(x) for x in vec_list))
                    if norm < 1e-8:
                        skipped_count += 1
                        print(f"⚠️ 跳过图片（零向量）: {image_path}")
                        continue
                    
                    results.append({
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "type": meta_type,
                        "object": meta_object,
                        "purpose": meta_purpose,
                        "customer_type": meta_customer_type,
                        "field_type": "image",
                        "field_text": '',
                        "text_embedding": create_zero_vector(1024),  # 使用零向量替代None，维度与schema一致
                        "vl_embedding": vec_list,
                        "weight": 1,
                        "file_url": image_path,
                        "web_links": meta_web_links,
                    })
                print(f"✅ 成功处理图片向量: {len(image_files) - skipped_count}/{len(image_files)}")
            except Exception as e:
                print(f"❌ 处理图片嵌入失败: {e}")
    
    # TODO: vl_embedding
    # 视觉内容部分的嵌入源自于file_url字段, 该字段有可能指向不同的文件数量与类型
    # 若涉及到txt，word，pdf等可转文字的文件，仅视觉处理或许不够，有可能需要转文本后再分片
    # 若涉及到图片，视频等视觉内容，则vl_embedding可以附带在每一个文本chunk中，增强单个chunk的召回概率；也可以chunk中仅有vl_embedding，以此召回doc
    # 但是以上情况均需要考虑何时何种情况将vl_embedding附带在文本chunk中，何时何种情况单独成chunk
    # 若涉及到多个文件，则需要将每个文件作为一个chunk
    # 暂定，优先保证原有业务的稳定性
    return results
