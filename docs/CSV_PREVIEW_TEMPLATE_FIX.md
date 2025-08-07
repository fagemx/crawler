# 🔧 CSV 預覽資料模板修復報告

## ❌ **原始問題**

用戶反饋：
```
Playwright 爬蟲 下面導出的CSV預覽 選擇 發布時間
但是CSV 預覽上面 沒有發布時間 欄位
這樣計算排列基於什麼??
為何不跟顯示詳細結果 使用一樣的資料模板就好?
```

## 🔍 **問題分析**

### **資料模板不一致**
發現兩個地方使用了不同的資料模板：

#### **1. "顯示詳細結果" 模板** ✅
在 `ui/components/playwright_crawler_component_v2.py` 中：
```python
# 完整的資料欄位
{
    "貼文ID": post_id,
    "內容": content,
    "觀看數": views_count,
    "按讚數": likes_count,
    "分數": calculated_score,
    "發布時間": published_taipei,  # ✅ 有發布時間
    "爬取時間": created_taipei,    # ✅ 有爬取時間
    # ... 其他欄位
}
```

#### **2. CSV 預覽模板** ❌
在 `ui/components/playwright_data_export_handler.py` 中：
```python
# 修復前：缺少發布時間
{
    "#": i,
    "貼文ID": post_id,
    "內容預覽": content_preview,
    "觀看數": views_count,
    "按讚數": likes_count,
    "分數": calculated_score,
    "爬取時間": fetched_at    # ❌ 沒有發布時間
}
```

### **邏輯不一致問題**
- **排序選項**：包含"發布時間"作為排序依據
- **預覽顯示**：但CSV預覽中沒有顯示發布時間欄位
- **用戶困惑**：不知道"發布時間"排序是基於什麼

## ✅ **修復方案**

### **統一資料模板**
將CSV預覽的資料模板修改為與"顯示詳細結果"一致：

```python
# 修復後：完整的資料模板
preview_data.append({
    "#": i,
    "貼文ID": post_id_display,
    "內容預覽": content_display,
    "觀看數": views_count_formatted,
    "按讚數": likes_count_formatted,
    "分數": calculated_score_formatted,
    "發布時間": published_display,  # ✅ 新增發布時間
    "爬取時間": fetched_display     # ✅ 改進爬取時間
})
```

### **時間處理改進**
添加了智能時間格式化：

```python
# 發布時間處理
published_at = post.get('post_published_at', '')
if published_at:
    try:
        taipei_published = PlaywrightUtils.convert_to_taipei_time(published_at)
        published_display = taipei_published.strftime('%Y-%m-%d %H:%M') if taipei_published else str(published_at)[:16]
    except:
        published_display = str(published_at)[:16] if published_at else 'N/A'
else:
    published_display = 'N/A'

# 爬取時間處理
fetched_at = post.get('fetched_at', '')
if fetched_at:
    try:
        taipei_fetched = PlaywrightUtils.convert_to_taipei_time(fetched_at)
        fetched_display = taipei_fetched.strftime('%Y-%m-%d %H:%M') if taipei_fetched else str(fetched_at)[:16]
    except:
        fetched_display = str(fetched_at)[:16] if fetched_at else 'N/A'
else:
    fetched_display = 'N/A'
```

## 🎯 **修復效果**

### **修復前的問題**：
```bash
❌ CSV預覽缺少發布時間欄位
❌ 無法理解"發布時間"排序的依據
❌ 資料模板不一致
❌ 時間格式處理簡陋
❌ 用戶體驗混淆
```

### **修復後的改進**：
```bash
✅ CSV預覽包含完整的發布時間欄位
✅ 清楚顯示"發布時間"排序的依據
✅ 資料模板完全一致
✅ 智能時間格式化（台北時區）
✅ 一致的用戶體驗
```

## 📊 **現在的CSV預覽欄位**

修復後，CSV預覽包含以下完整欄位：

| # | 欄位 | 格式 | 說明 |
|---|------|------|------|
| 1 | **#** | 數字 | 預覽序號 |
| 2 | **貼文ID** | 文字 | 截短顯示 |
| 3 | **內容預覽** | 文字 | 可選完整/預覽 |
| 4 | **觀看數** | 格式化數字 | 千分位分隔 |
| 5 | **按讚數** | 格式化數字 | 千分位分隔 |
| 6 | **分數** | 格式化數字 | 一位小數 |
| 7 | **發布時間** | 台北時間 | ✅ 新增！格式：YYYY-MM-DD HH:MM |
| 8 | **爬取時間** | 台北時間 | ✅ 改進！格式：YYYY-MM-DD HH:MM |

## 🔄 **排序邏輯一致性**

現在排序選項與預覽顯示完全對應：

### **排序選項** ↔ **預覽欄位**
- ✅ **發布時間** ↔ **發布時間欄位**
- ✅ **爬取時間** ↔ **爬取時間欄位**
- ✅ **觀看數** ↔ **觀看數欄位**
- ✅ **按讚數** ↔ **按讚數欄位**
- ✅ **計算分數** ↔ **分數欄位**

### **時間格式標準化**
- **台北時區**：所有時間都轉換為台北時區
- **統一格式**：`YYYY-MM-DD HH:MM`
- **錯誤處理**：無效時間顯示為 'N/A'

## 🚀 **用戶體驗提升**

### **清晰的排序依據**
- 用戶選擇"發布時間"排序 → 可以在預覽中看到發布時間欄位
- 排序結果與預覽顯示邏輯一致
- 不再有"排序基於什麼"的困惑

### **一致的資料模板**
- CSV預覽 = 詳細結果顯示
- 相同的欄位名稱和格式
- 統一的時間處理邏輯

### **更好的資訊完整性**
- 包含發布時間和爬取時間
- 提供完整的貼文資訊概覽
- 方便用戶在導出前預覽數據

---

**修復完成時間**：2025-08-07  
**影響範圍**：`ui/components/playwright_data_export_handler.py`  
**修復類型**：資料模板統一 + 時間處理改進 + 用戶體驗提升
