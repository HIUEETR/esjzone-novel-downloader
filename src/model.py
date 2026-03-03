from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chapter:
    url: str
    title: str
    index: int
    section_name: Optional[str] = None
    section_index: Optional[int] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: dict[str, bytes] = field(default_factory=dict)


@dataclass
class Book:
    url: str
    title: str
    author: str
    introduction: str
    cover_url: Optional[str] = None
    cover_image: Optional[bytes] = None
    update_time: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)
