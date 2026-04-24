"""
本地实现 qwen_vl_utils 的 vision_process 模块
用于处理多模态输入（文本、图像、视频）
"""

import os
from typing import List, Dict, Tuple, Any, Optional, Union
from PIL import Image


def process_vision_info(
    conversations: List[Dict[str, Any]],
    image_patch_size: int = 16,
    return_video_metadata: bool = False,
    return_video_kwargs: bool = False,
    **kwargs
) -> Union[Tuple, Tuple[None, None, Dict]]:
    """
    处理对话中的视觉信息（图像和视频）
    
    Args:
        conversations: 对话列表，包含图像/视频内容
        image_patch_size: 图像块大小
        return_video_metadata: 是否返回视频元数据
        return_video_kwargs: 是否返回视频关键字参数
        
    Returns:
        Tuple: (images, video_inputs, video_kwargs)
    """
    images = []
    video_inputs = None
    video_kwargs = {'do_sample_frames': False}
    
    try:
        # 遍历对话内容提取视觉信息
        if not conversations:
            return images if images else None, video_inputs, video_kwargs
            
        for conversation in conversations:
            if 'content' not in conversation:
                continue
                
            content = conversation['content']
            if not isinstance(content, list):
                continue
            
            for item in content:
                if not isinstance(item, dict):
                    continue
                    
                item_type = item.get('type', '')
                
                # 处理图像
                if item_type == 'image':
                    image_data = item.get('image', item.get('image_url', None))
                    if image_data:
                        if isinstance(image_data, str):
                            # 如果是URL或路径，尝试加载
                            if image_data.startswith(('http://', 'https://')):
                                images.append(image_data)
                            elif os.path.exists(image_data):
                                try:
                                    images.append(Image.open(image_data))
                                except Exception:
                                    images.append(image_data)
                        elif isinstance(image_data, Image.Image):
                            images.append(image_data)
                
                # 处理视频
                elif item_type == 'video':
                    video_data = item.get('video', item.get('video_url', None))
                    if video_data:
                        # 视频处理的占位符实现
                        if video_inputs is None:
                            video_inputs = []
                        video_inputs.append((video_data, {}))
        
        # 如果没有提取到图像，返回None
        if not images:
            images = None
            
    except Exception as e:
        # 如果处理失败，返回安全的默认值
        images = None
        video_inputs = None
        video_kwargs = {'do_sample_frames': False}
    
    return images, video_inputs, video_kwargs
