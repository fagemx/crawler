"""
欄位對照表配置

定義從各種API響應格式中提取數據的路徑映射
"""

# 強健的欄位對照表
FIELD_MAP = {
    "like_count": [
        "like_count", "likeCount", 
        ["feedback_info", "aggregated_like_count"],
        ["feedback_info", "aggregated_like_count", "count"],  # 更深層路徑
        ["like_info", "count"]
    ],
    "comment_count": [
        ["text_post_app_info", "direct_reply_count"],
        "comment_count", "commentCount",
        ["reply_info", "count"]
    ],
    "share_count": [
        ["text_post_app_info", "reshare_count"],  # 真正的 shares 欄位
        "reshareCount", "share_count", "shareCount"
    ],
    "repost_count": [
        ["text_post_app_info", "repost_count"],  # reposts 欄位
        "repostCount", "repost_count"
    ],
    "content": [
        ["caption", "text"],
        "caption", "text", "content"
    ],
    "author": [
        ["user", "username"], 
        ["owner", "username"],
        ["user", "handle"]
    ],
    "created_at": [
        "taken_at", "taken_at_timestamp", 
        "publish_date", "created_time"
    ],
    "post_id": [
        "pk", "id", "post_id"
    ],
    "code": [
        "code", "shortcode", "media_code"
    ],
    # 增加直接從 API 嘗試獲取 views 的路徑
    "view_count": [
        ["feedback_info", "view_count"],
        ["video_info", "play_count"],
        "view_count",
        "views",
        "impression_count"
    ],
}