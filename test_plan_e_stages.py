#!/usr/bin/env python3
"""
Plan E 分階段測試

測試新的 Plan E 架構的每個階段：
1. 基礎設施測試（Redis + PostgreSQL）
2. JinaMarkdown Agent 測試
3. VisionFill Agent 測試  
4. 排序功能測試
5. 端到端整合測試
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any

# 載入 .env 檔案
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ 已載入 .env 檔案")
except ImportError:
    print("⚠️ 未安裝 python-dotenv，無法載入 .env 檔案")

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.redis_client import get_redis_client
from common.db_client import get_db_client
from common.models import PostMetrics
from agents.jina_markdown.jina_markdown_logic import JinaMarkdownAgent
from agents.vision.vision_fill_logic import VisionFillAgent


class PlanEStageTest:
    """Plan E 分階段測試類"""
    
    def __init__(self):
        self.test_urls = [
            "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf",
            # 可以添加更多測試 URL
        ]
        self.test_username = "evenchen14"
        
    async def test_infrastructure(self) -> bool:
        """測試基礎設施（Redis + PostgreSQL）"""
        print("=== 階段 1: 基礎設施測試 ===")
        
        try:
            # 測試 Redis 連接
            print("測試 Redis 連接...")
            redis_client = get_redis_client()
            redis_health = redis_client.health_check()
            print(f"Redis 健康狀態: {redis_health}")
            
            if redis_health.get("status") != "healthy":
                print("❌ Redis 連接失敗")
                return False
            
            # 測試 PostgreSQL 連接
            print("測試 PostgreSQL 連接...")
            db_client = await get_db_client()
            db_health = await db_client.health_check()
            print(f"PostgreSQL 健康狀態: {db_health}")
            
            if db_health.get("status") != "healthy":
                print("❌ PostgreSQL 連接失敗")
                return False
            
            # 測試基本 Redis 操作
            print("測試 Redis 基本操作...")
            test_metrics = {
                "views": 1000,
                "likes": 50,
                "comments": 10,
                "reposts": 5,
                "shares": 2
            }
            test_url = "https://test.example.com/post/123"
            
            # 寫入測試
            redis_client.set_post_metrics(test_url, test_metrics)
            
            # 讀取測試
            retrieved_metrics = redis_client.get_post_metrics(test_url)
            print(f"Redis 讀寫測試: {retrieved_metrics}")
            
            if retrieved_metrics != test_metrics:
                print("❌ Redis 讀寫測試失敗")
                return False
            
            print("✅ 基礎設施測試通過")
            return True
            
        except Exception as e:
            print(f"❌ 基礎設施測試失敗: {e}")
            return False
    
    async def test_jina_markdown_agent(self) -> bool:
        """測試 JinaMarkdown Agent"""
        print("\n=== 階段 2: JinaMarkdown Agent 測試 ===")
        
        try:
            # 創建測試數據
            test_posts = [
                PostMetrics(
                    url=url,
                    post_id=url.split("/")[-1],
                    username=self.test_username
                ) for url in self.test_urls
            ]
            
            # 創建 Agent
            jina_agent = JinaMarkdownAgent()
            
            # 測試健康檢查
            health = await jina_agent.health_check()
            print(f"JinaMarkdown Agent 健康狀態: {health}")
            
            if health.get("status") != "healthy":
                print("❌ JinaMarkdown Agent 健康檢查失敗")
                return False
            
            # 測試單一貼文處理
            print(f"測試單一貼文處理: {test_posts[0].url}")
            result = await jina_agent.process_single_post_with_storage(
                post_url=test_posts[0].url,
                author=test_posts[0].username,
                task_id="test_single"
            )
            
            print(f"處理結果: {result}")
            
            # 驗證 Redis 中的數據
            redis_client = get_redis_client()
            redis_metrics = redis_client.get_post_metrics(test_posts[0].url)
            print(f"Redis 中的指標: {redis_metrics}")
            
            # 驗證 PostgreSQL 中的數據
            db_client = await get_db_client()
            db_post = await db_client.get_post(test_posts[0].url)
            print(f"PostgreSQL 中的貼文: {db_post is not None}")
            
            if not redis_metrics or not db_post:
                print("❌ 數據未正確寫入存儲")
                return False
            
            print("✅ JinaMarkdown Agent 測試通過")
            return True
            
        except Exception as e:
            print(f"❌ JinaMarkdown Agent 測試失敗: {e}")
            return False
    
    async def test_vision_fill_agent(self) -> bool:
        """測試 VisionFill Agent"""
        print("\n=== 階段 3: VisionFill Agent 測試 ===")
        
        try:
            # 檢查 Gemini API Key
            gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                print("⚠️ 未設定 GEMINI_API_KEY，跳過 VisionFill 測試")
                return True  # 不算失敗，只是跳過
            
            # 創建 VisionFill Agent
            vision_agent = VisionFillAgent()
            
            # 測試健康檢查
            health = await vision_agent.health_check()
            print(f"VisionFill Agent 健康狀態: {health}")
            
            # 創建一個需要補值的測試場景
            # 先在 Redis 中設置一個不完整的指標
            redis_client = get_redis_client()
            incomplete_metrics = {
                "views": 1000,
                "likes": None,  # 缺失
                "comments": None,  # 缺失
                "reposts": 0,
                "shares": 1
            }
            
            test_url = self.test_urls[0]
            redis_client.set_post_metrics(test_url, incomplete_metrics)
            
            # 測試補值功能
            print(f"測試補值功能: {test_url}")
            result = await vision_agent.fill_single_missing_metrics(test_url)
            print(f"補值結果: {result}")
            
            # 檢查補值後的指標
            updated_metrics = redis_client.get_post_metrics(test_url)
            print(f"補值後的指標: {updated_metrics}")
            
            print("✅ VisionFill Agent 測試通過")
            return True
            
        except Exception as e:
            print(f"❌ VisionFill Agent 測試失敗: {e}")
            return False
    
    async def test_ranking_function(self) -> bool:
        """測試排序功能"""
        print("\n=== 階段 4: 排序功能測試 ===")
        
        try:
            redis_client = get_redis_client()
            
            # 創建測試數據 - 多個貼文的指標
            test_data = [
                {
                    "url": f"https://www.threads.com/@{self.test_username}/post/test1",
                    "metrics": {"views": 5000, "likes": 100, "comments": 20, "reposts": 5, "shares": 3}
                },
                {
                    "url": f"https://www.threads.com/@{self.test_username}/post/test2", 
                    "metrics": {"views": 2000, "likes": 200, "comments": 50, "reposts": 10, "shares": 8}
                },
                {
                    "url": f"https://www.threads.com/@{self.test_username}/post/test3",
                    "metrics": {"views": 8000, "likes": 80, "comments": 15, "reposts": 2, "shares": 1}
                }
            ]
            
            # 寫入測試數據
            for data in test_data:
                redis_client.set_post_metrics(data["url"], data["metrics"])
            
            # 測試排序功能
            print(f"測試用戶 {self.test_username} 的貼文排序...")
            ranked_posts = redis_client.rank_user_posts(self.test_username, limit=10)
            
            print("排序結果:")
            for i, post in enumerate(ranked_posts):
                print(f"  {i+1}. URL: {post['url']}")
                print(f"      分數: {post['score']:.2f}")
                print(f"      指標: {post['metrics']}")
            
            if not ranked_posts:
                print("❌ 排序功能返回空結果")
                return False
            
            # 驗證排序是否正確（分數應該是降序）
            scores = [post['score'] for post in ranked_posts]
            if scores != sorted(scores, reverse=True):
                print("❌ 排序順序不正確")
                return False
            
            print("✅ 排序功能測試通過")
            return True
            
        except Exception as e:
            print(f"❌ 排序功能測試失敗: {e}")
            return False
    
    async def test_end_to_end_integration(self) -> bool:
        """測試端到端整合"""
        print("\n=== 階段 5: 端到端整合測試 ===")
        
        try:
            # 模擬完整的 Plan E 流程
            print("模擬完整的 Plan E 流程...")
            
            # 1. 創建測試貼文（模擬 Crawler 輸出）
            test_posts = [
                PostMetrics(
                    url=url,
                    post_id=url.split("/")[-1],
                    username=self.test_username
                ) for url in self.test_urls
            ]
            
            # 2. JinaMarkdown 處理
            print("步驟 1: JinaMarkdown 處理...")
            jina_agent = JinaMarkdownAgent()
            
            jina_results = []
            final_result_content = None
            async for result in jina_agent.batch_process_posts_with_storage(
                posts=test_posts,
                task_id="e2e_test"
            ):
                # 我們只關心最終的結果摘要
                if result.get("response_type") == "data" and result.get("is_task_complete"):
                    final_result_content = result.get("content")
            
            if not final_result_content:
                print("❌ JinaMarkdown 處理失敗，未收到最終結果")
                return False
            
            jina_result = final_result_content
            print(f"JinaMarkdown 結果: 成功 {jina_result.get('success_count', 0)} 個")
            
            # 3. VisionFill 處理（如果需要）
            vision_needed = jina_result.get('vision_needed_count', 0)
            if vision_needed > 0:
                print(f"步驟 2: VisionFill 處理 {vision_needed} 個貼文...")
                
                gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if gemini_key:
                    vision_agent = VisionFillAgent()
                    
                    # 處理 vision_fill 佇列
                    vision_results = []
                    final_vision_content = None
                    async for result in vision_agent.process_vision_queue(
                        queue_name="vision_fill",
                        batch_size=10,
                        task_id="e2e_vision_test"
                    ):
                        if result.get("response_type") == "data" and result.get("is_task_complete"):
                            final_vision_content = result.get("content")
                    
                    if final_vision_content:
                        print(f"VisionFill 結果: 處理了 {final_vision_content.get('total_processed', 0)} 個項目")
                    else:
                        print("VisionFill 未返回最終結果")
                else:
                    print("⚠️ 跳過 VisionFill（未設定 API Key）")
            
            # 4. 排序
            print("步驟 3: 排序...")
            redis_client = get_redis_client()
            ranked_posts = redis_client.rank_user_posts(self.test_username, limit=5)
            
            if not ranked_posts:
                print("❌ 排序失敗")
                return False
            
            print(f"排序結果: 找到 {len(ranked_posts)} 個貼文")
            
            # 5. 獲取 Top-K 貼文的完整數據（模擬分析階段）
            print("步驟 4: 獲取分析數據...")
            top_urls = [post['url'] for post in ranked_posts[:3]]
            
            db_client = await get_db_client()
            analysis_data = await db_client.get_posts_with_metrics(top_urls)
            
            print(f"分析數據: 獲取了 {len(analysis_data)} 個貼文的完整數據")
            
            for post in analysis_data:
                print(f"  - URL: {post['url']}")
                print(f"    Markdown 長度: {len(post.get('markdown', '')) if post.get('markdown') else 0}")
                print(f"    分數: {post.get('score', 0):.2f}")
            
            print("✅ 端到端整合測試通過")
            return True
            
        except Exception as e:
            print(f"❌ 端到端整合測試失敗: {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """運行所有測試"""
        print("開始 Plan E 分階段測試")
        print("=" * 60)
        
        # 檢查環境變數
        print("環境變數檢查:")
        print(f"GOOGLE_API_KEY: {'已設定' if os.getenv('GOOGLE_API_KEY') else '未設定'}")
        print(f"GEMINI_API_KEY: {'已設定' if os.getenv('GEMINI_API_KEY') else '未設定'}")
        print(f"DATABASE_URL: {'已設定' if os.getenv('DATABASE_URL') else '未設定'}")
        print(f"REDIS_URL: {'已設定' if os.getenv('REDIS_URL') else '未設定'}")
        print()
        
        # 定義測試
        tests = [
            ("基礎設施測試", self.test_infrastructure),
            ("JinaMarkdown Agent 測試", self.test_jina_markdown_agent),
            ("VisionFill Agent 測試", self.test_vision_fill_agent),
            ("排序功能測試", self.test_ranking_function),
            ("端到端整合測試", self.test_end_to_end_integration)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                print(f"\n{'='*20} {test_name} {'='*20}")
                results[test_name] = await test_func()
            except Exception as e:
                print(f"{test_name} 執行異常: {e}")
                results[test_name] = False
        
        return results


async def main():
    """主測試函數"""
    tester = PlanEStageTest()
    results = await tester.run_all_tests()
    
    # 總結
    print(f"\n{'='*60}")
    print("Plan E 測試總結:")
    for test_name, success in results.items():
        status = "✅ 通過" if success else "❌ 失敗"
        print(f"  {test_name}: {status}")
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\n總計: {passed_tests}/{total_tests} 個測試通過")
    
    if passed_tests == total_tests:
        print("🎉 所有 Plan E 測試都通過了！")
        return 0
    else:
        print("⚠️  部分測試失敗，請檢查錯誤訊息")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))