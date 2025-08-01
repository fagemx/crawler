"""
Instagram Mobile API - Threads 觀看數擷取器
版本：2.0 (最終版 - Claim "0" 策略)
作者：AI Assistant (基於使用者提供的卓越策略)
日期：2025-08-01

核心策略:
1.  使用 `save_auth.py` 產生的有效 Cookies。
2.  在請求標頭中，將 `X-IG-WWW-Claim` 固定設為 "0"。
3.  在請求標頭中，加入 `Referer: https://www.instagram.com/`。
4.  直接對 Threads GraphQL API 發送單一 POST 請求，無需任何預先操作。
"""
import asyncio
import json
import uuid
import httpx
from pathlib import Path
import sys

# --- 設定路徑 ---
try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from common.config import get_auth_file_path
except ImportError:
    def get_auth_file_path():
        return Path("agents/playwright_crawler/auth.json")

# --- 常數 ---
UA = ("Mozilla/5.0 (Linux; Android 11; Pixel 6) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0.0.0 Mobile Safari/537.36")

DOC_ID = "7428920450586442"
APP_ID = "238260118697367"
ASBD_ID = "129477"

class MobileThreadsClient:
    """一個採用 Claim "0" 策略的極簡 Threads API 客戶端"""
    def __init__(self, auth_json: Path):
        auth = json.loads(auth_json.read_text())
        cookies = {c["name"]: c["value"] for c in auth["cookies"]}
        
        # 從 cookies 中提取 csrftoken 以加入標頭
        csrftoken = cookies.get("csrftoken")
        if not csrftoken:
            raise ValueError("auth.json 中缺少 'csrftoken' cookie，請重新執行 save_auth.py。")

        self.http_client = httpx.AsyncClient(
            http2=True,
            headers={
                "User-Agent": UA,
                "X-IG-App-ID": APP_ID,
                "X-ASBD-ID": ASBD_ID,
                "X-IG-Device-ID": str(uuid.uuid4()),
                "X-IG-WWW-Claim": "0",
                "X-CSRFToken": csrftoken,                  # ← 核心修正
                "Referer": "https://www.instagram.com/",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=cookies,
            timeout=20.0,
        )

    async def get_views(self, post_code: str) -> int:
        """獲取指定貼文的觀看數"""
        variables = {"code": post_code, "surface": "WEB_POST"}
        params = {"doc_id": DOC_ID}
        data = {"variables": json.dumps(variables, separators=(",", ":"))}

        try:
            response = await self.http_client.post(
                "https://www.threads.net/api/graphql",
                params=params,
                data=data,
                follow_redirects=False,
            )
            response.raise_for_status()
            json_data = response.json()
            
            post = json_data["data"]["containing_thread"]["thread_items"][0]["post"]
            return (
                post.get("video_info", {}).get("play_count") or
                post.get("feedback_info", {}).get("view_count") or 0
            )
        except json.JSONDecodeError:
            print(f"❌ 獲取或解析貼文 {post_code} 失敗: JSONDecodeError")
            if 'response' in locals() and response is not None:
                print(f"   -> 伺服器回傳了非 JSON 內容 (狀態碼: {response.status_code})。")
                print(f"   -> 回應內容預覽: {response.text[:300]}")
            return 0
        except (httpx.HTTPStatusError, KeyError, IndexError, TypeError) as e:
            print(f"❌ 獲取或解析貼文 {post_code} 失敗: {type(e).__name__}")
            if isinstance(e, httpx.HTTPStatusError):
                print(f"   -> 狀態碼: {e.response.status_code}, 回應: {e.response.text[:200]}")
            return 0

    async def close(self):
        """關閉 httpx 客戶端"""
        await self.http_client.aclose()

# ------------ Demo ------------
async def demo():
    """執行範例測試"""
    print("🚀 Mobile API Claim '0' 策略測試開始...")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 錯誤: 找不到認證檔案 {auth_file}。請先執行 save_auth.py。")
        return

    client = MobileThreadsClient(auth_file)
    
    test_codes = {
        "萬": "DMxwLDUy4JD",
        "多": "DMyvZJRz5Cz",
        "少": "DMwKpQlThM8",
    }
    
    async def worker(label, code):
        views = await client.get_views(code)
        return label, code, views

    tasks = [worker(label, code) for label, code in test_codes.items()]
    results = await asyncio.gather(*tasks)

    print("\n--- 測試結果 ---")
    for label, code, views in results:
        status = "✅" if views > 0 else "❌"
        print(f"{status} {label} ({code}): {views:,} 次瀏覽")

    await client.close()
    print("\n✅ 測試完成。")

if __name__ == "__main__":
    asyncio.run(demo())
