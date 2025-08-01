"""
測試修復後的數據準確性
"""

import sys
import asyncio
from pathlib import Path

# Windows asyncio 修復
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 導入修復後的測試函數
sys.path.append(str(Path(__file__).parent))
from test_graphql_single_post import test_single_post_graphql
from common.config import get_auth_file_path

# 測試案例和預期結果
TEST_CASE = {
    "url": "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz",
    "expected": {
        "likes": 229,      # 可能有 ±5 的誤差（時間差）
        "comments": 66,    # 應該精確
        "reposts": 6,      # 應該精確
        "shares": 34       # 應該精確
    }
}

def validate_results(parsed_data, expected):
    """驗證結果準確性"""
    validation = {
        "accurate": True,
        "errors": [],
        "warnings": [],
        "metrics": {}
    }
    
    metrics_map = {
        "likes": "like_count",
        "comments": "comment_count", 
        "reposts": "repost_count",
        "shares": "share_count"
    }
    
    for metric, field in metrics_map.items():
        actual = parsed_data.get(field, 0)
        expected_val = expected[metric]
        diff = abs(actual - expected_val)
        
        validation["metrics"][metric] = {
            "actual": actual,
            "expected": expected_val,
            "difference": diff,
            "percentage_error": (diff / expected_val * 100) if expected_val > 0 else 0
        }
        
        # 驗證準確性
        if metric == "likes":
            # 讚數允許 ±5 的誤差（可能有時間差）
            if diff > 5:
                validation["errors"].append(f"{metric}: 差異過大 ({actual} vs {expected_val}, 差異: {diff})")
                validation["accurate"] = False
            elif diff > 0:
                validation["warnings"].append(f"{metric}: 有輕微差異 ({actual} vs {expected_val}, 差異: {diff})")
        else:
            # 其他指標要求精確匹配
            if diff > 0:
                validation["errors"].append(f"{metric}: 不匹配 ({actual} vs {expected_val})")
                validation["accurate"] = False
    
    return validation

async def main():
    print("🔧 測試修復後的數據準確性...")
    
    auth_file_path = get_auth_file_path()
    if not auth_file_path.exists():
        print(f"❌ 認證檔案不存在: {auth_file_path}")
        return
    
    print(f"📊 預期數據: 讚={TEST_CASE['expected']['likes']}, 留言={TEST_CASE['expected']['comments']}, 轉發={TEST_CASE['expected']['reposts']}, 分享={TEST_CASE['expected']['shares']}")
    
    try:
        # 使用修復後的函數測試
        result = await test_single_post_graphql(TEST_CASE["url"], auth_file_path)
        
        if result:
            # 獲取解析後的數據
            parsed_data = list(result.values())[0]  # 取第一個結果
            
            print(f"\n📊 解析結果:")
            print(f"   讚數: {parsed_data.get('like_count', 0)}")
            print(f"   留言數: {parsed_data.get('comment_count', 0)}")
            print(f"   轉發數: {parsed_data.get('repost_count', 0)}")
            print(f"   分享數: {parsed_data.get('share_count', 0)}")
            print(f"   來源: {parsed_data.get('data_source', 'unknown')}")
            print(f"   類型: {parsed_data.get('source_type', 'unknown')}")
            
            # 驗證準確性
            validation = validate_results(parsed_data, TEST_CASE['expected'])
            
            print(f"\n🎯 準確性驗證:")
            if validation["accurate"]:
                print(f"   ✅ 數據準確！")
            else:
                print(f"   ❌ 發現準確性問題:")
                for error in validation["errors"]:
                    print(f"      ❌ {error}")
            
            if validation["warnings"]:
                print(f"   ⚠️ 警告:")
                for warning in validation["warnings"]:
                    print(f"      ⚠️ {warning}")
            
            print(f"\n📊 詳細對比:")
            for metric, data in validation["metrics"].items():
                status = "✅" if data["difference"] == 0 else ("⚠️" if metric == "likes" and data["difference"] <= 5 else "❌")
                print(f"   {status} {metric}: {data['actual']} (預期: {data['expected']}, 差異: {data['difference']})")
                
        else:
            print(f"❌ 無法獲取測試結果")
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())