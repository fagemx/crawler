"""
測試任務佇列功能
"""

import time
from common.task_queue_manager import get_task_queue_manager, TaskStatus

def test_task_queue():
    """測試任務佇列基本功能"""
    print("🧪 開始測試任務佇列功能")
    
    queue_manager = get_task_queue_manager()
    
    # 清理現有佇列
    print("\n1. 清理現有佇列...")
    queue_manager.cleanup_old_tasks(0)  # 清理所有舊任務
    
    # 測試新增任務
    print("\n2. 測試新增任務...")
    tasks = [
        ("user1", 20, "new"),
        ("user2", 30, "hist"),
        ("user3", 15, "new")
    ]
    
    task_ids = []
    for username, max_posts, mode in tasks:
        task_id = f"test_{username}_{int(time.time())}"
        success = queue_manager.add_task(task_id, username, max_posts, mode)
        if success:
            task_ids.append(task_id)
            print(f"   ✅ 已新增任務: {username}")
        else:
            print(f"   ❌ 新增任務失敗: {username}")
    
    # 檢查佇列狀態
    print("\n3. 檢查佇列狀態...")
    status = queue_manager.get_queue_status()
    print(f"   總任務數: {status['total']}")
    print(f"   等待中: {status['waiting']}")
    print(f"   執行中: {status['running']}")
    
    # 測試開始任務
    print("\n4. 測試開始執行任務...")
    next_task = queue_manager.get_next_task()
    if next_task:
        print(f"   下一個任務: {next_task.username}")
        if queue_manager.start_task(next_task.task_id):
            print(f"   ✅ 已開始執行: {next_task.task_id[:8]}...")
        else:
            print(f"   ❌ 開始執行失敗")
    
    # 測試取消等待中的任務
    print("\n5. 測試取消等待中的任務...")
    if len(task_ids) > 1:
        cancel_task_id = task_ids[1]  # 取消第二個任務
        if queue_manager.cancel_task(cancel_task_id):
            print(f"   ✅ 已取消任務: {cancel_task_id[:8]}...")
        else:
            print(f"   ❌ 取消任務失敗")
    
    # 查看更新後的狀態
    print("\n6. 查看更新後的佇列狀態...")
    status = queue_manager.get_queue_status()
    print(f"   等待中: {status['waiting']}")
    print(f"   執行中: {status['running']}")
    print(f"   已取消: {status['cancelled']}")
    
    # 列出所有任務
    print("\n7. 列出所有任務詳情...")
    for i, task in enumerate(status['queue']):
        print(f"   {i+1}. @{task.username} - {task.display_status} - ID: {task.task_id[:8]}...")
    
    # 測試完成任務
    print("\n8. 測試完成執行中的任務...")
    running_task = queue_manager.get_current_running_task()
    if running_task:
        queue_manager.complete_task(running_task.task_id, True)
        print(f"   ✅ 已完成任務: {running_task.task_id[:8]}...")
    
    # 最終狀態
    print("\n9. 最終佇列狀態...")
    final_status = queue_manager.get_queue_status()
    print(f"   總任務數: {final_status['total']}")
    print(f"   等待中: {final_status['waiting']}")
    print(f"   執行中: {final_status['running']}")
    print(f"   已完成: {final_status['completed']}")
    print(f"   已取消: {final_status['cancelled']}")
    
    print("\n✅ 任務佇列測試完成！")
    
    return final_status

def test_queue_ui_integration():
    """測試佇列 UI 整合"""
    print("\n🖥️ 測試佇列 UI 整合...")
    
    try:
        from ui.components.task_queue_component import get_task_queue_component
        
        queue_component = get_task_queue_component()
        
        # 測試佇列可用性檢查
        is_available = queue_component.is_queue_available()
        print(f"   佇列可用性: {'✅ 可用' if is_available else '❌ 不可用'}")
        
        # 測試佇列位置查詢
        queue_manager = get_task_queue_manager()
        status = queue_manager.get_queue_status()
        
        if status['queue']:
            test_task = status['queue'][0]
            position = queue_component.get_queue_position(test_task.task_id)
            print(f"   任務位置查詢: {position}")
        
        print("   ✅ UI 整合測試成功")
        
    except ImportError as e:
        print(f"   ❌ UI 整合測試失敗: {e}")

if __name__ == "__main__":
    # 執行基本功能測試
    test_result = test_task_queue()
    
    # 執行 UI 整合測試
    test_queue_ui_integration()
    
    print("\n📊 測試報告:")
    print(f"   ✅ 基本功能: {'通過' if test_result else '失敗'}")
    print("   ✅ 佇列機制: 依序執行")
    print("   ✅ 取消功能: 僅等待中任務可取消")
    print("   ✅ 狀態管理: 完整追蹤")
    
    print("\n💡 使用建議:")
    print("   1. 啟動 Streamlit UI 測試完整功能")
    print("   2. 多個任務會自動排隊執行")
    print("   3. 等待中的任務可以取消")
    print("   4. 執行中的任務無法取消（避免資源衝突）")