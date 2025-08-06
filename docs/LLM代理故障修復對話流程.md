# LLM代理故障修復對話流程 - 快速復原指南

## 🎯 流程總覽

本文檔提供與LLM代理配合進行Threads爬蟲系統故障修復的**標準對話流程**，確保快速、有效地恢復系統功能。

---

## 🚨 場景1：影片提取全面失效

### 階段1：故障發現與初步診斷

**👤 用戶**：
```
影片提取出問題了，所有層級都是0個
測試結果：📊 各層成效統計: 直接攔截=0 | GraphQL=0 | __NEXT_DATA__=0 | play()劫持=0 | DOM=0
```

**🤖 LLM代理**：
```
這是典型的Threads架構更新導致的全面失效。我們需要立即啟動故障診斷流程：

1. 首先運行 GraphQL 攔截工具來發現新的API模式
2. 然後分析結果並更新代碼

請運行以下命令：
python intercept_all_graphql.py

運行完成後，請告訴我：
- 終端輸出的關鍵信息（特別是包含 "has_videos" 的響應）
- 生成的 JSON 文件名稱
- 是否有任何錯誤信息
```

### 階段2：GraphQL攔截分析

**👤 用戶**：
```
運行完成，結果如下：
📥 響應: ThreadsVideoPlayerQuery (has_videos, has_media)
📥 響應: BarcelonaMediaQuery (has_media)
🎯 可能的內容響應！
📁 已保存到: potential_content_ThreadsVideoPlayerQuery_143052.json
📁 已保存到: potential_content_BarcelonaMediaQuery_143053.json

發現的 doc_id:
   1234567890 - ThreadsVideoPlayerQuery
   0987654321 - BarcelonaMediaQuery
```

**🤖 LLM代理**：
```
太好了！發現了新的查詢模式。我看到：
1. ThreadsVideoPlayerQuery - 這可能是新的影片查詢
2. BarcelonaMediaQuery - 這可能是媒體相關查詢

請提供以下信息讓我分析：
1. 把 potential_content_ThreadsVideoPlayerQuery_143052.json 的內容貼給我（前100行即可）
2. 或者如果文件太大，請告訴我文件大小，我會指導你如何提取關鍵部分

另外，請確認當前的影片URL獲取是否完全失效？還是只是成功率降低？
```

### 階段3：JSON結構分析

**👤 用戶**：
```json
{
  "query_name": "ThreadsVideoPlayerQuery",
  "response_data": {
    "data": {
      "video_player": {
        "playback_url": "https://instagram.fkhh5-1.fna.fbcdn.net/v/video123.mp4",
        "hd_url": "https://instagram.fkhh5-1.fna.fbcdn.net/v/video123_hd.mp4",
        "thumbnail": "https://instagram.fkhh5-1.fna.fbcdn.net/t/thumb123.jpg"
      }
    }
  }
}
```

**🤖 LLM代理**：
```
完美！我看到新的結構了。Threads把影片數據移到了 "video_player" 字段下，而且字段名也變了：
- playback_url (新) vs playable_url (舊)
- hd_url (新) vs playable_url_hd (舊)

現在我來修復代碼。需要更新兩個地方：

1. 在 details_extractor.py 中添加新的 GraphQL 攔截模式
2. 更新數據提取路徑

請讓我直接修改這些文件。我會使用 search_replace 工具來更新代碼。
```

### 階段4：代碼修復實施

**🤖 LLM代理**：
```python
# 我正在更新 details_extractor.py
# 1. 添加新的查詢攔截
if "ThreadsVideoPlayerQuery" in response.url:
    video_player = data.get("data", {}).get("video_player", {})
    for key in ("hd_url", "playback_url"):
        if video_player.get(key):
            video_urls.add(video_player[key])

# 2. 保持舊模式作為備援
if "PolarisGraphVideoPlaybackQuery" in response.url:
    # 保持原有邏輯
```

修復完成！請測試一下：
`python test_triple_backup_system.py`

如果第1層GraphQL開始有結果，我們就成功了！
```

### 階段5：修復驗證

**👤 用戶**：
```
測試結果好多了！
📊 各層成效統計: 直接攔截=0 | GraphQL=2 | __NEXT_DATA__=0 | play()劫持=1 | DOM=0
🎬 影片1(完整URL): https://instagram.fkhh5-1.fna.fbcdn.net/v/video123.mp4

GraphQL層級恢復了！但是為什麼第0層直接攔截還是0？
```

**🤖 LLM代理**：
```
太棒了！主要問題已經解決，GraphQL層級恢復了，這是最重要的。

第0層直接攔截為0是正常的，因為：
1. 直接攔截依賴影片文件的實際網路請求
2. 如果GraphQL已經提供了URL，瀏覽器可能不會重複請求
3. 第0層主要是作為其他層級都失效時的最後備援

當前狀態很健康：
- ✅ GraphQL層級：2個URL（主要來源）
- ✅ play()劫持：1個URL（備援確認）
- ✅ 總體成功率：恢復正常

