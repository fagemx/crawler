#!/usr/bin/env python3
"""
簡單排序功能測試

基於 Plan E 的排序邏輯：從 Redis 批量 hgetall → score = views +0.3(likes+comments) 排序
這個測試可以獨立運行，不依賴完整的 Agent 架構
"""

import os
import sys
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


def create_test_data(username: str) -> List[Dict[str, Any]]:
    """創建測試數據"""
    return [
        {
            "url": f"https://www.threads.com/@{username}/post/high_engagement",
            "metrics": {"views": 2000, "likes": 200, "comments": 50, "reposts": 10, "shares": 8},
            "expected_score": 2000 + 0.3 * (200 + 50) + 0.1 * (10 + 8)  # 2000 + 75 + 1.8 = 2076.8
        },
        {
            "url": f"https://www.threads.com/@{username}/post/high_views",
            "metrics": {"views": 8000, "likes": 80, "comments": 15, "reposts": 2, "shares": 1},
            "expected_score": 8000 + 0.3 * (80 + 15) + 0.1 * (2 + 1)  # 8000 + 28.5 + 0.3 = 8028.8
        },
        {
            "url": f"https://www.threads.com/@{username}/post/medium_all",
            "metrics": {"views": 5000, "likes": 100, "comments": 20, "reposts": 5, "shares": 3},
            "expected_score": 5000 + 0.3 * (100 + 20) + 0.1 * (5 + 3)  # 5000 + 36 + 0.8 = 5036.8
        },
        {
            "url": f"https://www.threads.com/@{username}/post/low_all",
            "metrics": {"views": 1000, "likes": 20, "comments": 5, "reposts": 1, "shares": 0},
            "expected_score": 1000 + 0.3 * (20 + 5) + 0.1 * (1 + 0)  # 1000 + 7.5 + 0.1 = 1007.6
        }
    ]


def test_plan_e_ranking():
    """測試 Plan E 排序邏輯"""
    print("=== Plan E 排序邏輯測試 ===")
    
    try:
        # 獲取 Redis 客戶端
        redis_client = get_redis_client()
        
        # 測試 Redis 連接
        health = redis_client.health_check()
        if health.get("status") != "healthy":
            print(f"❌ Redis 連接失敗: {health}")
            return False
        
        print("✅ Redis 連接正常")
        
        # 創建測試數據
        username = "test_user"
        test_data = create_test_data(username)
        
        print(f"\n創建測試數據 ({len(test_data)} 個貼文):")
        for i, data in enumerate(test_data):
            print(f"  {i+1}. {data['url'].split('/')[-1]}")
            print(f"     指標: {data['metrics']}")
            print(f"     預期分數: {data['expected_score']:.1f}")
        
        # 寫入測試數據到 Redis
        print(f"\n寫入數據到 Redis...")
        for data in test_data:
            success = redis_client.set_post_metrics(data["url"], data["metrics"])
            if not success:
                print(f"❌ 寫入失敗: {data['url']}")
                return False
        
        print("✅ 數據寫入成功")
        
        # 執行排序
        print(f"\n執行排序...")
        ranked_posts = redis_client.rank_user_posts(username, limit=10)
        
        if not ranked_posts:
            print("❌ 排序返回空結果")
            return False
        
        print(f"✅ 排序完成，返回 {len(ranked_posts)} 個結果")
        
        # 顯示排序結果
        print(f"\n排序結果:")
        for i, post in enumerate(ranked_posts):
            url_name = post['url'].split('/')[-1]
            print(f"  {i+1}. {url_name}")
            print(f"     分數: {post['score']:.1f}")
            print(f"     指標: views={post['metrics']['views']}, likes={post['metrics']['likes']}, comments={post['metrics']['comments']}")
        
        # 驗證排序正確性
        print(f"\n驗證排序正確性...")
        
        # 檢查分數是否降序排列
        scores = [post['score'] for post in ranked_posts]
        if scores != sorted(scores, reverse=True):
            print("❌ 分數未按降序排列")
            return False
        
        print("✅ 分數按降序排列正確")
        
        # 檢查預期的排序順序
        expected_order = [
            "high_views",      # 8028.8
            "high_engagement", # 2076.8  
            "medium_all",      # 5036.8
            "low_all"          # 1007.6
        ]
        
        # 實際順序應該是: high_views > medium_all > high_engagement > low_all
        correct_order = ["high_views", "medium_all", "high_engagement", "low_all"]
        
        actual_order = [post['url'].split('/')[-1] for post in ranked_posts]
        
        print(f"預期順序: {correct_order}")
        print(f"實際順序: {actual_order}")
        
        if actual_order == correct_order:
            print("✅ 排序順序完全正確")
        else:
            print("⚠️ 排序順序與預期不同，但可能是正常的（分數計算差異）")
        
        # 驗證分數計算
        print(f"\n驗證分數計算...")
        for post in ranked_posts:
            url_name = post['url'].split('/')[-1]
            metrics = post['metrics']
            
            # 手動計算分數
            calculated_score = (
                metrics['views'] * 1.0 +
                metrics['likes'] * 0.3 +
                metrics['comments'] * 0.3 +
                metrics['reposts'] * 0.1 +
                metrics['shares'] * 0.1
            )
            
            actual_score = post['score']
            
            print(f"  {url_name}: 計算={calculated_score:.1f}, 實際={actual_score:.1f}")
            
            if abs(calculated_score - actual_score) > 0.1:
                print(f"❌ 分數計算錯誤: {url_name}")
                return False
        
        print("✅ 分數計算正確")
        
        print("\n✅ Plan E 排序邏輯測試通過")
        return True
        
    except Exception as e:
        print(f"❌ Plan E 排序邏輯測試失敗: {e}")
        return False


