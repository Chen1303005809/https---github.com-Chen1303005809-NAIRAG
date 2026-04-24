# -*- coding: utf-8 -*-
from typing import List, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class Record(BaseModel):
    object: str
    type: str
    purpose: str
    customer_type: str
    reply_logic: str
    feature_explanation: str
    example: str = ""
    notes: str = ""
    keyword: Optional[str] = None
    problem: List[str]
    image_url: List[str] = []
    file_url: List[str] = []
