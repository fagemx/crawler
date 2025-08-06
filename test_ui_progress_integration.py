#!/usr/bin/env python3
"""
UI 進度整合測試腳本
測試 playwright_crawler_component_v2.py 的雙軌進度機制
"""

import asyncio
import time
import uuid
import json
from pathlib import Path
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_progress_integration():
    """測試 UI 進度整合功能"""
    print("🧪 UI 進度整合測試")
    print("=" * 50)
    
    # 測試進度管理器
    try:
        from ui.components.progress_manager import ProgressManager
        from ui.components.task_recovery_component import TaskRecoveryComponent
        
        print("✅ 進度管理組件載入成功")
        
        # 初始化組件
        progress_manager = ProgressManager()
        task_recovery = TaskRecoveryComponent()
        
        print("✅ 組件初始化成功")
        
    except ImportError as e:
        print(f"❌ 組件載入失敗: {e}")
        return False
    
    # 測試基本功能
    try:
        # 1. 測試進度寫入
        test_task_id = f"ui_test_{uuid.uuid4().hex[:8]}"
        test_data = {
            "stage": "test_stage",
            "progress": 50.0,
            "username": "test_user",
            "current_work": "測試中..."
        }
        
        print(f"\n📝 測試進度寫入 (任務 ID: {test_task_id})")
        progress_manager.write_progress(test_task_id, test_data)
        
        # 2. 測試進度讀取
        print("📖 測試進度讀取")
        
        # 檔案讀取
        file_data = progress_manager.read_file_progress(test_task_id)
        print(f"   檔案資料: {file_data.get('progress', '無')}")
        
        # Redis 讀取
        redis_data = progress_manager.read_redis_progress(test_task_id)
        print(f"   Redis 資料: {redis_data.get('progress', '無')}")
        
        # 混合讀取
        mixed_data = progress_manager.get_progress(test_task_id)
        print(f"   混合資料: {mixed_data.get('progress', '無')}")
        
        # 3. 測試任務列表
        print("\n📋 測試任務列表")
        tasks = progress_manager.list_active_tasks()
        print(f"   找到 {len(tasks)} 個任務")
        
        for task in tasks[:3]:  # 只顯示前 3 個
            print(f"   - {task.task_id[:8]}... | @{task.username} | {task.progress:.1f}% | {task.display_status}")
        
        # 4. 測試任務摘要
        print("\n📊 測試任務摘要")
        summary = progress_manager.get_task_summary()
        print(f"   總計: {summary['total']} | 執行中: {summary['running']} | 完成: {summary['completed']} | 錯誤: {summary['error']}")
        
        print("\n✅ 所有測試通過！")
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_playwright_component_import():
    """測試 Playwright 組件載入"""
    print("\n🎭 測試 Playwright 組件載入")
    print("-" * 30)
    
    try:
        from ui.components.playwright_crawler_component_v2 import PlaywrightCrawlerComponentV2
        
        component = PlaywrightCrawlerComponentV2()
        print("✅ PlaywrightCrawlerComponentV2 載入成功")
        
        # 檢查新增的屬性
        if hasattr(component, 'progress_manager'):
            print("✅ progress_manager 屬性存在")
        else:
            print("❌ progress_manager 屬性不存在")
        
        if hasattr(component, 'task_recovery'):
            print("✅ task_recovery 屬性存在")
        else:
            print("❌ task_recovery 屬性不存在")
        
        # 檢查新增的方法
        methods_to_check = ['_handle_recovered_task', '_render_task_manager']
        for method_name in methods_to_check:
            if hasattr(component, method_name):
                print(f"✅ {method_name} 方法存在")
            else:
                print(f"❌ {method_name} 方法不存在")
        
        return True
        
    except Exception as e:
        print(f"❌ 組件載入失敗: {e}")
        return False

def create_test_progress_files():
    """創建測試進度檔案"""
    print("\n📁 創建測試進度檔案")
    print("-" * 25)
    
    temp_progress_dir = Path("temp_progress")
    temp_progress_dir.mkdir(exist_ok=True)
    
    # 創建幾個測試檔案
    test_files = [
        {
            "task_id": "test_running_001",
            "data": {
                "stage": "process_round_2_details",
                "progress": 45.0,
                "username": "test_user_1",
                "current_work": "正在處理第 2 輪資料...",
                "start_time": time.time() - 300,  # 5 分鐘前開始
                "status": "running"
            }
        },
        {
            "task_id": "test_completed_002", 
            "data": {
                "stage": "completed",
                "progress": 100.0,
                "username": "test_user_2",
                "current_work": "任務完成",
                "start_time": time.time() - 1800,  # 30 分鐘前開始
                "status": "completed",
                "final_data": {"total_posts": 50}
            }
        },
        {
            "task_id": "test_error_003",
            "data": {
                "stage": "error",
                "progress": 25.0,
                "username": "test_user_3",
                "current_work": "發生錯誤",
                "start_time": time.time() - 600,  # 10 分鐘前開始
                "status": "error",
                "error": "網路連線超時"
            }
        }
    ]
    
    for test_file in test_files:
        file_path = temp_progress_dir / f"playwright_progress_{test_file['task_id']}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(test_file["data"], f, ensure_ascii=False, indent=2)
        print(f"✅ 創建: {file_path.name}")
    
    print(f"📁 測試檔案已創建在: {temp_progress_dir}")

async def main():
    """主測試函式"""
    print("🚀 開始 UI 進度整合測試")
    print("=" * 60)
    
    # 創建測試檔案
    create_test_progress_files()
    
    # 測試進度整合
    integration_ok = await test_progress_integration()
    
    # 測試組件載入
    component_ok = test_playwright_component_import()
    
    print("\n" + "=" * 60)
    print("📋 測試結果總結")
    print(f"   進度整合: {'✅ 通過' if integration_ok else '❌ 失敗'}")
    print(f"   組件載入: {'✅ 通過' if component_ok else '❌ 失敗'}")
    
    if integration_ok and component_ok:
        print("\n🎉 所有測試通過！UI 進度整合已就緒")
        print("\n💡 使用指南:")
        print("   1. 啟動 Streamlit UI")
        print("   2. 進入 Playwright 爬蟲頁面")
        print("   3. 查看「任務管理」區域")
        print("   4. 點擊「📊 管理任務」按鈕")
        print("   5. 可以查看和恢復背景任務")
    else:
        print("\n❌ 部分測試失敗，請檢查錯誤訊息")

if __name__ == "__main__":
    asyncio.run(main())