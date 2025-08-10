# RustFS 自動管理指南

本文檔說明如何使用自動化工具來管理 RustFS 存儲系統，特別是解決 "Heal queue is full" 錯誤問題。

## 問題背景

RustFS 錯誤 `"Heal queue is full"` 通常發生在以下情況：
- 存儲空間不足
- 大量文件需要自我修復
- 修復進程被阻塞
- 長期運行後積累了太多待處理任務

## 解決方案

我們提供了完整的自動化管理工具來處理這些問題：

### 1. RustFS 自動管理腳本

**檔案：** `rustfs_auto_manager.py`

這是主要的管理工具，提供以下功能：

#### 功能特性
- 🔍 **健康監控**：檢查 RustFS 容器狀態、S3 API 可用性、存儲使用情況
- 🧹 **自動清理**：清理過期媒體檔案、失敗的下載記錄、舊日誌檔案
- 🔄 **服務重啟**：當清理無法解決問題時自動重啟 RustFS 服務
- 📊 **智能維護**：根據狀態自動決定維護策略

#### 使用方法

```bash
# 檢查健康狀態
python rustfs_auto_manager.py --action health

# 執行清理
python rustfs_auto_manager.py --action cleanup

# 重啟 RustFS 服務
python rustfs_auto_manager.py --action restart

# 自動維護（推薦）
python rustfs_auto_manager.py --action auto

# 持續監控模式（每30分鐘檢查一次）
python rustfs_auto_manager.py --action monitor --interval 30
```

### 2. 定期任務設置

**檔案：** `scripts/rustfs_cron_setup.sh`

這個腳本會自動設置定期維護任務。

#### Linux/macOS 使用方法

```bash
# 執行設置腳本
chmod +x scripts/rustfs_cron_setup.sh
./scripts/rustfs_cron_setup.sh
```

這會設置一個 cron 任務，每天凌晨 2:00 自動執行維護。

#### Windows 使用方法

Windows 用戶請使用任務排程器：

1. 開啟 Windows 任務排程器
2. 建立基本任務
3. 設置參數：
   - **名稱：** RustFS Auto Maintenance
   - **觸發程序：** 每日執行
   - **時間：** 02:00
   - **動作：** 啟動程式
   - **程式：** `python`
   - **引數：** `"C:\ai_base\knowledge_base\social-media-content-generator\rustfs_auto_manager.py" --action auto`
   - **起始於：** `C:\ai_base\knowledge_base\social-media-content-generator`

或使用 PowerShell 手動執行：
```powershell
cd "C:\ai_base\knowledge_base\social-media-content-generator"
python rustfs_auto_manager.py --action auto
```

### 3. 環境變數配置

可以通過環境變數自定義管理行為：

```bash
# .env 檔案中添加
RUSTFS_MAX_FILE_AGE_DAYS=7        # 檔案保留天數（預設7天）
RUSTFS_MAX_LOG_AGE_DAYS=3         # 日誌保留天數（預設3天）
RUSTFS_MAX_STORAGE_SIZE_GB=10     # 最大存儲大小（預設10GB）
```

## 故障排除

### 當 "Heal queue is full" 錯誤發生時

1. **立即解決：**
   ```bash
   python rustfs_auto_manager.py --action auto
   ```

2. **如果自動維護無效：**
   ```bash
   # 強制重啟 RustFS
   python rustfs_auto_manager.py --action restart
   ```

3. **檢查清理結果：**
   ```bash
   python rustfs_auto_manager.py --action health
   ```

### 常見問題

#### Q: 腳本報告 "找不到 docker-compose"
**A:** 確保已安裝 Docker Compose：
```bash
# Ubuntu/Debian
sudo apt install docker-compose

# 或使用 Docker Compose V2
sudo apt install docker-compose-plugin
```

#### Q: 權限被拒絕錯誤
**A:** 確保用戶在 docker 群組中：
```bash
sudo usermod -aG docker $USER
# 重新登入或重啟
```

#### Q: 清理後仍然出現錯誤
**A:** 可能需要檢查磁碟空間或增加存儲配額：
```bash
# 檢查磁碟空間
df -h

# 檢查 RustFS 存儲使用
du -sh storage/rustfs/
```

## 監控和日誌

### 查看維護日誌
```bash
# 查看管理腳本日誌
tail -f rustfs_manager.log

# 查看定期維護日誌
tail -f logs/rustfs_maintenance.log

# 查看 RustFS 容器日誌
docker-compose logs -f rustfs
```

### 監控指標

管理腳本會監控以下指標：
- 容器運行狀態
- S3 API 可用性
- 存儲使用率
- Heal queue 錯誤數量
- 檔案數量和大小

## 最佳實踐

1. **定期維護：** 設置自動化任務，不要等問題出現才處理
2. **監控存儲：** 保持存儲使用率在 80% 以下
3. **日誌輪轉：** 定期清理舊日誌，避免佔用過多空間
4. **備份重要數據：** 在大規模清理前備份重要媒體檔案
5. **監控日誌：** 定期檢查錯誤日誌，及早發現問題

## 手動管理

如果需要手動管理，可以使用 `manage_system.sh` 腳本：

```bash
# 查看 RustFS 狀態
./manage_system.sh status

# 重啟 RustFS
./manage_system.sh restart

# 查看 RustFS 日誌
./manage_system.sh logs | grep rustfs
```

## 高級配置

### 自定義清理策略

編輯 `rustfs_auto_manager.py` 中的參數：

```python
# 修改這些參數來調整清理策略
self.max_file_age_days = 7      # 檔案保留天數
self.max_log_age_days = 3       # 日誌保留天數
self.max_storage_size_gb = 10   # 最大存儲大小
```

### 整合到系統監控

可以將健康檢查結果整合到現有監控系統：

```bash
# 獲取 JSON 格式的健康狀態
python rustfs_auto_manager.py --action health > rustfs_health.json
```

## 更新和維護

1. **定期更新腳本：** 隨著專案更新，管理腳本可能會有改進
2. **調整清理參數：** 根據實際使用情況調整檔案保留期限
3. **監控效果：** 觀察自動維護的效果，必要時調整策略

---

如果您遇到任何問題或需要協助，請檢查日誌檔案或聯繫系統管理員。
