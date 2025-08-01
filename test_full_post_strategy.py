"""
實現完整的「計數 + 內容」雙查詢策略
基於用戶提供的專業解決方案
"""

import sys
import asyncio
import json
import re
import httpx
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# 添加 zstd 支持
try:
    import zstandard
    HAS_ZSTD = True
except ImportError:
    print("⚠️ 建議安裝 zstandard: pip install zstandard")
    HAS_ZSTD = False

# Windows asyncio 修復
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Page

# 導入必要的解析函數
sys.path.append(str(Path(__file__).parent))
from common.config import get_auth_file_path

# 測試貼文
TEST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_CODE = "DMyvZJRz5Cz"

# 預期數據
EXPECTED_DATA = {
    "likes": 233,
    "comments": 66,
    "reposts": 6,
    "shares": 34
}

# 常數
APP_ID = "238260118697367"
# 嘗試多個可能的 manifest URL
MANIFEST_URLS = [
    "https://www.threads.com/data/manifest.json",
    "https://www.threads.com/static/bundles/metro/barcelona_web-QueryMap.json",
    "https://static.cdninstagram.com/rsrc.php/v4/manifest.json",
    "https://www.threads.com/qp/batch_fetch_web/",
]
COUNTS_DOC_ID = "6637585034415426"  # 固定的 counts doc_id