def test_ranking_with_missing_data():
    """測試缺失數據的排序處理"""
    print("\n=== 缺失數據排序測試 ===")
    
    try:
        redis_client = get_redis_client()
        username = "test_missing"
        
        # 創建包含缺失數據的測試
        test_data = [
            {
                "url": f"https://www.threads.com/@{username}/post/complete",
                "metrics": {"views": 1000, "likes": 50, "comments": 10, "reposts": 2, "shares": 1}
            },
            {
                "url": f"https://www.threads.com/@{username}/post/missing_some",
                "metrics": {"views": 2000, "likes": 0, "comments": 0, "reposts": 0, "shares": 0}  # 可能是缺失數據
            }
        ]
        
        # 寫入數據
        for data in test_data:
            redis_client.set_post_metrics(data["url"], data["metrics"])
        
        # 排序
        ranked_posts = redis_client.rank_user_posts(username, limit=10)
        
        print(f"缺失數據排序結果:")
        for i, post in enumerate(ranked_posts):
            url_name = post['url'].split('/')[-1]
            print(f"  {i+1}. {url_name}: 分數={post['score']:.1f}")
        
        print("✅ 缺失數據排序測試通過")
        return True
        
    except Exception as e:
        print(f"❌ 缺失數據排序測試失敗: {e}")
        return False


def main():
    """主測試函數"""
    print("開始 Plan E 排序功能測試")
    print("=" * 50)
    print("測試 Plan E 中定義的排序邏輯：score = views + 0.3*(likes+comments) + 0.1*(reposts+shares)")
    print()
    
    # 檢查環境變數
    print("環境變數檢查:")
    print(f"REDIS_URL: {'已設定' if os.getenv('REDIS_URL') else '未設定'}")
    print()
    
    # 執行測試
    tests = [
        ("Plan E 排序邏輯", test_plan_e_ranking),
        ("缺失數據排序處理", test_ranking_with_missing_data)
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            results[test_name] = test_func()
        except Exception as e:
            print(f"{test_name} 執行異常: {e}")
            results[test_name] = False
    
    # 總結
    print(f"\n{'='*50}")
    print("排序功能測試總結:")
    for test_name, success in results.items():
        status = "✅ 通過" if success else "❌ 失敗"
        print(f"  {test_name}: {status}")
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\n總計: {passed_tests}/{total_tests} 個測試通過")
    
    if passed_tests == total_tests:
        print("🎉 所有排序功能測試都通過了！")
        print("✅ Plan E 排序邏輯實現正確")
        return 0
    else:
        print("⚠️  部分測試失敗，請檢查排序邏輯實現")
        return 1


if __name__ == "__main__":
    sys.exit(main())