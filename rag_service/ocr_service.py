# -*- coding: utf-8 -*-
import io
import logging
from typing import List

import numpy as np
from PIL import Image
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self):
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            from paddleocr import PaddleOCR

            self.engine = PaddleOCR(
                lang="ch",
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_name="PP-OCRv5_server_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
            )
            logger.info("✅ OCR 引擎初始化成功")
        except Exception as exc:
            logger.warning("⚠️ OCR 引擎初始化失败，检索仍可用: %s", exc)
            self.engine = None

    async def extract_query_from_images(self, files: List[UploadFile]) -> str:
        if not self.engine:
            return ""

        ocr_texts: List[str] = []
        for file in files:
            if not (file.content_type or "").startswith("image/"):
                continue
            try:
                image_bytes = await file.read()
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                np_img = np.array(img)
                results = self.engine.predict(np_img)
                for res in results:
                    texts = res.get("rec_texts", [])
                    scores = res.get("rec_scores", [])
                    for text, confidence in zip(texts, scores):
                        if confidence > 0.5:
                            ocr_texts.append(text.strip())
            except Exception as exc:
                logger.error("处理文件 %s 时出错：%s", file.filename, exc)
                continue

        return "\n".join(ocr_texts) if ocr_texts else ""
