"""
GraphQL 直接 API 測試腳本 (LSD Token 策略)
作者：AI Assistant (基於使用者的卓越分析)
日期：2025-08-01

核心策略：
1. GET 公開帳號頁面 (如 https://www.threads.net/@instagram) 取得 LSD token。
2. 帶著 LSD token 和 cookies 直接 POST 到 GraphQL API。
3. 完全棄用 Playwright 進行資料擷取，僅用於初始認證。
"""
import re
import json
import asyncio
import httpx
from pathlib import Path
import sys

# --- 設定路徑 ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from common.config import get_auth_file_path

# --- 常數 ---
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
DOC_ID = "7428920450586442"
CONCURRENT_REQUESTS = 10

# --- 輔助函式 ---
def parse_views_text(text: str) -> int:
    """將 '1.2萬次瀏覽' 或 '1,234 views' 轉換為整數"""
    if not isinstance(text, str):
        return 0
    text = text.lower().strip()
    text = re.sub(r'(,|次瀏覽|views|view)', '', text)
    
    number = 0
    if '萬' in text or '万' in text:
        num_part = text.replace('萬', '').replace('万', '')
        number = float(num_part) * 10000
    elif 'k' in text:
        num_part = text.replace('k', '')
        number = float(num_part) * 1000
    elif 'm' in text:
        num_part = text.replace('m', '')
        number = float(num_part) * 1000000
    else:
        try:
            number = float(text)
        except (ValueError, TypeError):
            return 0
            
    return int(number)
    
class ThreadsGraphQLClient:
    """一個使用 httpx 和 LSD Token 策略的 Threads GraphQL 客戶端 (最終穩定版)"""
    def __init__(self, auth_data):
        self.cookies = {c["name"]: c["value"] for c in auth_data.get("cookies", [])}
        self.headers = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
            "X-IG-App-ID": "238260118697367",
            "X-FB-Friendly-Name": "CometSinglePostQuery"
        }
        self.lsd_token = None
        self.http_client = httpx.AsyncClient(http2=True, cookies=self.cookies, headers=self.headers, timeout=20.0)
        self._token_lock = asyncio.Lock()

    async def _get_lsd_token(self, force=False):
        if self.lsd_token and not force:
            return self.lsd_token
        async with self._token_lock:
            if self.lsd_token and not force:
                return self.lsd_token

            print("🔄 正在取得新的 LSD token...")
            for url in (
                "https://www.threads.net/@instagram",
                "https://www.threads.net/@zuck",
                "https://www.threads.net/@meta",
            ):
                try:
                    # 允許自動跟隨重導向 (httpx 預設最多20次)，以獲取最終的 HTML 頁面
                    r = await self.http_client.get(url, follow_redirects=True)
                    r.raise_for_status()
                    m = re.search(r'"token"\s*:\s*"([^"]+)"', r.text)
                    if m:
                        self.lsd_token = m.group(1)
                        print("✅ LSD token:", self.lsd_token[:10], "…")
                        return self.lsd_token
                except httpx.RequestError as e:
                    print(f"   -> {url} 發生網路錯誤 ({type(e).__name__})，換下一個…")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"   -> {url} 處理時發生未知錯誤 ({type(e).__name__})，換下一個…")
                    await asyncio.sleep(1)

            raise RuntimeError("🛑 連續多個公開頁都抓不到 LSD token")

    async def fetch_views(self, post_code: str, retries=2):
        """使用 post_code 取得單篇貼文的觀看數，包含 token 自動刷新"""
        await self._get_lsd_token()
        
        variables = {"code": post_code, "surface": "WEB_POST"}
        params = {"doc_id": DOC_ID}
        
        for attempt in range(retries + 1):
            form_data = {
                "variables": json.dumps(variables),
                "lsd": self.lsd_token
            }
            request_headers = self.headers.copy()
            request_headers["X-FB-LSD"] = self.lsd_token
        
            try:
                r = await self.http_client.post(
                    "https://www.threads.net/api/graphql",
                    params=params,
                    data=form_data,
                    headers=request_headers,
                    follow_redirects=False # 不跟隨重導向
                )
                r.raise_for_status()
                data = r.json()

                if "errors" in data or "data" not in data:
                    print(f"❌ 貼文 {post_code}: GraphQL API 回傳錯誤: {data.get('errors', '未知錯誤')}")
                    return 0

                thread_items = data.get("data", {}).get("containing_thread", {}).get("thread_items", [])
                if not thread_items:
                    return 0

                post_data = thread_items[0].get("post", {})
                
                view_count = (post_data.get("video_info", {}).get("play_count") or
                              post_data.get("feedback_info", {}).get("view_count") or
                              parse_views_text(post_data.get("accessibility_caption", "")))
                return view_count

            except httpx.HTTPStatusError as e:
                print(f"❌ 貼文 {post_code}: HTTP 狀態錯誤 {e.response.status_code} (嘗試 {attempt+1}/{retries+1})")
                if e.response.status_code == 429:
                    wait_time = min(2**attempt, 60)
                    print(f"   -> 速率限制，等待 {wait_time} 秒後重試...")
                    await asyncio.sleep(wait_time)
                elif e.response.status_code in (400, 401, 302):
                    print(f"   -> Token 可能已失效 (HTTP {e.response.status_code})，強制刷新...")
                    if attempt < retries:
                         await self._get_lsd_token(force=True)
                else:
                    break
            except Exception as e:
                print(f"❌ 貼文 {post_code}: 發生未預期錯誤 (嘗試 {attempt+1}/{retries+1}) - {e}")
                break
        
        return 0

async def main():
    print("🚀 GraphQL 直接 API 測試開始 (LSD Token 策略 - 最終穩定版)...")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 錯誤: 找不到認證檔案 {auth_file}。請先執行 save_auth.py。")
        return

    try:
        with open(auth_file, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
    except Exception as e:
        print(f"❌ 讀取或解析 {auth_file} 失敗: {e}")
        return

    if "cookies" not in auth_data or not auth_data["cookies"]:
        print("❌ 認證檔案中沒有找到 cookies。")
        return
        
    print(f"✅ 認證 Cookie ({len(auth_data['cookies'])} 個) 載入成功。")

    client = ThreadsGraphQLClient(auth_data)

    test_cases = {
        "成功 [萬]": "DMxwLDUy4JD",
        "成功 [數字]": "DMyvZJRz5Cz",
        "成功 [數字 (少)]": "DMwKpQlThM8",
    }
    
    print(f"🔧 準備併發測試 {len(test_cases)} 個案例 (併發數: {CONCURRENT_REQUESTS})...")
    
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    
    async def worker(label, code):
        async with semaphore:
            print(f"   -> 開始抓取: {label} ({code})")
            views = await client.fetch_views(code)
            print(f"   <- 完成抓取: {label} ({code}) -> {views} 次瀏覽")
            return label, views

    tasks = [worker(label, code) for label, code in test_cases.items()]
    results = await asyncio.gather(*tasks)
    
    await client.http_client.aclose()

    print("\n" + "--- 測試結果 ---")
    all_successful = True
    for label, views in results:
        if views > 0:
            print(f"✅ {label}: {views} 次瀏覽")
        else:
            print(f"❌ {label}: 獲取失敗或瀏覽數為 0")
            all_successful = False
    print("-" * 18)

    if all_successful:
        print("✅✅✅ 所有測試案例均成功獲取瀏覽數！LSD Token 策略驗證通過！✅✅✅")
    else:
        print("⚠️ 部分測試案例失敗，請檢查上面的錯誤訊息。")


if __name__ == "__main__":
    asyncio.run(main())
