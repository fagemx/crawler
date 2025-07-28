下面直接給「AI 代理開發者」一套 **可落地、一步步照抄就能跑通** 的說明，重點放在：

1. **最容易卡住的三個坑**
2. **必改的程式碼斷點（含範例 diff）**
3. **單元自我測試清單** —— 開發完成後複查即可

---

## 0. 為什麼你現在跑不起來？

| 常見卡點                                                 | 立即症狀                                                                     | 修正關鍵                                                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| **`self.context` 在 `fill_views_from_page` 是 `None`** | `Browser context 未初始化`                                                   | 把 context 從 `fetch_posts()` 傳進 `fill_views_from_page()`，或改寫成在 `fill_views_from_page` 內部 `async with` 新建。 |
| **`self.posts_data` 不存在**                            | `AttributeError: 'PlaywrightLogic' object has no attribute 'posts_data'` | 直接回傳 `posts_to_fill` 即可；不要引用不存在的屬性。                                                                      |
| **頁面還沒載入就抓 selector**                                | `TimeoutError waiting for selector`                                      | 赴約式寫法：`await page.wait_for_selector(selector, state="visible")`；並在 goto 後加 `wait_until="networkidle"`.   |
| **中文 / 英文介面抓不到**                                     | 只拿到英文 `views` 或中文 `次瀏覽` 其中一種                                             | selector 用逗號分隔的複合：`"span:has-text('次瀏覽'), span:has-text('views')"`                                       |

---

## 1. 必改程式碼（最小 diff）

### 1‑A `fetch_posts`: 保留 `context` 供後續使用

```diff
 async with async_playwright() as p:
     browser = await p.chromium.launch(...)
-    ctx = await browser.new_context(...)
+    self.context = await browser.new_context(...)  # <── 保存到 self
-    page = await ctx.new_page()
+    page = await self.context.new_page()
```

> 📌 **記得在 finally 關閉**
>
> ```python
> finally:
>     if self.context:
>         await self.context.close()
>         self.context = None
> ```

### 1‑B `fill_views_from_page`：去掉不存在的 `self.posts_data`、用 `async with` 建 page

```diff
-        tasks = []
-        for post in posts_to_fill:
-            page = await self.context.new_page()
-            tasks.append(fetch_single_view(post, page))
-        await asyncio.gather(*tasks)
-        return self.posts_data
+        async def wrap(post):
+            async with self.context.new_page() as page:
+                await fetch_single_view(post, page)
+        await asyncio.gather(*(wrap(p) for p in posts_to_fill))
+        return posts_to_fill
```

### 1‑C `parse_post_data`: 給 `views_count` 初值（API 可能撈不到）

```diff
 views_count = first_of(post, *FIELD_MAP["view_count"])
 return PostMetrics(
     ...
     views_count=views_count if views_count is not None else None,
 )
```

---

## 2. 執行流程圖（簡化）

```
fetch_posts()
└─ 建 browser + context
   └─ 滾動 + 攔截 GraphQL → parse_post_data()
      └─ PostMetrics(images, videos, views=None)
   └─ 關閉 page (但保留 context)
fill_views_from_page(posts, context)
└─ semaphore 控制並發 new_page()
   └─ goto(貼文URL) → wait span → parse_views_text
   └─ 回填 post.views_count
└─ 關閉 context
return PostMetricsBatch
```

---

## 3. 單元自測清單

1. **API 直帶 view**

   * 把 Threads 影片貼文 mock 成含 `feedback_info.view_count=1234`
   * `parse_post_data` 回傳的 `views_count == 1234`

2. **`fill_views_from_page` 補值**

   * 給一筆 `views_count=None` 的貼文 URL：
     `https://www.threads.com/@meta/post/CrEu6kGy5Xj`
   * 執行 `fill_views_from_page`，應回填一個 ≥ 0 的 `views_count`

3. **並發限流**

   * 同時塞 20 個貼文，Semaphore=5
   * 觀察網路請求，同時間最大 tab ≤ 5

4. **中文 / 英文雙語**

   * 把瀏覽器 `locale` 改 `zh-TW` → 應抓到「次瀏覽」
   * 改 `en-US` → 抓到 `views`

5. **圖片 / 影片 URL**

   * 輪播貼文 3 圖 1 mp4
   * `images` 長度 == 3；`videos` 長度 == 1；URL 均為 https\://… .jpg / .mp4

---

## 4. Bonus：提高穩定度的小技巧

| 技巧                     | 代碼片段                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| 禁掉圖片、影片載入節省頻寬          | `page.route("**/*.{png,jpg,jpeg,gif,mp4,webp}", lambda r: r.abort())` |
| 遇 429 自動 back‑off      | \`\`\`python                                                          |
| if resp.status == 429: |                                                                       |

```
await asyncio.sleep(random.uniform(3,6))
```

````|
| 解析 `blob:` video | 攔 `response`；判斷 `content-type: video/mp4`；若 URL 含 `&dl=1` 即可存 |

---

## 5. 給 AI 代理的最終指令

> **「先跑第一階段 `fetch_posts` 拿文字 + image/video URL；再把同批資料丟給 `fill_views_from_page` 回填 `views_count`；最後 return。」**

開發時 **嚴格對照上面 diff 與測試清單**。任何 assertion 不過＝回來修，不要跳步。

完成後部屬，即可一次拿到：

```json
{
  "post_id": "3679375184…",
  "content": "都是漂亮女生呀…",
  "likes_count": 17,
  "views_count": 1619000,
  "images": ["https://…n.jpg", "…"],
  "videos": ["https://…n.mp4"]
}
````

—— 這樣就達到「文字＋數據＋圖片＋影片＋views」全量抓取 💯。


########################

