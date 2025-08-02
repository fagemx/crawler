"""
貼文去重工具

處理主貼文 vs 回應的重複問題，基於多維度判斷保留主貼文
"""

import logging
from typing import List, Dict, Set
from collections import defaultdict
from common.models import PostMetrics


class PostDeduplicator:
    """
    貼文去重器 - 識別並保留主貼文，過濾回應
    """
    
    @staticmethod
    def deduplicate_posts(posts: List[PostMetrics]) -> List[PostMetrics]:
        """
        去重邏輯：當發現相似內容時，保留主貼文
        
        判斷標準（按優先級）：
        1. views_count - 主貼文通常瀏覽數更高
        2. 綜合互動分數 - likes + comments + reposts + shares
        3. 內容長度 - 主貼文通常更詳細
        4. 時間戳 - 主貼文通常更早發布
        """
        if not posts:
            return posts
            
        # 按內容分組（處理相同用戶的相同/相似內容）
        content_groups = defaultdict(list)
        
        for post in posts:
            # 使用內容的前100字符作為分組key（處理完全相同的內容）
            content_key = post.content[:100].strip() if post.content else post.post_id
            content_groups[content_key].append(post)
        
        deduplicated_posts = []
        
        for content_key, group_posts in content_groups.items():
            if len(group_posts) == 1:
                # 單一貼文，直接保留
                deduplicated_posts.extend(group_posts)
            else:
                # 多個相似貼文，選擇主貼文
                main_post = PostDeduplicator._select_main_post(group_posts)
                deduplicated_posts.append(main_post)
                
                # 記錄去重信息
                filtered_ids = [p.post_id for p in group_posts if p.post_id != main_post.post_id]
                logging.info(f"🔄 去重：保留主貼文 {main_post.post_id}，過濾回應 {filtered_ids}")
        
        return deduplicated_posts
    
    @staticmethod
    def _select_main_post(posts: List[PostMetrics]) -> PostMetrics:
        """
        從相似貼文中選擇主貼文
        """
        def calculate_score(post: PostMetrics) -> tuple:
            """
            計算貼文重要性分數 (返回tuple用於排序)
            優先級：views_count > 互動分數 > 內容長度 > 時間戳
            """
            views_score = post.views_count or 0
            interaction_score = (
                (post.likes_count or 0) + 
                (post.comments_count or 0) + 
                (post.reposts_count or 0) + 
                (post.shares_count or 0)
            )
            content_length = len(post.content) if post.content else 0
            # 時間戳轉為負數，讓早期的貼文分數更高
            timestamp_score = -(post.created_at.timestamp() if post.created_at else 0)
            
            return (views_score, interaction_score, content_length, timestamp_score)
        
        # 按分數排序，選擇最高分的作為主貼文
        sorted_posts = sorted(posts, key=calculate_score, reverse=True)
        main_post = sorted_posts[0]
        
        # 輸出判斷依據
        for post in sorted_posts:
            score = calculate_score(post)
            logging.info(f"   📊 {post.post_id}: views={score[0]:,}, 互動={score[1]}, 內容長度={score[2]}")
        
        return main_post


def apply_deduplication(posts: List[PostMetrics]) -> List[PostMetrics]:
    """
    便捷函數：對貼文列表應用去重
    """
    original_count = len(posts)
    deduplicated = PostDeduplicator.deduplicate_posts(posts)
    
    if len(deduplicated) < original_count:
        logging.info(f"✅ 去重完成：{original_count} → {len(deduplicated)} 篇貼文")
    
    return deduplicated