系統已經完全恢復！建議更新監控，記錄這次發現的新模式。
```

---

## 🔢 場景2：數據準確性突然下降

### 階段1：問題發現

**👤 用戶**：
```
數據好像有問題，留言數變成0了，之前明明是有數據的
測試結果：
❤️ 按讚數: 675
💬 留言數: 0  ← 這個之前是22
🔄 轉發數: 13
📤 分享數: 68
```

**🤖 LLM代理**：
```
這是典型的數據提取退化問題。我需要診斷幾個可能原因：

1. HTML結構變化導致正則表達式失效
2. 硬編碼範圍限制過於嚴格
3. 混合策略邏輯問題

請運行測試並提供詳細日誌：
python test_triple_backup_system.py > debug.log 2>&1

然後請告訴我日誌中關於留言數的部分，特別是：
- "📊 JSON提取留言數" 的結果
- "💬 補齊留言數" 是否出現
- 任何包含 "comments" 的日誌行
```

### 階段2：日誌分析

**👤 用戶**：
```
日誌中關於留言數的部分：
2025-08-06 23:59:37,172 - INFO -    📊 JSON提取留言數: 22
2025-08-06 23:59:37,883 - INFO -    🎯 HTML解析成功: {'likes': 675, 'comments': 0, 'reposts': 13, 'shares': 68}

看起來JSON提取到了22，但最終結果變成0了？
```

**🤖 LLM代理**：
```
找到問題了！這是混合策略的數據丟失問題：
1. JSON提取成功：22 ✅
2. 混合策略處理後：0 ❌

這表明混合策略的範圍限制或邏輯有問題，把正確的數據給覆蓋了。

我需要檢查 html_parser.py 中的範圍限制。很可能是：
```python
# 問題代碼：範圍太嚴格
if metric == "comments" and 20 <= value <= 50:  # 22在範圍內但可能被其他邏輯覆蓋
```

讓我直接修復這個問題，放寬範圍限制並改進後備邏輯。
```

### 階段3：快速修復

**🤖 LLM代理執行修復**：
```python
# 修復範圍限制
if metric == "comments" and 0 <= value <= 200:  # 擴大範圍

# 修復後備邏輯
if not result.get("comments"):
    if original_data.get("comments"):  # 使用原始數據作為後備
        result["comments"] = original_data["comments"]
```

**🤖 LLM代理**：
```
修復完成！主要修改：
1. 擴大了合理範圍限制（0-200）
2. 加強了後備邏輯，確保不會丟失有效數據
3. 改進了評分機制，不再依賴硬編碼目標值

請測試：`python test_triple_backup_system.py`

期待看到留言數恢復到22！
```

---

## 🖼️ 場景3：圖片數量異常

### 階段1：問題報告

**👤 用戶**：
```
圖片數量爆炸了，一個影片貼文抓到15張圖片，明明應該只有1-2張
🖼️ 圖片數量: 15
估計是把留言區的圖片也抓進來了
```

**🤖 LLM代理**：
```
這是圖片過濾失效的問題。我需要了解：

1. 系統是否有卡頓？（可能是選擇器太複雜）
2. 主貼文圖片提取是否成功？

請看一下測試日誌中的這幾行：
- "🖼️ 圖片提取結果: 主貼文=?個, 總計=?個"
- 是否有 "⚠️ 圖片數量異常多" 的警告
- 系統響應時間是否正常

如果系統卡頓，我會優先簡化邏輯；如果只是過濾不準，我會加強選擇器。
```

### 階段2：診斷結果

**👤 用戶**：
```
日誌顯示：
🖼️ 圖片提取結果: 主貼文=0個, 總計=15個
⚠️ 圖片數量異常多(15個)，可能包含留言區圖片

系統沒有卡頓，就是主貼文圖片提取完全失效，全部走回退邏輯了
```

**🤖 LLM代理**：
```
清楚了！主貼文選擇器全面失效（0個），導致走回退邏輯抓到留言區圖片（15個）。

這表明Threads更新了DOM結構，我們的主貼文選擇器不再有效：
```python
# 當前失效的選擇器
'article img'  # 可能不再適用
'main img'     # 可能結構變化
```

我需要：
1. 更新主貼文選擇器
2. 加強回退邏輯的過濾

但首先，你能提供一個當前測試頁面的URL嗎？我可以分析可能的新選擇器模式。
```

### 階段3：協作分析

**👤 用戶**：
```
測試URL: https://www.threads.com/@netflixtw/post/DM_vwNio_wb

我可以用瀏覽器開發者工具看看DOM結構嗎？你希望我重點看什麼？
```

**🤖 LLM代理**：
```
非常好！請用開發者工具檢查：

1. **找主貼文圖片元素**：
   - 右鍵點擊你認為是"主貼文"的圖片
   - 選擇"檢查元素"
   - 告訴我這個圖片元素的父容器結構

2. **重點查看**：
   - 圖片是否還在 `<article>` 標籤內？
   - 是否有新的 `data-*` 屬性？
   - 父容器是否有特殊的 class 或 role？

