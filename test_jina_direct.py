"""
直接測試 Jina Agent 邏輯 - 不透過 Docker
"""
import sys
import os
sys.path.append('.')

import requests
from agents.jina.jina_logic import JinaMarkdownAgent
from common.models import PostMetrics, PostMetricsBatch
from datetime import datetime

def test_single_url():
    """測試單一 URL"""
    print("=== 直接測試 Jina API ===")
    
    # 測試 URL
    test_url = "https://www.threads.net/t/DMSy3RVNma0"
    
    # 直接呼叫 Jina API
    jina_url = f"https://r.jina.ai/{test_url}"
    headers = {
        "Authorization": "Bearer jina_763fec6216074e92a759d160e97c0d63-vMwaCsFV12-4Obv9G5DZeeCnrcH",
        "X-Return-Format": "markdown"
    }
    
    print(f"📡 呼叫 Jina API: {jina_url}")
    
    try:
        response = requests.get(jina_url, headers=headers, timeout=30)
        print(f"✅ 回應狀態: {response.status_code}")
        
        if response.status_code == 200:
            markdown_text = response.text
            print(f"📄 Markdown 長度: {len(markdown_text)} 字元")
            print(f"📄 前 500 字元:")
            print("=" * 50)
            print(markdown_text[:500])
            print("=" * 50)
            
            # 測試解析
            print("\n=== 測試 Metrics 解析 ===")
            agent = JinaMarkdownAgent()
            metrics = agent._extract_metrics_from_markdown(markdown_text)
            print(f"🎯 解析結果: {metrics}")
            
            return markdown_text, metrics
        else:
            print(f"❌ API 錯誤: {response.status_code} - {response.text}")
            return None, None
            
    except Exception as e:
        print(f"❌ 例外錯誤: {e}")
        return None, None

def test_batch_processing():
    """測試批次處理"""
    print("\n=== 測試批次處理邏輯 ===")
    
    # 建立測試 batch
    posts = [
        PostMetrics(
            url="https://www.threads.net/t/DMSy3RVNma0",
            post_id="3680227546021390004",
            username="natgeo",  # 添加缺少的 username
            likes_count=169,
            comments_count=2,
            reposts_count=None,
            shares_count=None,
            views_count=None,  # 這個應該被 Jina 填補
            content="Raise your hand if you've rewatched this video more than 5 times 🙌...",
            created_at=datetime.now()
        )
    ]
    
    batch = PostMetricsBatch(
        posts=posts,
        username="natgeo",
        total_count=1,
        processing_stage="playwright_completed"
    )
    
    print(f"📦 測試 Batch: {len(batch.posts)} 個貼文")
    print(f"📦 第一個貼文的 views_count: {batch.posts[0].views_count}")
    
    # 使用 JinaMarkdownAgent 處理
    agent = JinaMarkdownAgent()
    try:
        import asyncio
        enriched_batch = asyncio.run(agent.enrich_batch(batch))
        
        print(f"✅ 處理完成!")
        print(f"📦 處理後的 views_count: {enriched_batch.posts[0].views_count}")
        print(f"📦 處理後的 processing_stage: {enriched_batch.processing_stage}")
        
        return enriched_batch
        
    except Exception as e:
        print(f"❌ 批次處理錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🧪 直接測試 Jina Agent 邏輯")
    print("=" * 60)
    
    # 測試 1: 單一 URL
    markdown_text, metrics = test_single_url()
    
    # 測試 2: 批次處理
    if metrics:
        enriched_batch = test_batch_processing()
        
        if enriched_batch:
            print(f"\n🎉 成功！Views 已被填補為: {enriched_batch.posts[0].views_count}")
        else:
            print(f"\n❌ 批次處理失敗")
    else:
        print(f"\n❌ 無法獲取 Markdown，跳過批次測試") 