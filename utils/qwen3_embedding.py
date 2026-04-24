# -*- coding: utf-8 -*-
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Union

import torch
import torch.nn.functional as F
from PIL import Image
from transformers.models.qwen3_vl.processing_qwen3_vl import Qwen3VLProcessor

from .qwen3_modeling import (
    FPS,
    MAX_FRAMES,
    MAX_LENGTH,
    MAX_PIXELS,
    MAX_TOTAL_PIXELS,
    MIN_PIXELS,
    Qwen3VLForEmbedding,
    is_video_input,
    sample_frames,
)

try:
    from qwen_vl_utils.vision_process import process_vision_info
except ImportError:
    from .qwen_vl_utils_stub import process_vision_info

logger = logging.getLogger(__name__)


class Qwen3VLEmbedder:
    def __init__(
        self,
        model_name_or_path: str,
        max_length: int = MAX_LENGTH,
        min_pixels: int = MIN_PIXELS,
        max_pixels: int = MAX_PIXELS,
        total_pixels: int = MAX_TOTAL_PIXELS,
        fps: float = FPS,
        max_frames: int = MAX_FRAMES,
        default_instruction: str = "Represent the user's input.",
        **kwargs,
    ):
        # Keep device selection aligned with upstream behavior:
        # use the default CUDA device when available.
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.total_pixels = total_pixels
        self.fps = fps
        self.max_frames = max_frames
        self.default_instruction = default_instruction

        self.model = Qwen3VLForEmbedding.from_pretrained(
            model_name_or_path,
            trust_remote_code=True,
            **kwargs,
        ).to(device)
        self.processor = Qwen3VLProcessor.from_pretrained(model_name_or_path, padding_side="right")
        self.model.eval()

    @torch.no_grad()
    def forward(self, inputs: Dict[str, Any]) -> Dict[str, torch.Tensor]:
        outputs = self.model(**inputs)
        return {
            "last_hidden_state": outputs.last_hidden_state,
            "attention_mask": inputs.get("attention_mask"),
        }

    def format_model_input(
        self,
        text: Optional[Union[List[str], str]] = None,
        image: Optional[Union[List[Union[str, Image.Image]], str, Image.Image]] = None,
        video: Optional[Union[List[Union[str, List[Union[str, Image.Image]]]], str, List[Union[str, Image.Image]]]] = None,
        instruction: Optional[str] = None,
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> List[Dict]:
        if instruction:
            instruction = instruction.strip()
            if instruction and not unicodedata.category(instruction[-1]).startswith("P"):
                instruction += "."

        content = []
        conversation = [
            {"role": "system", "content": [{"type": "text", "text": instruction or self.default_instruction}]},
            {"role": "user", "content": content},
        ]

        texts = [] if text is None else ([text] if isinstance(text, str) else text)
        images = [] if image is None else ([image] if not isinstance(image, list) else image)
        if video is None:
            videos = []
        elif is_video_input(video):
            videos = [video]
        else:
            videos = video

        if not texts and not images and not videos:
            content.append({"type": "text", "text": "NULL"})
            return conversation

        for vid in videos:
            if isinstance(vid, list):
                sampled = sample_frames(vid, self.max_frames) if self.max_frames is not None else vid
                video_content = [("file://" + ele if isinstance(ele, str) else ele) for ele in sampled]
                content.append({"type": "video", "video": video_content, "total_pixels": self.total_pixels})
                continue
            if isinstance(vid, str):
                video_content = vid if vid.startswith(("http://", "https://")) else "file://" + vid
                content.append(
                    {
                        "type": "video",
                        "video": video_content,
                        "fps": fps or self.fps,
                        "max_frames": max_frames or self.max_frames,
                    }
                )
                continue
            raise TypeError(f"Unrecognized video type: {type(vid)}")

        for img in images:
            if isinstance(img, Image.Image):
                image_content = img
            elif isinstance(img, str):
                image_content = img if img.startswith(("http://", "https://")) else "file://" + img
            else:
                raise TypeError(f"Unrecognized image type: {type(img)}")
            content.append(
                {
                    "type": "image",
                    "image": image_content,
                    "min_pixels": self.min_pixels,
                    "max_pixels": self.max_pixels,
                }
            )

        for txt in texts:
            content.append({"type": "text", "text": txt})

        return conversation

    def _preprocess_inputs(self, conversations: List[List[Dict]]) -> Dict[str, torch.Tensor]:
        text = self.processor.apply_chat_template(conversations, add_generation_prompt=True, tokenize=False)

        try:
            images, video_inputs, video_kwargs = process_vision_info(
                conversations,
                image_patch_size=16,
                return_video_metadata=True,
                return_video_kwargs=True,
            )
        except Exception as exc:
            logger.error("Error in processing vision info: %s", exc)
            images, video_inputs, video_kwargs = None, None, {"do_sample_frames": False}
            text = self.processor.apply_chat_template(
                [{"role": "user", "content": [{"type": "text", "text": "NULL"}]}],
                add_generation_prompt=True,
                tokenize=False,
            )

        if video_inputs is not None:
            videos, video_metadata = zip(*video_inputs)
            videos, video_metadata = list(videos), list(video_metadata)
        else:
            videos, video_metadata = None, None

        return self.processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadata,
            truncation=True,
            max_length=self.max_length,
            padding=True,
            do_resize=False,
            return_tensors="pt",
            **video_kwargs,
        )

    @staticmethod
    def _pooling_last(hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        flipped_tensor = attention_mask.flip(dims=[1])
        last_one_positions = flipped_tensor.argmax(dim=1)
        col = attention_mask.shape[1] - last_one_positions - 1
        row = torch.arange(hidden_state.shape[0], device=hidden_state.device)
        return hidden_state[row, col]

    def process(self, inputs: List[Dict[str, Any]], normalize: bool = True):
        conversations = [
            self.format_model_input(
                text=ele.get("text"),
                image=ele.get("image"),
                video=ele.get("video"),
                instruction=ele.get("instruction"),
                fps=ele.get("fps"),
                max_frames=ele.get("max_frames"),
            )
            for ele in inputs
        ]
        processed_inputs = self._preprocess_inputs(conversations)
        processed_inputs = {k: v.to(self.model.device) for k, v in processed_inputs.items()}

        outputs = self.forward(processed_inputs)
        embeddings = self._pooling_last(outputs["last_hidden_state"], outputs["attention_mask"])
        if normalize:
            embeddings = F.normalize(embeddings, p=2, dim=-1)
        return embeddings