class ThreadsFullPostFetcher:
    def __init__(self, auth_file_path: Path):
        """初始化 Threads 完整貼文抓取器"""
        # 讀取認證
        auth_data = json.loads(auth_file_path.read_text())
        self.cookies = {c["name"]: c["value"] for c in auth_data["cookies"]}
        
        # 設置 HTTP 客戶端
        self.headers = {
            "x-ig-app-id": APP_ID,
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "accept": "*/*",
            "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.threads.com",
            "referer": "https://www.threads.com/",
            "x-requested-with": "XMLHttpRequest",
            "x-csrftoken": self.cookies.get("csrftoken", ""),
            "x-asbd-id": "129477",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        
        # 如果有 authorization token，添加它
        if "authorization" in [c["name"].lower() for c in auth_data["cookies"]]:
            auth_cookie = next((c for c in auth_data["cookies"] if c["name"].lower() == "authorization"), None)
            if auth_cookie:
                self.headers["authorization"] = auth_cookie["value"]
        
        self.http_client = httpx.AsyncClient(
            cookies=self.cookies,
            headers=self.headers,
            timeout=30.0,
            http2=True
        )
        
        self.content_doc_id = None
        self.lsd_token = None
    
    async def _load_manifest(self) -> Optional[str]:
        """載入並解壓縮 manifest.json"""
        try:
            print("      🔄 載入 manifest.json...")
            response = await self.http_client.get("https://www.threads.com/data/manifest.json")
            if response.status_code != 200:
                print(f"         ❌ HTTP {response.status_code}")
                return None
            
            raw_content = response.content
            
            # 檢查 Content-Encoding header
            content_encoding = response.headers.get("content-encoding", "").lower()
            print(f"         📋 Content-Encoding: {content_encoding or 'none'}")
            
            # 嘗試不同的解壓縮方法
            manifest_text = None
            
            # 方法1: 直接當作 UTF-8 文本
            try:
                manifest_text = raw_content.decode('utf-8')
                print(f"         ✅ 直接解析為 UTF-8 成功 ({len(manifest_text):,} 字符)")
                return manifest_text
            except UnicodeDecodeError:
                print(f"         ⚠️ 不是純 UTF-8，嘗試解壓縮...")
            
            # 方法2: zstd 解壓縮
            if content_encoding == "zstd" or raw_content.startswith(b'\x28\xb5\x2f\xfd'):
                if HAS_ZSTD:
                    try:
                        print(f"         🔄 嘗試 zstd 解壓縮...")
                        decompressed = zstandard.ZstdDecompressor().decompress(raw_content)
                        manifest_text = decompressed.decode('utf-8')
                        print(f"         ✅ zstd 解壓縮成功 ({len(manifest_text):,} 字符)")
                        return manifest_text
                    except Exception as e:
                        print(f"         ❌ zstd 解壓縮失敗: {e}")
                else:
                    print(f"         ❌ 需要 zstandard 庫來解壓縮")
            
            # 方法3: gzip 解壓縮
            if content_encoding == "gzip" or raw_content.startswith(b'\x1f\x8b'):
                try:
                    import gzip
                    print(f"         🔄 嘗試 gzip 解壓縮...")
                    decompressed = gzip.decompress(raw_content)
                    manifest_text = decompressed.decode('utf-8')
                    print(f"         ✅ gzip 解壓縮成功 ({len(manifest_text):,} 字符)")
                    return manifest_text
                except Exception as e:
                    print(f"         ❌ gzip 解壓縮失敗: {e}")
            
            # 方法4: 保存原始內容用於調試
            debug_file = Path(f"debug_manifest_raw_{datetime.now().strftime('%H%M%S')}.bin")
            with open(debug_file, 'wb') as f:
                f.write(raw_content)
            print(f"         📁 已保存原始 manifest 到: {debug_file}")
            print(f"         📋 原始數據前20字節: {raw_content[:20]}")
            
            return None
            
        except Exception as e:
            print(f"         ❌ 載入 manifest 失敗: {e}")
            return None

    async def get_content_doc_id(self) -> Optional[str]:
        """從 manifest.json 獲取內容查詢的 doc_id"""
        if self.content_doc_id:
            return self.content_doc_id
        
        print("   🔄 從 manifest.json 獲取最新 doc_id...")
        
        manifest_text = await self._load_manifest()
        if not manifest_text:
            print("   ❌ 無法載入 manifest")
            return None
        
        # 新的搜索模式：找「含 PostPage 且有 media/__typename 的查詢」
        patterns = [
            # 主要模式 - 任何包含 PostPage 的查詢
            r'"([A-Za-z0-9]+PostPage[^"]*)":\s*\{\s*"id":\s*"(\d{15,19})"',
            # 備用模式
            r'"([A-Za-z0-9]*Thread[^"]*)":\s*\{\s*"id":\s*"(\d{15,19})"',
            r'"([A-Za-z0-9]*Media[^"]*)":\s*\{\s*"id":\s*"(\d{15,19})"',
        ]
        
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, manifest_text)
            if matches:
                # 取第一個匹配項
                query_name, doc_id = matches[0]
                self.content_doc_id = doc_id
                print(f"      ✅ 找到內容查詢: {query_name} -> doc_id: {doc_id}")
                return self.content_doc_id
        
        print(f"      ❌ 在 manifest 中未找到匹配的 doc_id")
        
        # 保存 manifest 用於調試
        debug_file = Path(f"debug_manifest_parsed_{datetime.now().strftime('%H%M%S')}.txt")
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(manifest_text)
        print(f"      📁 已保存解析後的 manifest 到: {debug_file}")
        
        return None
    
    async def get_lsd_token(self) -> Optional[str]:
        """獲取 LSD token（已從 GraphQL response 中獲取）"""
        if self.lsd_token:
            return self.lsd_token
        
        print("   ⚠️ 尚未從 GraphQL 響應中獲取 LSD token")
        return None
    
    async def get_counts_from_pk(self, pk: str) -> Optional[Dict]:
        """使用 PK 獲取計數數據"""
        print(f"   📊 使用 PK {pk} 獲取計數數據...")
        try:
            # 確保有 LSD token
            lsd_token = await self.get_lsd_token()
            if not lsd_token:
                print(f"   ❌ 沒有 LSD token，無法請求計數")
                return None
            
            variables = json.dumps({"postIDs": [pk]})
            
            # 🔧 使用新的 payload 格式
            data = f"lsd={lsd_token}&doc_id={COUNTS_DOC_ID}&variables={variables}"
            
            # headers
            headers = {
                "x-fb-lsd": lsd_token
            }
            
            response = await self.http_client.post(
                "https://www.threads.com/graphql/query",
                data=data,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            if "data" in result and "data" in result["data"] and "posts" in result["data"]["data"]:
                posts = result["data"]["data"]["posts"]
                if posts and len(posts) > 0:
                    post = posts[0]
                    print(f"   ✅ 成功獲取計數數據")
                    return post
            
            print(f"   ❌ 計數數據格式異常")
            return None
            
        except Exception as e:
            print(f"   ❌ 獲取計數數據失敗: {e}")
            return None
    
    async def get_content_from_pk(self, pk: str) -> Optional[Dict]:
        """使用 PK 獲取完整內容"""
        doc_id = await self.get_content_doc_id()
        if not doc_id:
            return None
        
        print(f"   📝 使用 PK {pk} 和 doc_id {doc_id} 獲取完整內容...")
        try:
            # 確保有 LSD token
            lsd_token = await self.get_lsd_token()
            if not lsd_token:
                print(f"   ❌ 沒有 LSD token，無法請求內容")
                return None
            
            # 🔧 使用新的變數格式
            variables = json.dumps({
                "postID_pk": pk,               # 新格式：postID → postID_pk
                "withShallowTree": False,      # 必須為 False 才能獲得完整內容
                "includePromotedPosts": False
            })
            
            # 🔧 使用新的 payload 格式
            data = f"lsd={lsd_token}&doc_id={doc_id}&variables={variables}"
            
            # headers
            headers = {
                "x-fb-lsd": lsd_token
            }
            
            response = await self.http_client.post(
                "https://www.threads.com/graphql/query",
                data=data,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            if "data" in result and "media" in result["data"]:
                media = result["data"]["media"]
                print(f"   ✅ 成功獲取完整內容")
                return media
            
            print(f"   ❌ 內容數據格式異常")
            # 保存響應用於調試
            debug_file = Path(f"debug_content_response_{datetime.now().strftime('%H%M%S')}.json")
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"   📁 已保存內容響應到: {debug_file}")
            
            return None
            
        except Exception as e:
            print(f"   ❌ 獲取完整內容失敗: {e}")
            return None
    
    async def extract_pk_from_gate_page(self, post_url: str) -> tuple[Optional[str], list]:
        """從 Gate 頁面攔截獲取 PK，返回 (pk, captured_pks_list)"""
        print(f"   🚪 從 Gate 頁面攔截 PK...")
        
        captured_pks = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            
            context = await browser.new_context(
                storage_state=str(get_auth_file_path()),
                user_agent=self.headers["user-agent"],
                viewport={"width": 375, "height": 812},  # iPhone 尺寸
                locale="zh-TW",
                bypass_csp=True
            )
            
            await context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            
            page = await context.new_page()
            
            # 攔截計數查詢
            async def response_handler(response):
                url = response.url.lower()
                qname = response.request.headers.get("x-fb-friendly-name", "")
                
                # 🔑 從第一個 GraphQL 響應中提取 LSD token
                if "/graphql" in url and not self.lsd_token:
                    lsd = (response.request.headers.get("x-fb-lsd") or 
                           response.headers.get("x-fb-lsd"))
                    if lsd:
                        self.lsd_token = lsd
                        print(f"      🔑 從 GraphQL 響應獲取 LSD token: {lsd[:10]}...")
                
                if ("/graphql" in url and 
                    "DynamicPostCountsSubscriptionQuery" in qname and 
                    response.status == 200):
                    
                    try:
                        data = await response.json()
                        if ("data" in data and "data" in data["data"] and 
                            "posts" in data["data"]["data"]):
                            
                            posts = data["data"]["data"]["posts"]
                            for post in posts:
                                if isinstance(post, dict) and "pk" in post:
                                    pk = post["pk"]
                                    like_count = post.get("like_count", 0)
                                    captured_pks.append({
                                        "pk": pk,
                                        "like_count": like_count,
                                        "post": post
                                    })
                                    print(f"      📝 攔截到 PK: {pk}, 讚數: {like_count}")
                    except:
                        pass
            
            page.on("response", response_handler)
            
            # 導航到頁面
            await page.goto(post_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # 輕微滾動觸發更多請求
            await page.evaluate("window.scrollTo(0, 100)")
            await asyncio.sleep(2)
            
            await browser.close()
        
        # 分析攔截到的 PK
        if captured_pks:
            print(f"   📊 攔截到 {len(captured_pks)} 個 PK")
            
            # 選擇最有可能的 PK（讚數最高的）
            best_pk = max(captured_pks, key=lambda x: x["like_count"])
            selected_pk = best_pk["pk"]
            
            print(f"   🎯 選擇 PK: {selected_pk} (讚數: {best_pk['like_count']})")
            return selected_pk, captured_pks
        else:
            print(f"   ❌ 未攔截到任何 PK")
            return None, []
    
    async def fetch_full_post(self, post_url: str) -> Optional[Dict]:
        """獲取完整貼文（計數 + 內容）"""
        print(f"\n🔍 獲取完整貼文: {post_url}")
        
        # 步驟1: 從 Gate 頁面攔截 PK
        pk, captured_pks = await self.extract_pk_from_gate_page(post_url)
        if not pk:
            print(f"❌ 無法獲取 PK")
            return None
        
        # 步驟2: 使用 PK 獲取計數和內容
        # 優先嘗試從已攔截的數據中找到匹配的計數
        counts = None
        for captured in captured_pks:
            if captured["pk"] == pk:
                counts = captured["post"]
                print(f"   ✅ 使用已攔截的計數數據")
                break
        
        # 如果沒有找到，嘗試 API 獲取
        if not counts:
            counts = await self.get_counts_from_pk(pk)
        
        # 獲取內容
        content = await self.get_content_from_pk(pk)
        
        # 檢查結果
        if isinstance(counts, Exception):
            print(f"❌ 獲取計數失敗: {counts}")
            counts = None
        
        if isinstance(content, Exception):
            print(f"❌ 獲取內容失敗: {content}")
            content = None
        
        if not counts:
            print(f"❌ 無法獲取計數數據")
            return None
        
        # 步驟3: 合併數據
        print(f"   🔄 合併計數和內容數據...")
        
        text_info = counts.get("text_post_app_info", {})
        merged_post = {
            "post_id": pk,
            "code": TARGET_CODE,  # 從 URL 提取
            "author": post_url.split("/@")[1].split("/")[0] if "/@" in post_url else "unknown",
            
            # 計數數據（來自計數 API）
            "like_count": counts.get("like_count", 0),
            "comment_count": text_info.get("direct_reply_count", 0),
            "repost_count": text_info.get("repost_count", 0),
            "share_count": text_info.get("reshare_count", 0),
            
            # 內容數據（來自內容 API）
            "content": "",
            "images": [],
            "videos": [],
            
            # 元數據
            "data_source": "dual_api",
            "has_content_api": content is not None,
            "raw_counts": counts,
            "raw_content": content
        }
        
        # 如果有內容數據，填充內容字段
        if content:
            # 文字內容
            if "caption" in content and content["caption"]:
                merged_post["content"] = content["caption"].get("text", "")
            
            # 圖片
            if "image_versions2" in content and content["image_versions2"]:
                candidates = content["image_versions2"].get("candidates", [])
                merged_post["images"] = [c["url"] for c in candidates if "url" in c]
            
            # 影片
            if "video_versions" in content and content["video_versions"]:
                merged_post["videos"] = [v["url"] for v in content["video_versions"] if "url" in v]
        
        print(f"   ✅ 成功合併數據")
        print(f"      讚數: {merged_post['like_count']}")
        print(f"      留言數: {merged_post['comment_count']}")
        print(f"      轉發數: {merged_post['repost_count']}")
        print(f"      分享數: {merged_post['share_count']}")
        print(f"      內容長度: {len(merged_post['content'])}")
        print(f"      圖片數: {len(merged_post['images'])}")
        print(f"      影片數: {len(merged_post['videos'])}")
        
        return merged_post
    
    async def close(self):
        """關閉 HTTP 客戶端"""
        await self.http_client.aclose()

async def test_full_post_strategy():
    """測試完整貼文策略"""
    print("🚀 測試完整貼文策略（計數 + 內容雙查詢）...")
    
    auth_file_path = get_auth_file_path()
    if not auth_file_path.exists():
        print(f"❌ 認證檔案不存在: {auth_file_path}")
        return
    
    fetcher = ThreadsFullPostFetcher(auth_file_path)
    
    try:
        result = await fetcher.fetch_full_post(TEST_URL)
        
        if result:
            print(f"\n📊 完整貼文數據:")
            print(f"   ID: {result['post_id']}")
            print(f"   代碼: {result['code']}")
            print(f"   作者: {result['author']}")
            print(f"   讚數: {result['like_count']:,}")
            print(f"   留言數: {result['comment_count']:,}")
            print(f"   轉發數: {result['repost_count']:,}")
            print(f"   分享數: {result['share_count']:,}")
            print(f"   內容: {result['content'][:100]}...")
            print(f"   圖片: {len(result['images'])} 張")
            print(f"   影片: {len(result['videos'])} 個")
            
            # 驗證準確性
            print(f"\n🎯 準確性驗證:")
            accuracy_checks = []
            
            if abs(result['like_count'] - EXPECTED_DATA['likes']) <= 5:
                accuracy_checks.append("✅ 讚數準確")
            else:
                accuracy_checks.append(f"❌ 讚數偏差 ({result['like_count']} vs {EXPECTED_DATA['likes']})")
            
            if result['comment_count'] == EXPECTED_DATA['comments']:
                accuracy_checks.append("✅ 留言數準確")
            else:
                accuracy_checks.append(f"❌ 留言數偏差 ({result['comment_count']} vs {EXPECTED_DATA['comments']})")
            
            if result['repost_count'] == EXPECTED_DATA['reposts']:
                accuracy_checks.append("✅ 轉發數準確")
            else:
                accuracy_checks.append(f"❌ 轉發數偏差 ({result['repost_count']} vs {EXPECTED_DATA['reposts']})")
            
            if result['share_count'] == EXPECTED_DATA['shares']:
                accuracy_checks.append("✅ 分享數準確")
            else:
                accuracy_checks.append(f"❌ 分享數偏差 ({result['share_count']} vs {EXPECTED_DATA['shares']})")
            
            for check in accuracy_checks:
                print(f"   {check}")
            
            # 計算準確率
            correct_count = len([c for c in accuracy_checks if c.startswith("✅")])
            accuracy_rate = (correct_count / len(accuracy_checks)) * 100
            
            print(f"\n🏆 整體準確率: {accuracy_rate:.1f}% ({correct_count}/{len(accuracy_checks)})")
            
            if accuracy_rate >= 75:
                print("🎉 策略成功！數據高度準確！")
            else:
                print("⚠️ 策略需要進一步調整")
            
            # 保存結果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = Path(f"full_post_result_{timestamp}.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n📁 完整結果已保存至: {result_file}")
            
        else:
            print(f"❌ 獲取完整貼文失敗")
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await fetcher.close()

async def main():
    """主函數"""
    await test_full_post_strategy()

if __name__ == "__main__":
    asyncio.run(main())