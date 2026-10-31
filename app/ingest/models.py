from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class Document(BaseModel):
    url: str
    title: Optional[str] = None
    text: str = ""
    published_date: Optional[str] = None
    date_origin: str = "none"  # 'meta', 'header', 'url', 'body', 'pasted', 'none'
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    content_hash: str = ""
    status: str = "ok"  # 'ok', 'blocked', 'unreachable', 'disallowed', 'error'
    error: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
