以下是新問題
我要處理爬蟲流程 
我要先從一位帳號主頁進入 
然後抓100則 依照觀看數排序
Apify 可以方便抓到主頁多則貼文的URL 但是沒有 VIEWS

所以用 Apify Actor 爬到URL 之後
我需要再URL 前面加上 https://r.jina.ai/
這樣可以得到jina 處理過的格式
 jina 可以抓到 views

但是 jina 有views 卻沒有詳細的

  "likes_count": "",
  "comments_count": "",
  "reposts_count": "",
  "shares_count": ""

只有用數字表示  如果其中一個是0  會無法對齊欄位
只知道缺一個  如果都滿 就是所需要的

所以如果缺一欄  就要先截圖  再把螢幕圖片送到gemini 2.5 flash 影像辨識
把欄位補齊

補齊之後 就有五個數值
  "views_count": "",
  "likes_count": "",
  "comments_count": "",
  "reposts_count": "",
  "shares_count": ""

權重以 views_count 最重
likes_count與comments_count 其次
接著開始把100則貼文排序

以上流程 需要工程化 而且要適用於A2A架構
這步驟就是先抓貼文 然後要把五個欄位先填滿
沒填滿的要用影像辨識填滿
然後排序
接著才下一步 依照文字或是圖片還是影片 下一步驟

請問這樣要怎麼規劃???

#####

#####
💬 訊息：調用 Apify Actor: curious_coder/threads-scraper
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> Status: RUNNING, Message:
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:29.879Z ACTOR: Pulling Docker image of build JsuYrg5tPYSUHbnjv from registry.
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:29.880Z ACTOR: Creating Docker container.
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:30.005Z ACTOR: Starting Docker container.
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:33.420Z INFO  System info {"apifyVersion":"3.2.6","apifyClientVersion":"2.11.1","crawleeVersion":"3.12.1","osType":"Linux","nodeVersion":"v18.20.5"}
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:33.744Z INFO  BasicCrawler: Starting the crawler.
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:58.473Z WARN  BasicCrawler: Reclaiming failed request back to the list or queue. Request timeout after 20000ms
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:36:58.474Z     at file:///usr/src/app/src/client.js:195:19 {"id":"mxO5nXSKUM5jTl2","url":"https://www.threads.net/@09johan24","retryCount":1}
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:37:11.827Z INFO  BasicCrawler: All requests from the queue have been processed, the crawler will shut down.
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:37:11.924Z INFO  BasicCrawler: Final request statistics: {"requestsFinished":1,"requestsFailed":0,"retryHistogram":[null,1],"requestAvgFailedDurationMillis":null,"requestAvgFinishedDurationMillis":13349,"requestsFinishedPerMinute":2,"requestsFailedPerMinute":0,"requestTotalDurationMillis":13349,"requestsTotal":1,"crawlerRuntimeMillis":38103}
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> 2025-07-23T03:37:11.929Z INFO  BasicCrawler: Finished! Total 1 requests: 1 succeeded, 0 failed. {"terminal":true}
[apify.threads-scraper runId:2nGcih12JwIuukQtq] -> Status: SUCCEEDED, Message:
📋 狀態：running - Apify Actor 執行中，等待結果...
📈 進度：20.0% - 處理貼文 1/5
📈 進度：40.0% - 處理貼文 2/5
📈 進度：60.0% - 處理貼文 3/5
📈 進度：80.0% - 處理貼文 4/5
📈 進度：100.0% - 處理貼文 5/5

✅ 抓取完成！
📊 總共抓取：5 個 URL
⏱️  處理時間：51.81 秒
👤 用戶：09johan24🔍 URL 格式驗證： 
   預期格式：https://www.threads.com/@username/post/code
   ✅ https://www.threads.com/@09johan24/post/C2RM1lbPWV2
   ✅ https://www.threads.com/@09johan24/post/DMaUaSnTRLQ
   ✅ https://www.threads.com/@09johan24/post/DMaQlaET9wO
   ✅ https://www.threads.com/@09johan24/post/DMaHMSqTdFs
   ✅ https://www.threads.com/@09johan24/post/DMZmCsHTA9U

✅ 有效 URL：5/5
####



####
LLM 截圖 分析

提取主要貼文下顯示的以下數字，分別的數量是多少?

views數量:
數量(愛心):  
留言(氣泡):
轉發(旋轉):
分享(紙飛機):
{
  "views_count": "",
  "likes_count": "",
  "comments_count": "",
  "reposts_count": "",
  "shares_count": ""
}
#####

# pip install screenshotone

from screenshotone import Client, TakeOptions

# create API client
client = Client("lE6SdLD9Vftg0Q", "ZYX53aD4rYjHqw")

# set up options
options = TakeOptions.url("https://www.threads.com/@earthmomltpodcast/post/DMa5BCWy27Z").format("jpg")
    .block_ads(true)
    .block_cookie_banners(true)
    .block_banners_by_heuristics(false)
    .block_trackers(true)
    .delay(0)
    .timeout(60)
    .response_type("by_format")
    .image_quality(80)

# generate URL
url = client.generate_take_url(options)
print(url)
# expected output: https://api.screenshotone.com/take?url=...

# or download the screenshot
image = client.take(options)

# store the screenshot in a file
with open("path_to_file.ext", "wb") as f:
    f.write(image)
# the screenshot is stored in the provided file path

###################

### 把需求拆成 **4 個明確步驟 + 3 支可獨立部署的 Agent**

（每支 Agent 都符合 A2A：`POST /a2a/message`，並附一張 AgentCard 註冊到 MCP）

