#!/usr/bin/env python3
"""
Orchestration Service - Plan F

負責協調多個 Agent，完成一個完整的資料處理管道。
"""

import httpx
import asyncio
from typing import Dict, Any
import json # Added for json.load
from datetime import datetime
from pathlib import Path

from common.models import PostMetricsBatch
from common.config import get_auth_file_path # 假設我們有一個共用的設定檔
from common.db_client import DatabaseClient
from common.redis_client import get_redis_client

# Agent 的 API 端點設定
# 在真實環境中，這些應該來自設定檔 (e.g., a settings module)
PLAYWRIGHT_AGENT_URL = "http://localhost:8006/v1/playwright/crawl"
JINA_AGENT_URL = "http://localhost:8004/v1/jina/enrich" # 修正端口為 8004
# VISION_AGENT_URL = "http://localhost:8005/v1/vision/fill" # 未來擴展

class PipelineService:
    """
    協調服務，用於執行多階段的資料處理管道。
    """
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.db_client = DatabaseClient()
        self.redis_client = get_redis_client()

    async def run_crawling_pipeline(self, username: str, max_posts: int) -> PostMetricsBatch:
        """
        執行標準的爬蟲與資料豐富化管道。
        流程: Playwright -> Jina
        """
        print("🚀 [Pipeline] Stage 1: Calling Playwright Agent...")
        
        # 1. 準備 Playwright Agent 的請求
        # 由 Orchestrator 負責讀取認證檔案並傳遞
        try:
            auth_file = get_auth_file_path(from_project_root=True)
            with open(auth_file, 'r', encoding='utf-8') as f:
                auth_content = json.load(f)
        except FileNotFoundError:
            print(f"❌ [Pipeline] Authentication file not found at {get_auth_file_path(from_project_root=True)}")
            raise
        
        playwright_payload = {
            "username": username, 
            "max_posts": max_posts,
            "auth_json_content": auth_content
        }

        try:
            response_p = await self.client.post(PLAYWRIGHT_AGENT_URL, json=playwright_payload, timeout=300)
            response_p.raise_for_status()
            batch_v1_data = response_p.json()
            batch_v1 = PostMetricsBatch(**batch_v1_data)
            print(f"✅ [Pipeline] Playwright Agent completed. Got {len(batch_v1.posts)} posts.")
        except httpx.HTTPStatusError as e:
            print(f"❌ [Pipeline] Playwright Agent failed with status {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"❌ [Pipeline] Failed to call or parse Playwright Agent response: {e}")
            raise

        print("\n🚀 [Pipeline] Stage 2: Calling Jina Agent for enrichment...")

        # 2. 呼叫 Jina Agent
        try:
            # Pydantic v2 的 model_dump() 預設會將 datetime 轉為字串，但我們需要確保格式正確
            # 最穩健的方式是使用 model_dump_json()，它會處理好所有序列化
            batch_v1_json_str = batch_v1.model_dump_json()

            response_j = await self.client.post(
                JINA_AGENT_URL, 
                content=batch_v1_json_str,
                headers={"Content-Type": "application/json"},
                timeout=900  # 增加到 15 分鐘，適應優化後的速率控制處理時間
            )
            response_j.raise_for_status()
            batch_v2_data = response_j.json()
            batch_v2 = PostMetricsBatch(**batch_v2_data)
            
            # 簡單比較一下豐富化前後的變化
            enriched_count = 0
            if batch_v1.posts and batch_v2.posts:
                # 確保索引在範圍內
                if len(batch_v1.posts) > 0 and len(batch_v2.posts) > 0:
                    if batch_v2.posts[0].views_count is not None and batch_v1.posts[0].views_count is None:
                        enriched_count = sum(1 for post in batch_v2.posts if post.views_count is not None)
            
            print(f"✅ [Pipeline] Jina Agent completed. Enriched {enriched_count} posts with views.")
            
            # 🗄️ 存儲最終結果到資料庫、Redis 和 JSON 檔案
            print("\n💾 [Pipeline] Stage 3: Saving results to database, cache, and JSON file...")
            await self._save_batch_results(batch_v2)
            json_file_path = self._save_to_json(batch_v2)
            print(f"✅ [Pipeline] Results saved successfully.")
            print(f"📄 [Pipeline] JSON file saved to: {json_file_path}")
            
        except httpx.HTTPStatusError as e:
            print(f"❌ [Pipeline] Jina Agent failed with status {e.response.status_code}: {e.response.text}")
            # 即使 Jina 失敗，我們仍然可以存儲和回傳 Playwright 的結果
            json_file_path = self._save_to_json(batch_v1)
            print(f"📄 [Pipeline] Playwright-only results saved to: {json_file_path}")
            return batch_v1
        except Exception as e:
            print(f"❌ [Pipeline] Failed to call or parse Jina Agent response: {e}")
            print(f"💡 [Pipeline] 錯誤詳情: {type(e).__name__}")
            # 同樣，存儲和回傳 v1 的結果
            json_file_path = self._save_to_json(batch_v1)
            print(f"📄 [Pipeline] Playwright-only results saved to: {json_file_path}")
            return batch_v1

        return batch_v2

    async def _save_batch_results(self, batch: PostMetricsBatch) -> None:
        """
        將批次結果存儲到資料庫和 Redis
        """
        try:
            # 初始化資料庫連接池
            await self.db_client.init_pool()
            
            # 準備批次數據
            posts_data = []
            metrics_data = []
            
            for post in batch.posts:
                # 貼文基本資料
                posts_data.append({
                    "url": post.url,
                    "author": post.username,
                    "markdown": post.content,
                    "media_urls": post.media_urls or []
                })
                
                # 指標資料
                metrics_data.append({
                    "url": post.url,
                    "views": post.views_count,
                    "likes": post.likes_count,
                    "comments": post.comments_count,
                    "reposts": post.reposts_count,
                    "shares": post.shares_count
                })
                
                # 存到 Redis 快取
                redis_metrics = {
                    "views": post.views_count or 0,
                    "likes": post.likes_count or 0,
                    "comments": post.comments_count or 0,
                    "reposts": post.reposts_count or 0,
                    "shares": post.shares_count or 0
                }
                self.redis_client.set_post_metrics(post.url, redis_metrics)
            
            # 批次存入 PostgreSQL
            posts_saved = await self.db_client.batch_upsert_posts(posts_data)
            metrics_saved = await self.db_client.batch_upsert_metrics(metrics_data)
            
            print(f"💾 [Pipeline] Saved {posts_saved} posts and {metrics_saved} metrics to database")
            print(f"⚡ [Pipeline] Cached {len(batch.posts)} posts to Redis")
            
        except Exception as e:
            print(f"❌ [Pipeline] Failed to save results: {e}")
            # 不拋出異常，因為處理已經完成，只是存儲失敗

    def _save_to_json(self, batch: PostMetricsBatch) -> str:
        """
        將批次結果存儲為 JSON 檔案，方便即時查看
        """
        try:
            # 創建輸出目錄
            output_dir = Path("pipeline_results")
            output_dir.mkdir(exist_ok=True)
            
            # 生成檔案名（包含時間戳和用戶名）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pipeline_results_{batch.username}_{timestamp}.json"
            file_path = output_dir / filename
            
            # 準備 JSON 數據
            result_data = {
                "batch_info": {
                    "batch_id": batch.batch_id,
                    "username": batch.username,
                    "total_posts": len(batch.posts),
                    "processing_stage": batch.processing_stage,
                    "timestamp": timestamp
                },
                "posts": []
            }
            
            # 添加每個貼文的詳細資料
            for post in batch.posts:
                post_data = {
                    "url": post.url,
                    "post_id": post.post_id,
                    "username": post.username,
                    "metrics": {
                        "views_count": post.views_count,
                        "likes_count": post.likes_count,
                        "comments_count": post.comments_count,
                        "reposts_count": post.reposts_count,
                        "shares_count": post.shares_count,
                        "calculated_score": post.calculate_score()
                    },
                    "content": {
                        "text": post.content[:200] + "..." if post.content and len(post.content) > 200 else post.content,
                        "media_urls": post.media_urls or []
                    },
                    "metadata": {
                        "source": post.source,
                        "processing_stage": post.processing_stage,
                        "is_complete": post.is_complete,
                        "last_updated": post.last_updated.isoformat() if post.last_updated else None,
                        "created_at": post.created_at.isoformat() if post.created_at else None
                    }
                }
                result_data["posts"].append(post_data)
            
            # 排序貼文（按分數降序）
            result_data["posts"].sort(key=lambda x: x["metrics"]["calculated_score"], reverse=True)
            
            # 寫入 JSON 檔案
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
            return str(file_path.absolute())
            
        except Exception as e:
            print(f"❌ [Pipeline] Failed to save JSON file: {e}")
            return "JSON save failed"

# --- 測試用的主函數 ---
async def main():
    """
    一個簡單的測試函數，用於演示如何使用 PipelineService。
    """
    print("===== Running Pipeline Test =====")
    test_username = "starettoday"  # 🔄 修改這裡: 例如 "zuck", "elonmusk", "instagram" 等
    test_max_posts = 100       # 🔄 修改這裡: 例如 20, 50, 100 等 (建議不超過 50)

    async with httpx.AsyncClient() as client:
        pipeline = PipelineService(client)
        try:
            final_batch = await pipeline.run_crawling_pipeline(test_username, test_max_posts)
            
            print("\n✅✅✅ Pipeline Completed Successfully! ✅✅✅")
            print("-" * 50)
            print("Final Batch Summary:")
            print(f"  - Batch ID: {final_batch.batch_id}")
            print(f"  - Username: {final_batch.username}")
            print(f"  - Total Posts: {len(final_batch.posts)}")
            print(f"  - Final Stage: {final_batch.processing_stage}")
            
            if final_batch.posts:
                print("\n--- Sample of Final Enriched Post ---")
                sample_post = final_batch.posts[0]
                print(f"  URL: {sample_post.url}")
                print(f"  Post ID: {sample_post.post_id}")
                print(f"  Likes: {sample_post.likes_count}")
                print(f"  Comments: {sample_post.comments_count}")
                print(f"  Views (from Jina): {sample_post.views_count}")
                print(f"  Content Preview: {sample_post.content[:80] if sample_post.content else 'N/A'}...")
            print("-" * 50)

        except Exception as e:
            print(f"\n❌❌❌ Pipeline Failed: {e} ❌❌❌")

if __name__ == "__main__":
    # 確保 common.models 在 sys.path 中
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    
    asyncio.run(main()) 