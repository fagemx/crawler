#!/usr/bin/env python3
"""
測試用戶名修復 - 模擬UI結果顯示流程
"""
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.redis_client import get_redis_client
from ui.components.playwright_utils import PlaywrightUtils

def test_username_fix():
    """測試用戶名修復效果"""
    task_id = "28da6114-fee1-4b6d-9547-ac85c0de44e0"  # 最新任務
    
    print("🧪 測試用戶名修復效果")
    
    # 步驟1: 從Redis獲取final_data
    print(f"\n📡 步驟1: 從Redis獲取任務數據 ({task_id[:8]}...)")
    redis_client = get_redis_client()
    progress_data = redis_client.get_task_status(task_id)
    final_data = progress_data.get("final_data", {})
    
    print(f"✅ Redis username: {progress_data.get('username')}")
    print(f"✅ final_data username: {final_data.get('username')}")
    
    # 步驟2: 模擬_render_results轉換邏輯
    print(f"\n🔄 步驟2: 模擬UI轉換邏輯 (修復後)")
    
    # 原始轉換
    converted_results = PlaywrightUtils.convert_playwright_results(final_data)
    print(f"🔸 轉換後 target_username: {converted_results.get('target_username')}")
    
    # 模擬修復後的邏輯
    if not converted_results.get("target_username"):
        print("🔧 target_username為空，從其他來源獲取...")
        # 模擬session_state為空的情況（任務恢復時）
        target = {}  # st.session_state.get('playwright_target', {})
        session_username = target.get('username')
        final_data_username = final_data.get('username')
        converted_results["target_username"] = session_username or final_data_username or 'unknown'
        print(f"🔧 修復後 target_username: {converted_results.get('target_username')}")
    else:
        print("✅ target_username已存在，無需修復")
    
    # 步驟3: 檢查最終結果
    print(f"\n📊 步驟3: 最終結果")
    print(f"✅ 最終用戶名: @{converted_results.get('target_username', 'unknown')}")
    print(f"✅ 總貼文數: {len(converted_results.get('results', []))}")
    
    # 驗證
    final_username = converted_results.get('target_username')
    if final_username and final_username != 'unknown':
        print(f"\n🎉 修復成功！用戶名正確顯示為: @{final_username}")
    else:
        print(f"\n❌ 修復失敗！用戶名仍為: @{final_username}")

if __name__ == "__main__":
    test_username_fix()