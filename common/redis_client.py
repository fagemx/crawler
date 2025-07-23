"""
Redis 客戶端模組

基於 Plan E 三層資料策略的 Redis 操作封裝
- Tier-0: 臨時快取（指標、排序、任務狀態）
- TTL 管理
- 批次操作優化
"""

import json
import redis
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import asdict

from .settings import get_settings


class RedisClient:
    """Redis 客戶端 - Plan E 三層策略實現"""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_pool = redis.ConnectionPool.from_url(
            self.settings.redis.url,
            max_connections=self.settings.redis.max_connections,
            decode_responses=True
        )
        self.redis = redis.Redis(connection_pool=self.redis_pool)
        
        # Plan E TTL 設定
        self.TTL_METRICS = 30 * 24 * 3600  # 30 天
        self.TTL_RANKING = 10 * 60         # 10 分鐘
        self.TTL_TASK = 3600               # 1 小時
    
    # ============================================================================
    # Tier-0: 指標快取 (metrics:{url})
    # ============================================================================
    
    def set_post_metrics(self, url: str, metrics: Dict[str, Union[int, float]]) -> bool:
        """
        設置貼文指標到 Redis
        
        Args:
            url: 貼文 URL
            metrics: 指標字典 {views, likes, comments, reposts, shares}
            
        Returns:
            bool: 是否成功
        """
        try:
            key = f"metrics:{url}"
            
            # 確保所有值都是數字
            clean_metrics = {}
            for k, v in metrics.items():
                if v is not None:
                    clean_metrics[k] = int(v) if isinstance(v, (int, float)) else 0
                else:
                    clean_metrics[k] = 0
            
            # 批次設置
            pipe = self.redis.pipeline()
            pipe.hset(key, mapping=clean_metrics)
            pipe.expire(key, self.TTL_METRICS)
            pipe.execute()
            
            return True
            
        except Exception as e:
            print(f"設置指標失敗 {url}: {e}")
            return False
    
    def get_post_metrics(self, url: str) -> Optional[Dict[str, int]]:
        """
        獲取貼文指標
        
        Args:
            url: 貼文 URL
            
        Returns:
            Dict[str, int]: 指標字典，如果不存在返回 None
        """
        try:
            key = f"metrics:{url}"
            metrics = self.redis.hgetall(key)
            
            if not metrics:
                return None
            
            # 轉換為整數
            return {k: int(v) for k, v in metrics.items()}
            
        except Exception as e:
            print(f"獲取指標失敗 {url}: {e}")
            return None
    
    def batch_get_metrics(self, urls: List[str]) -> Dict[str, Dict[str, int]]:
        """
        批次獲取多個貼文的指標
        
        Args:
            urls: URL 列表
            
        Returns:
            Dict[str, Dict[str, int]]: URL -> 指標字典
        """
        try:
            if not urls:
                return {}
            
            pipe = self.redis.pipeline()
            for url in urls:
                pipe.hgetall(f"metrics:{url}")
            
            results = pipe.execute()
            
            # 組合結果
            metrics_dict = {}
            for i, url in enumerate(urls):
                if results[i]:
                    metrics_dict[url] = {k: int(v) for k, v in results[i].items()}
            
            return metrics_dict
            
        except Exception as e:
            print(f"批次獲取指標失敗: {e}")
            return {}
    
    def get_user_metrics_keys(self, username: str) -> List[str]:
        """
        獲取用戶的所有指標 key
        
        Args:
            username: 用戶名
            
        Returns:
            List[str]: key 列表
        """
        try:
            pattern = f"metrics:https://www.threads.com/@{username}/*"
            return self.redis.keys(pattern)
            
        except Exception as e:
            print(f"獲取用戶指標 key 失敗 {username}: {e}")
            return []
    
    # ============================================================================
    # Tier-0: 排序快取 (ranking:{username})
    # ============================================================================
    
    def set_user_ranking(self, username: str, ranked_urls: List[str]) -> bool:
        """
        設置用戶的排序結果
        
        Args:
            username: 用戶名
            ranked_urls: 按分數排序的 URL 列表
            
        Returns:
            bool: 是否成功
        """
        try:
            key = f"ranking:{username}"
            
            # 使用 sorted set 存儲排序
            pipe = self.redis.pipeline()
            pipe.delete(key)  # 清除舊數據
            
            for i, url in enumerate(ranked_urls):
                # 分數越高排名越前，所以用負數索引
                score = len(ranked_urls) - i
                pipe.zadd(key, {url: score})
            
            pipe.expire(key, self.TTL_RANKING)
            pipe.execute()
            
            return True
            
        except Exception as e:
            print(f"設置排序失敗 {username}: {e}")
            return False
    
    def get_user_ranking(self, username: str, limit: int = 30) -> List[str]:
        """
        獲取用戶的排序結果
        
        Args:
            username: 用戶名
            limit: 返回數量限制
            
        Returns:
            List[str]: 排序的 URL 列表
        """
        try:
            key = f"ranking:{username}"
            # 按分數降序獲取
            return self.redis.zrevrange(key, 0, limit - 1)
            
        except Exception as e:
            print(f"獲取排序失敗 {username}: {e}")
            return []
    
    # ============================================================================
    # Tier-0: 任務狀態快取 (task:{task_id})
    # ============================================================================
    
    def set_task_status(self, task_id: str, status: Dict[str, Any]) -> bool:
        """
        設置任務狀態
        
        Args:
            task_id: 任務 ID
            status: 狀態字典
            
        Returns:
            bool: 是否成功
        """
        try:
            key = f"task:{task_id}"
            
            # 添加時間戳
            status_with_time = {
                **status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            pipe = self.redis.pipeline()
            pipe.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                                   for k, v in status_with_time.items()})
            pipe.expire(key, self.TTL_TASK)
            pipe.execute()
            
            return True
            
        except Exception as e:
            print(f"設置任務狀態失敗 {task_id}: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取任務狀態
        
        Args:
            task_id: 任務 ID
            
        Returns:
            Dict[str, Any]: 狀態字典，如果不存在返回 None
        """
        try:
            key = f"task:{task_id}"
            status = self.redis.hgetall(key)
            
            if not status:
                return None
            
            # 解析 JSON 值
            parsed_status = {}
            for k, v in status.items():
                try:
                    parsed_status[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed_status[k] = v
            
            return parsed_status
            
        except Exception as e:
            print(f"獲取任務狀態失敗 {task_id}: {e}")
            return None
    
    # ============================================================================
    # 批次處理佇列
    # ============================================================================
    
    def push_to_queue(self, queue_name: str, items: List[str]) -> int:
        """
        推送項目到佇列
        
        Args:
            queue_name: 佇列名稱 (如 'jina_markdown', 'vision_fill')
            items: 項目列表
            
        Returns:
            int: 推送的項目數量
        """
        try:
            key = f"queue:{queue_name}"
            
            if not items:
                return 0
            
            return self.redis.lpush(key, *items)
            
        except Exception as e:
            print(f"推送到佇列失敗 {queue_name}: {e}")
            return 0
    
    def pop_from_queue(self, queue_name: str, count: int = 1) -> List[str]:
        """
        從佇列彈出項目
        
        Args:
            queue_name: 佇列名稱
            count: 彈出數量
            
        Returns:
            List[str]: 彈出的項目列表
        """
        try:
            key = f"queue:{queue_name}"
            
            items = []
            for _ in range(count):
                item = self.redis.rpop(key)
                if item:
                    items.append(item)
                else:
                    break
            
            return items
            
        except Exception as e:
            print(f"從佇列彈出失敗 {queue_name}: {e}")
            return []
    
    def get_queue_length(self, queue_name: str) -> int:
        """
        獲取佇列長度
        
        Args:
            queue_name: 佇列名稱
            
        Returns:
            int: 佇列長度
        """
        try:
            key = f"queue:{queue_name}"
            return self.redis.llen(key)
            
        except Exception as e:
            print(f"獲取佇列長度失敗 {queue_name}: {e}")
            return 0
    
    # ============================================================================
    # 工具方法
    # ============================================================================
    
    def calculate_score(self, metrics: Dict[str, int]) -> float:
        """
        計算 Plan E 權重分數
        
        Args:
            metrics: 指標字典
            
        Returns:
            float: 權重分數
        """
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        comments = metrics.get("comments", 0)
        reposts = metrics.get("reposts", 0)
        shares = metrics.get("shares", 0)
        
        return (
            views * 1.0 +
            likes * 0.3 +
            comments * 0.3 +
            reposts * 0.1 +
            shares * 0.1
        )
    
    def rank_user_posts(self, username: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        對用戶貼文進行排序（Plan E 核心邏輯）
        
        Args:
            username: 用戶名
            limit: 返回數量限制
            
        Returns:
            List[Dict[str, Any]]: 排序後的貼文列表，包含 URL 和分數
        """
        try:
            # 獲取用戶的所有指標 key
            keys = self.get_user_metrics_keys(username)
            
            if not keys:
                return []
            
            # 批次獲取指標
            pipe = self.redis.pipeline()
            for key in keys:
                pipe.hgetall(key)
            
            results = pipe.execute()
            
            # 計算分數並排序
            scored_posts = []
            for i, key in enumerate(keys):
                if results[i]:
                    url = key.replace("metrics:", "")
                    metrics = {k: int(v) for k, v in results[i].items()}
                    score = self.calculate_score(metrics)
                    
                    scored_posts.append({
                        "url": url,
                        "metrics": metrics,
                        "score": score
                    })
            
            # 按分數降序排序
            scored_posts.sort(key=lambda x: x["score"], reverse=True)
            
            # 快取排序結果
            ranked_urls = [post["url"] for post in scored_posts[:limit]]
            self.set_user_ranking(username, ranked_urls)
            
            return scored_posts[:limit]
            
        except Exception as e:
            print(f"排序用戶貼文失敗 {username}: {e}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康檢查
        
        Returns:
            Dict[str, Any]: 健康狀態
        """
        try:
            # 測試連接
            self.redis.ping()
            
            # 獲取基本信息
            info = self.redis.info()
            
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "total_commands_processed": info.get("total_commands_processed")
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    def cleanup_expired_keys(self) -> int:
        """
        清理過期的 key（手動清理）
        
        Returns:
            int: 清理的 key 數量
        """
        try:
            cleaned = 0
            
            # 清理過期的任務狀態
            task_keys = self.redis.keys("task:*")
            for key in task_keys:
                ttl = self.redis.ttl(key)
                if ttl == -1:  # 沒有設置 TTL
                    self.redis.expire(key, self.TTL_TASK)
                elif ttl == -2:  # 已過期
                    self.redis.delete(key)
                    cleaned += 1
            
            return cleaned
            
        except Exception as e:
            print(f"清理過期 key 失敗: {e}")
            return 0


# 全域 Redis 客戶端實例
_redis_client = None


def get_redis_client() -> RedisClient:
    """獲取 Redis 客戶端實例（單例模式）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


# 便利函數
def set_post_metrics(url: str, metrics: Dict[str, Union[int, float]]) -> bool:
    """設置貼文指標的便利函數"""
    return get_redis_client().set_post_metrics(url, metrics)


def get_post_metrics(url: str) -> Optional[Dict[str, int]]:
    """獲取貼文指標的便利函數"""
    return get_redis_client().get_post_metrics(url)


def rank_user_posts(username: str, limit: int = 30) -> List[Dict[str, Any]]:
    """排序用戶貼文的便利函數"""
    return get_redis_client().rank_user_posts(username, limit)


if __name__ == "__main__":
    # 測試 Redis 連接
    client = get_redis_client()
    health = client.health_check()
    print(f"Redis 健康狀態: {health}")