下面給你一套「**最小修改路徑**」── 只改 `parse_post_data()` 這一層，就能把 **圖片 & 影片 URL** 一併寫進 `PostMetrics`；整體流程還是一次爬，一次回傳，不必再跑第二趟。

> **為什麼一次做就好？**
> 你現在抓的 GraphQL 回應 (`thread_items[].carousel_media[]`) 已經內含所有 `image_versions2[].url` 與 `video_versions[].url`。只要把它們撈出來放進結果欄位即可，並不需要再打其他 API 或再滾一次。

---

## 1 擴充 `PostMetrics`

在 `common/models.py`（或你定義 `PostMetrics` 的地方）：

```python
from typing import List, Optional
from pydantic import BaseModel

class PostMetrics(BaseModel):
    url: str
    post_id: str
    username: str
    source: str
    processing_stage: str

    # 數據
    likes_count: int
    comments_count: int
    reposts_count: int
    shares_count: int
    views_count: Optional[int] = None

    content: str = ""
    created_at: Optional[str] = None   # 你原本用 str/ISO
    # ⬇️ 新增兩欄
    images: List[str] = []
    videos: List[str] = []
```

（如果你想保留向後相容，也可以叫 `media_images`, `media_videos` 之類。）

---

## 2 在 `parse_post_data()` 抓取媒體

把下面這段 **替換 / 插到 parse\_post\_data() 末端**（讚數、留言數都抓完之後；註解標了 `# --- MEDIA ---`）：

```python
# --- MEDIA -------------------------------------------------------------
images, videos = [], []

def append_image(url):
    if url and url not in images:
        images.append(url)

def append_video(url):
    if url and url not in videos:
        videos.append(url)

def best_candidate(candidates: list[dict], prefer_mp4=False):
    """
    從 image_versions2 或 video_versions 裡挑「寬度最大的那個」URL
    """
    if not candidates:
        return None
    key = "url" if not prefer_mp4 else "url"    # 都叫 url
    return max(candidates, key=lambda c: c.get("width", 0)).get(key)

# 1) 單圖 / 單片
if "image_versions2" in post:
    append_image(best_candidate(post["image_versions2"].get("candidates", [])))
if "video_versions" in post:
    append_video(best_candidate(post["video_versions"], prefer_mp4=True))

# 2) 輪播 carousel_media
for media in post.get("carousel_media", []):
    if "image_versions2" in media:
        append_image(best_candidate(media["image_versions2"]["candidates"]))
    if "video_versions" in media:
        append_video(best_candidate(media["video_versions"], prefer_mp4=True))

# -----------------------------------------------------------------------
```

> * `image_versions2.candidates`：每張圖有多個尺寸，挑 `width` 最大的。
> * `video_versions`：通常會給 480p / 720p 幾個版本，一樣取最大。你也可以改成本身就要「第一個」或「is\_dash\_manifest == False」等條件。

---

### 把結果寫進 `PostMetrics` 物件

原本 `return PostMetrics(` 的地方，加兩行參數即可：

```python
return PostMetrics(
    url=url,
    post_id=str(post_id),
    username=username,
    source="playwright",
    processing_stage="playwright_crawled",

    likes_count=...,
    comments_count=...,
    # 其餘省略
    created_at=created_at,

    images=images,
    videos=videos,
)
```

---

## 3 API 傳回值自動帶出圖片/影片欄位

因為 `PostMetricsBatch.posts` 裡每一筆已經含 `images` / `videos`，
FastAPI 會照 `pydantic` model 自動序列化，前端拿到的 JSON 大概像：

```json
{
  "url": "https://www.threads.com/@starettoday/post/DMPxDxkyjNL",
  "post_id": "3679375184253039435",
  "likes_count": 17,
  "comments_count": 0,
  ...
  "created_at": "2025-07-18T10:48:43+00:00",
  "images": [
    "https://.../522633702_17922979218102263_n.jpg",
    "https://.../523186690_17922979209102263_n.jpg"
  ],
  "videos": [
    "https://.../17922979218102263_n.mp4"
  ]
}
```

---

## 4 下游怎麼「分次」下載？

* **第一次**（現在的 Playwright 任務）：只抓文字 & 數據 & 媒體 URL → 回存 DB。
* **第二次**：另外寫一個 **worker**，遍歷資料庫裡還沒下載的 `images` / `videos` URL，用 aiohttp 或 requests 分批下載到 S3 / 本地；失敗重試、並記 `file_path` 或 `cdn_url` 即可。

這樣優點是：

1. Playwright 不必下載大檔，速度快又省頻寬。
2. 下載器可以獨立重試，不怕單張圖 timeout 讓整趟爬蟲失敗。

如果你只是要「URL」，那一次爬完就結束，不需要第二步。

---

## 5 常見陷阱備忘

| 問題                      | 解法                                                                                                         |
| ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| 影片只有 `blob:` 視訊流        | GraphQL `video_versions[].url` 才是真 .mp4；你的程式取那個就行。                                                         |
| 影片縮圖混進 images           | 我們只看 `image_versions2` → 圖； `video_versions` → 影片，兩邏輯分流。                                                   |
| 解析輪播時少抓                 | `carousel_media` loop 一定要有；Threads 輪播有時是 `carousel_media`, 有時 `items`（你先用 `carousel_media` 不夠再加 fallback）。 |
| 大貼文沒有 `image_versions2` | 偶爾 IG 舊貼文叫 `display_resources`；可再 `first_of` 裡擴個 `"display_resources"`。                                    |

---

### 🚀 就這麼簡單

1. **改 `PostMetrics`** → 加 `images`, `videos`.
2. **在 `parse_post_data()` 加 media 抽取邏輯**（上面整塊可直接貼）。
3. 其他程式碼不用動；一次爬、一次回傳。

先這樣實作看看，有問題再丟訊息！
