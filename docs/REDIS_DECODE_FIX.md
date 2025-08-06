# 🔧 Redis Decode 錯誤修復報告

## ❌ **原始錯誤**

根據錯誤日誌：
```bash
⚠️ 更新Redis進度失敗: 'str' object has no attribute 'decode'
```

## 🔍 **問題分析**

### **錯誤原因**
在 `ui/components/playwright_crawler_component_v2.py` 中，多個位置假設從Redis讀取的數據總是 `bytes` 類型，並直接調用 `.decode()` 方法。但實際上，Redis客戶端的不同版本或配置可能會返回 `str` 而不是 `bytes`。

### **錯誤位置**
1. **第222行**：`status = job_data.get(b'status', b'running').decode()`
2. **第223行**：`progress = float(job_data.get(b'progress', b'0').decode())`  
3. **第229行**：`error_msg = job_data.get(b'error', b'..').decode()`
4. **第575行**：`existing_job_id = existing_job_id.decode()`
5. **第1548行**：`redis_conn.get(lock_key).decode() == job_id`
6. **第1550行**：`lock_key.decode()`

## ✅ **修復方案**

### **1. 創建安全Decode函數**
```python
def _safe_decode(self, value, default=''):
    """安全地將bytes或str轉換為str"""
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)
```

### **2. 兼容性讀取**
修復所有Redis讀取操作，同時支持bytes和str鍵：

```python
# 修復前（只支持bytes鍵）
status = job_data.get(b'status', b'running').decode()

# 修復後（同時支持bytes和str鍵）
status = self._safe_decode(job_data.get(b'status') or job_data.get('status'), 'running')
```

### **3. 全面修復位置**

#### **A. _show_existing_task_progress 方法**
- ✅ 添加 `_safe_decode` 輔助函數
- ✅ 修復 status、progress、error_msg 的讀取
- ✅ 同時支持 bytes 和 str 鍵名

#### **B. 任務鎖檢查**
- ✅ 修復 `existing_job_id.decode()` 錯誤
- ✅ 使用 `self._safe_decode(existing_job_id)`

#### **C. 鎖釋放邏輯**
- ✅ 修復 `lock_value.decode()` 錯誤
- ✅ 修復 `lock_key.decode()` 錯誤
- ✅ 使用安全decode函數

## 🎯 **修復效果**

### **修復前的錯誤行為**：
```bash
❌ 'str' object has no attribute 'decode'
❌ Redis進度更新失敗
❌ 任務狀態顯示異常
❌ 鎖管理失效
```

### **修復後的正確行為**：
```bash
✅ 自動檢測並處理 bytes/str 類型
✅ Redis進度更新正常
✅ 任務狀態正確顯示
✅ 鎖管理正常運作
✅ 向前兼容不同Redis客戶端版本
```

## 📊 **技術細節**

### **兼容性策略**
```python
# 同時嘗試bytes和str鍵名
progress_raw = job_data.get(b'progress') or job_data.get('progress') or '0'
progress = float(self._safe_decode(progress_raw, '0'))
```

### **安全轉換邏輯**
```python
def _safe_decode(self, value, default=''):
    if value is None:          # 處理None值
        return default
    if isinstance(value, bytes):  # 處理bytes → str
        return value.decode('utf-8')
    return str(value)           # 處理其他類型 → str
```

## 🚀 **測試場景**

修復後支持以下所有情況：

1. **✅ Redis返回bytes**：`{b'status': b'running'}`
2. **✅ Redis返回str**：`{'status': 'running'}`  
3. **✅ 混合類型**：`{b'status': 'running', 'progress': b'0.5'}`
4. **✅ 缺失值**：使用預設值而不是報錯
5. **✅ None值**：安全處理，返回預設值

---

**修復完成時間**：2025-08-07  
**影響範圍**：`ui/components/playwright_crawler_component_v2.py`  
**修復類型**：Redis兼容性 + 錯誤處理 + 向前兼容
