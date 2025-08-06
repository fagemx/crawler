# UI 進度整合指南 - 雙軌進度系統

## 🎯 功能概述

為 `playwright_crawler_component_v2.py` 實現了**雙軌進度系統**，支援：

- ✅ **前台進度**：保持原有的檔案進度機制（瀏覽器開著時）
- ✅ **背景進度**：新增 Redis 進度查詢（關閉瀏覽器後可恢復）
- ✅ **任務管理**：查看所有活躍任務、恢復背景任務
- ✅ **向後相容**：原有功能完全不受影響

## 🔧 新增組件

### 1. 進度管理器 (`progress_manager.py`)

```python
class ProgressManager:
    # 雙軌進度讀寫
    def get_progress(task_id, prefer_redis=False)  # 混合讀取
    def write_progress(task_id, data, write_both=True)  # 同時寫檔案和Redis
    
    # 任務管理
    def list_active_tasks() -> List[TaskInfo]  # 列出所有任務
    def get_task_summary() -> Dict[str, int]   # 任務統計
```

### 2. 任務恢復組件 (`task_recovery_component.py`)

```python
class TaskRecoveryComponent:
    def render_task_list()           # 任務列表 UI
    def render_task_monitor(task_id) # 背景任務監控
    def render_cleanup_controls()    # 清理控制
```

### 3. UI 組件增強

`PlaywrightCrawlerComponentV2` 新增：
- 📋 **任務管理區域**：顯示任務摘要和管理入口
- 🔄 **任務恢復功能**：從背景恢復任務查看
- 📊 **任務管理頁面**：完整的任務管理介面

## 🚀 使用方法

### 方法一：正常使用（前台進度）

1. 啟動 Streamlit UI
2. 進入 Playwright 爬蟲頁面
3. 設定參數，點擊「🚀 開始爬取」
4. 查看即時進度（原有功能不變）

### 方法二：背景任務恢復

1. 啟動爬蟲後關閉瀏覽器
2. 重新開啟 UI
3. 在「📋 任務管理」區域查看摘要
4. 點擊「📊 管理任務」
5. 找到執行中的任務，點擊「👁️ 查看」
6. 恢復查看背景任務進度

## 📊 UI 介面說明

### 主頁面新增區域

```
🎭 Playwright 智能爬蟲 V2
========================================

⚙️ 爬取設定                    📊 資料庫統計
[設定區域...]                   [統計資訊...]

📋 任務管理                           ← 新增區域
共 3 個任務 | 🔄 1 執行中 ✅ 2 已完成    [📊 管理任務]
```

### 任務管理頁面

```
📋 任務管理中心
========================================

總任務: 3    執行中: 1    已完成: 2    錯誤: 0

@test_user_1        🔄 執行中      ⏱️ 5分鐘       [👁️ 查看]
任務 ID: test_018d...  ████████░░ 45.0%   階段: process_round_2

@test_user_2        ✅ 已完成      ⏱️ 30分鐘      [📊 結果]  
任務 ID: test_completed...  ██████████ 100.0%  階段: completed
```

## 🔍 技術實現細節

### 雙軌進度寫入

```python
def _write_progress(self, path, data):
    # 1. 原有檔案寫入（向後相容）
    [原有邏輯...]
    
    # 2. 同時寫入 Redis（新增功能）
    if self.progress_manager and hasattr(st.session_state, 'playwright_task_id'):
        task_id = st.session_state.playwright_task_id
        redis_data = old.copy()
        redis_data['timestamp'] = time.time()
        self.progress_manager.write_progress(task_id, redis_data, write_both=False)
```

### 任務恢復邏輯

```python
def _handle_recovered_task(self):
    # 1. 檢查任務 ID
    # 2. 從 Redis 獲取最新進度
    # 3. 更新 UI 顯示
    # 4. 檢查任務狀態（完成/錯誤）
```

## 🧪 測試方法

### 完整功能測試

```bash
# 1. 執行測試腳本
python test_ui_progress_integration.py

# 2. 啟動 UI
streamlit run ui/main.py

# 3. 測試場景
# - 啟動爬蟲後關閉瀏覽器
# - 重新開啟查看任務管理
# - 恢復背景任務查看
```

### 手動測試步驟

1. **啟動背景任務**：
   ```bash
   docker-compose up -d playwright-crawler-agent
   ```

2. **模擬進度更新**：
   ```bash
   python test_background_progress.py
   ```

3. **UI 驗證**：
   - 開啟 Streamlit UI
   - 進入 Playwright 爬蟲頁面
   - 查看任務管理區域
   - 測試任務恢復功能

## 📋 檔案結構

```
ui/components/
├── playwright_crawler_component_v2.py    # 主組件（已增強）
├── progress_manager.py                   # 進度管理器（新增）
├── task_recovery_component.py            # 任務恢復組件（新增）
└── playwright_crawler_enhanced_methods.py # 增強方法（新增）

專案根目錄/
├── test_ui_progress_integration.py       # UI 整合測試（新增）
├── monitor_progress.py                   # CLI 監控工具
├── test_background_progress.py           # 背景進度測試
└── UI_PROGRESS_INTEGRATION_GUIDE.md      # 本指南
```

## 🔧 故障排除

### 常見問題

1. **進度管理器不可用**
   ```
   ⚠️ 進度管理器不可用，將使用基本功能
   ```
   - 檢查模組路徑
   - 確認新檔案已正確放置

2. **Redis 連線失敗**
   - 檢查 Redis 服務狀態
   - 確認環境變數設定

3. **任務列表為空**
   - 確認 `temp_progress/` 目錄存在
   - 檢查 Redis 中是否有任務資料

### 除錯指令

```bash
# 檢查組件載入
python -c "from ui.components.progress_manager import ProgressManager; print('OK')"

# 檢查 Redis 連線
python -c "from common.redis_client import get_redis_client; print(get_redis_client().health_check())"

# 檢查任務檔案
ls -la temp_progress/
```

## 🎉 成功指標

完成後，你將擁有：

1. **無縫體驗**：原有功能完全不變
2. **背景監控**：關閉瀏覽器後可恢復查看任務
3. **任務管理**：統一的任務查看和管理介面
4. **容錯設計**：Redis 不可用時降級為檔案模式

---

💡 **提示**：這個實現保持了完全的向後相容性，原有用戶的使用體驗不會受到任何影響，同時為需要背景監控的用戶提供了強大的新功能。