3. **找區分特徵**：
   - 主貼文區域vs留言區域有什麼明顯區別？
   - 是否有 `[data-pressable-container]` 或類似屬性？

把你看到的HTML結構（主貼文圖片的前3層父元素）貼給我。
```

### 階段4：基於分析的修復

**👤 用戶**：
```html
主貼文圖片的結構：
<div data-visualcompletion="media-vc">
  <div role="button">
    <div style="...">
      <img src="..." />
    </div>
  </div>
</div>

留言區圖片的結構：
<div class="comment-media">
  <img src="..." />
</div>
```

**🤖 LLM代理**：
```
太棒了！我看到明顯的區分特徵：

主貼文圖片特徵：
- ✅ `data-visualcompletion="media-vc"`  ← 這是關鍵！
- ✅ 嵌套在 `role="button"` 內

留言區圖片特徵：
- ❌ `class="comment-media"`  ← 明顯區別

我來立即更新選擇器：

```python
# 新的精確選擇器
main_post_selectors = [
    'div[data-visualcompletion="media-vc"] img',  # 主要特徵
    'div[role="button"] img',                     # 備用特徵
    'img[src*="t51.2885-15"]',                   # URL特徵（保留）
]

# 同時排除留言區
exclude_selectors = [
    '.comment-media img',
    '[class*="comment"] img'
]
```

修復中...完成！請測試看看主貼文圖片提取是否恢復。
```

---

## 🔄 場景4：系統完全崩潰

### 階段1：緊急情況

**👤 用戶**：
```
系統完全掛了！
錯誤信息：
Traceback (most recent call last):
  File "test_triple_backup_system.py", line 45, in test_triple_backup_extraction
    filled_posts = await extractor.fill_post_details_from_page(...)
PlaywrightError: Target page, context or browser has been closed
```

**🤖 LLM代理**：
```
這是瀏覽器進程崩潰！可能原因：
1. Threads新增了強力反爬蟲檢測
2. 瀏覽器參數不再適用
3. 內存洩漏或資源耗盡

緊急恢復步驟：

**立即操作**：
1. 重啟所有相關進程
2. 清理臨時文件
3. 回滾到上一個穩定版本

**診斷命令**：
```bash
# 檢查瀏覽器進程
tasklist | findstr chrome
tasklist | findstr playwright

# 清理
taskkill /f /im chrome.exe
taskkill /f /im playwright.exe
```

請先執行清理，然後告訴我：是否是突然開始的？之前有任何變更嗎？
```

### 階段2：回滾與恢復

**👤 用戶**：
```
清理完成。這個問題是在我們更新瀏覽器參數後開始的：
--disable-blink-features=AutomationControlled

之前運行正常
```

**🤖 LLM代理**：
```
找到問題了！新的反自動化檢測參數可能觸發了Threads的封鎖機制。

**立即回滾**：
我來移除或修改這個參數：

```python
# 問題參數
"--disable-blink-features=AutomationControlled"  # 移除

# 替代方案
"--disable-blink-features=AutomationControlled,WebRTC"  # 或改為更細粒度
```

**安全的瀏覽器參數組合**：
```python
args=[
    "--no-sandbox",
    "--disable-dev-shm-usage", 
    "--autoplay-policy=no-user-gesture-required",
    # 移除高風險參數
]
```

修復完成！請測試基本功能是否恢復。
```

---

## 📋 標準對話模板

### 🔍 故障報告模板

**👤 用戶報告格式**：
```
【問題類型】: 影片提取/數據準確性/圖片過量/系統崩潰
【症狀描述】: 具體現象
【測試結果】: 粘貼關鍵測試輸出
【環境信息】: 最近是否有變更
【錯誤信息】: 如果有的話
```

### 🤖 LLM代理響應模板

**標準響應結構**：
```
【問題確認】: 復述和分類問題
【診斷指令】: 明確的下一步操作
【資訊需求】: 需要用戶提供的具體信息
【預期結果】: 說明操作後應該看到什麼
```

### 🔧 修復確認模板

**👤 用戶確認格式**：
```
【修復結果】: 具體的測試結果
【問題狀態】: 完全解決/部分改善/仍有問題
【新問題】: 如果有新出現的問題
【下一步】: 是否需要進一步操作
```

---

## 🎯 關鍵成功要素

### 1. **明確的資訊交換**
- 用戶：提供準確的錯誤信息和測試結果
- LLM：給出具體的診斷步驟和修復指令

### 2. **分階段處理**
- 不要一次解決所有問題
- 每個階段有明確的目標和驗證點

### 3. **保持溝通**
- 每個操作後都報告結果
- 遇到意外情況立即反饋

### 4. **文檔記錄**
- 記錄成功的修復方案
- 更新監控機制

---

**使用這個對話流程，我們可以在30分鐘內恢復大部分故障！** 🚀

*流程版本: 2025.1.7*  
*適用於: Threads爬蟲系統升級版*