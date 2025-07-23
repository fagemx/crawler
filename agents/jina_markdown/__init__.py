"""
Jina Markdown Agent 模組

Plan E 架構中的專門 Agent，負責：
- 使用 Jina Reader Markdown 解析貼文
- 提取社交媒體指標
- 寫入 Redis (Tier-0) 和 PostgreSQL (Tier-1)
- 標記需要 Vision 補值的貼文
"""

from .jina_markdown_logic import (
    JinaMarkdownAgent,
    create_jina_markdown_agent,
    process_posts_batch,
    health_check
)

__all__ = [
    "JinaMarkdownAgent",
    "create_jina_markdown_agent", 
    "process_posts_batch",
    "health_check"
]