```
          ┌────────────┐      threads-scraper Actor
UI ──▶ ORC│CrawlerAgent│──┐───────────────────────────┐
          └────────────┘  │      (JSON  無 views)     │
                           ▼                           │
          ┌────────────┐  Step 2                      Step 1
          │JinaAgent   │──r.jina.ai/URL───────────────┘
          └────────────┘  (views 但缺 4 欄)

                 │  若 still missing 欄位
                 ▼
          ┌────────────┐  Step 3 (fallback)
          │VisionAgent │──ScreenshotOne→Gemini-Flash
          └────────────┘  (補 likes/comments/… )

                 │ 全 5 欄就緒
                 ▼
          Step 4 ──> ORC 做排序 → 後續分析/生成
```

---

## 1. 介面契約（共用 Pydantic Model）

```python
class Metrics(BaseModel):
    url: str
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    reposts: int | None = None
    shares: int | None = None
```

所有 Agent 都 **收/回** `List[Metrics]`，未取到的欄位保持 `None`。

---

## 2. 三支 Agent 的核心邏輯

### 2-1 CrawlerAgent  (Apify)

```python
async def run(username: str, limit: int = 100) -> list[Metrics]:
    run = await apify.actor("threads-scraper").call(
        {"username": username, "max_posts": limit}
    )
    ds = apify.dataset(run["defaultDatasetId"])
    posts = []
    async for item in ds.iterate_items():
        posts.append(Metrics(url=item["url"]))          # 只先存 URL
    return posts
```

### 2-2 JinaAgent  (views 解析)

```python
async def run(batch: list[Metrics]) -> list[Metrics]:
    out = []
    async with httpx.AsyncClient() as cli:
        for m in batch:
            r = await cli.get(f"https://r.jina.ai/http://{m.url.lstrip('https://')}")
            data = json.loads(r.text)["meta"]
            m.views = int(data.get("views", 0))
            # 其餘四欄不一定存在 → 保持 None
            out.append(m)
    return out
```

### 2-3 VisionAgent  (ScreenshotOne + Gemini-Flash)

```python
SCREEN_API = Client(os.getenv("SHOT_KEY"), os.getenv("SHOT_SECRET"))
GEMINI     = genai.GenerativeModel("gemini-2.0-flash")

SS_PROMPT = """
提取螢幕截圖中貼文主要統計數字：
views、愛心、留言、轉發、分享（若不存在輸出 0）；
僅回傳 JSON: {"views":x,"likes":x,"comments":x,"reposts":x,"shares":x}
"""

async def run(partials: list[Metrics]) -> list[Metrics]:
    out = []
    for m in partials:
        if all([m.views, m.likes, m.comments, m.reposts, m.shares]):
            out.append(m); continue            # 已完整
        # 1. Screenshot
        take_url = SCREEN_API.generate_take_url(
            TakeOptions.url(m.url).format("jpg").response_type("by_format")
        )
        img_bytes = httpx.get(take_url).content
        # 2. Gemini Vision
        res = GEMINI.generate_content(
            [genai.ImagePart(img_bytes, mime_type="image/jpeg"),
             genai.TextPart(SS_PROMPT)]
        )
        d = json.loads(res.text)
        m.likes    = m.likes    or d["likes"]
        m.comments = m.comments or d["comments"]
        m.reposts  = m.reposts  or d["reposts"]
        m.shares   = m.shares   or d["shares"]
        out.append(m)
    return out
```

---

## 3. Orchestrator Workflow（簡化版）

```python
async def collect_and_sort(username: str):
    posts = await call_agent("crawler",  {"username": username})
    posts = await call_agent("jina",     {"posts": posts})
    posts = await call_agent("vision",   {"posts": posts})

    # 權重計算
    def score(m: Metrics):
        return (m.views or 0)*1.0 + (m.likes or 0)*0.3 + (m.comments or 0)*0.3
    posts.sort(key=score, reverse=True)
    return posts[:100]    # 已完整並按權重排序
```

> **call\_agent**＝A2A client：傳進 `{"role":"user","parts":[{"kind":"data","data":...}]}`，串流接收進度。

---

## 4. AgentCard 範例（VisionAgent）

```json
{
  "name": "Vision Metrics Filler",
  "url": "http://vision-agent:8003/",
  "version": "0.1.0",
  "capabilities": { "streaming": true },
  "skills": [{
    "id": "fill_metrics",
    "description": "補齊貼文互動數（likes/comments/...）",
    "input_schema": {
      "type":"array",
      "items": { "$ref": "#/definitions/Metrics" }
    }
  }]
}
```

---

## 5. 佇列 / 併發 策略

* **CrawlerAgent**：一次把 100 URL 放進 `asyncio.gather`，Apify 仍只算 1 CU。
* **VisionAgent**：Screenshot & Gemini 貴 → `Semaphore(5)` 控制併發，並將失敗 URL 重試 ≤ 2 次。
* 若日後要水平擴張，再把 three Agents 接 NATS Queue；MVP 可直接 `asyncio`.

---

## 6. 後續步驟

1. **實測** 5 條 URL，確保 Gemini prompt 能可靠抓五欄。
2. 加入 **單元測試**：

   * `test_jina_parse_views()`
   * `test_vision_fill_missing(metrics_with_hole)`
3. Orchestrator 排序後把 list 存 SQLite；接下來的「文本 vs 圖片/影片」判斷即可根據 `media_urls` 做分流。

這樣整條「抓取 → 補齊五欄 → 排序」在 A2A 內拆出三個職責明確的 Agent，**不必一次引入 Redis/NATS** 就能先跑通；當貼文量或同時用戶變多，再把 VisionAgent 拆多副本掛佇列即可。
