"""
修復版內容提取器
基於攔截到的 BarcelonaProfileThreadsTabRefetchableDirectQuery API
"""

import asyncio
import json
import httpx
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(Path(__file__).parent))

from common.config import get_auth_file_path

# 修復後的參數
FIXED_DOC_ID = "24435639366126837"  # 從攔截結果中獲得
QUERY_NAME = "BarcelonaProfileThreadsTabRefetchableDirectQuery"

# 測試目標
TEST_USERNAME = "threads"  # 使用threads官方帳號進行測試

class FixedContentExtractor:
    """修復版內容提取器 - 使用新發現的API"""
    
    def __init__(self):
        self.auth_data = None
        self.headers = None
        self.cookies = None
        
    async def load_auth(self):
        """載入認證信息"""
        auth_file_path = get_auth_file_path()
        if not auth_file_path.exists():
            raise FileNotFoundError(f"認證檔案 {auth_file_path} 不存在")
            
        self.auth_data = json.loads(auth_file_path.read_text())
        self.cookies = {cookie['name']: cookie['value'] for cookie in self.auth_data.get('cookies', [])}
        
        # 從攔截結果中復制基本headers
        self.headers = {
            "accept": "*/*",
            "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "sec-ch-prefers-color-scheme": "dark",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "x-asbd-id": "129477",
            "x-fb-friendly-name": QUERY_NAME,
            "x-fb-lsd": "",  # 需要從cookies中獲取
            "x-ig-app-id": "238260118697367"
        }
        
        # 從cookies中獲取關鍵認證信息
        self.fb_dtsg = None
        # 查找各種可能的dtsg格式
        dtsg_candidates = ['fb_dtsg', 'dtsg', 'datr']
        for candidate in dtsg_candidates:
            if candidate in self.cookies:
                self.fb_dtsg = self.cookies[candidate]
                break
        
        # 設置LSD - 查找各種可能的lsd格式  
        lsd_candidates = ['lsd', 'x-fb-lsd', '_js_lsd']
        for candidate in lsd_candidates:
            if candidate in self.cookies:
                self.headers["x-fb-lsd"] = self.cookies[candidate]
                break
        
        # 如果還是沒有找到，嘗試從localStorage中獲取
        if not self.fb_dtsg:
            local_storage = self.auth_data.get('localStorage', [])
            for item in local_storage:
                if 'dtsg' in item.get('name', '').lower():
                    self.fb_dtsg = item.get('value', '')
                    break
        
        # 調試信息：列出所有可用的cookies
        print(f"   📋 可用cookies: {list(self.cookies.keys())}")
        if hasattr(self.auth_data, 'get') and 'localStorage' in self.auth_data:
            local_storage_keys = [item.get('name', '') for item in self.auth_data.get('localStorage', [])]
            print(f"   📋 可用localStorage: {local_storage_keys[:10]}...")  # 只顯示前10個
        
        print(f"✅ 認證載入完成")
        print(f"   📊 Cookies: {len(self.cookies)} 個")
        print(f"   🔑 FB DTSG: {'是' if self.fb_dtsg else '否'}")
        print(f"   🎫 LSD: {'是' if self.headers.get('x-fb-lsd') else '否'}")
    
    async def get_user_posts(self, username: str, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
        """獲取用戶的貼文列表"""
        print(f"🔍 獲取 @{username} 的貼文 (限制: {limit} 篇)...")
        
        # 基於攔截結果構建variables
        variables = {
            "after": None,
            "before": None,
            "first": limit,
            "last": None,
            "userID": None,  # 需要查找userID
            "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasSelfReplyContextrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasInlineReplyComposerrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider": False,
            "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider": False,
            "__relay_internal__pv__IsTagIndicatorEnabledrelayprovider": True,
            "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasSelfThreadCountrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasSpoilerStylingInforelayprovider": True,
            "__relay_internal__pv__BarcelonaHasDeepDiverelayprovider": False,
            "__relay_internal__pv__BarcelonaQuotedPostUFIEnabledrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasTopicTagsrelayprovider": True,
            "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasDisplayNamesrelayprovider": False,
            "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider": True,
            "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": True,
            "__relay_internal__pv__BarcelonaImplicitTrendsGKrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False
        }
        
        # 如果是threads官方帳號，使用已知的userID
        if username == "threads":
            variables["userID"] = "63082166531"  # 從攔截結果中獲得
        else:
            print(f"⚠️ 未知用戶的userID，可能需要先查詢")
            return None
        
        # 構建POST數據 (基於攔截結果的格式)
        post_data = {
            "av": "17841476239996865",
            "__user": "0",
            "__a": "1",
            "__req": "1",
            "__hs": "20306.HYP:barcelona_web_pkg.2.1...0",
            "dpr": "3",
            "__ccg": "EXCELLENT",
            "__rev": "1025565823",
            "__s": "ibysx9:m2yycf:cxltff",
            "__hsi": "7535438263061243030",
            "__comet_req": "29",
            "fb_dtsg": self.fb_dtsg or "",
            "jazoest": "26145",
            "lsd": self.headers.get("x-fb-lsd", ""),
            "__spin_r": "1025565823",
            "__spin_b": "trunk",
            "__spin_t": str(int(datetime.now().timestamp())),
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": QUERY_NAME,
            "variables": json.dumps(variables),
            "server_timestamps": "true",
            "doc_id": FIXED_DOC_ID
        }
        
        # URL編碼
        encoded_data = urllib.parse.urlencode(post_data)
        
        # 發送請求
        async with httpx.AsyncClient(
            headers=self.headers,
            cookies=self.cookies,
            timeout=30.0,
            follow_redirects=True
        ) as client:
            try:
                response = await client.post(
                    "https://www.threads.com/graphql/query",
                    data=encoded_data
                )
                
                print(f"   📡 HTTP {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if "errors" in result:
                            print(f"   ❌ GraphQL 錯誤: {result['errors']}")
                            return None
                        
                        if "data" in result and result["data"] and "mediaData" in result["data"]:
                            media_data = result["data"]["mediaData"]
                            posts = self._parse_posts_from_response(media_data)
                            print(f"   ✅ 成功獲取 {len(posts)} 篇貼文")
                            return posts
                        else:
                            print(f"   ❌ 未預期的響應結構: {list(result.get('data', {}).keys()) if result.get('data') else 'No data'}")
                            return None
                    
                    except Exception as e:
                        print(f"   ❌ 解析響應失敗: {e}")
                        # 保存原始響應用於調試
                        debug_file = Path(f"debug_response_{datetime.now().strftime('%H%M%S')}.json")
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        print(f"   📁 原始響應已保存: {debug_file}")
                        return None
                
                else:
                    print(f"   ❌ HTTP 錯誤: {response.status_code}")
                    print(f"   📄 錯誤內容: {response.text[:500]}...")
                    return None
            
            except Exception as e:
                print(f"   ❌ 請求失敗: {e}")
                return None
    
    def _parse_posts_from_response(self, media_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """從響應中解析貼文數據"""
        posts = []
        
        try:
            edges = media_data.get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                thread_items = node.get("thread_items", [])
                
                for item in thread_items:
                    post_data = item.get("post", {})
                    if not post_data:
                        continue
                    
                    # 提取基本信息
                    pk = post_data.get("pk", "")
                    user_info = post_data.get("user", {})
                    username = user_info.get("username", "")
                    
                    # 提取計數數據
                    like_count = post_data.get("like_count", 0)
                    text_info = post_data.get("text_post_app_info", {})
                    direct_reply_count = text_info.get("direct_reply_count", 0)
                    repost_count = text_info.get("repost_count", 0)
                    reshare_count = text_info.get("reshare_count", 0)
                    
                    # 提取內容
                    content = ""
                    text_fragments = text_info.get("text_fragments", {})
                    fragments = text_fragments.get("fragments", [])
                    for fragment in fragments:
                        if fragment.get("fragment_type") == "plaintext":
                            content += fragment.get("plaintext", "")
                    
                    # 構建結果
                    post_result = {
                        "pk": pk,
                        "username": username,
                        "content": content.strip(),
                        "like_count": like_count,
                        "comment_count": direct_reply_count,
                        "repost_count": repost_count,
                        "share_count": reshare_count,
                        "url": f"https://www.threads.com/@{username}/post/{pk}" if username and pk else "",
                        "extracted_at": datetime.now().isoformat(),
                        "source": "fixed_extractor",
                        "success": True
                    }
                    
                    posts.append(post_result)
                    
                    print(f"      📄 @{username}: {like_count} 讚, {direct_reply_count} 留言")
                    if content:
                        print(f"         📝 內容: {content[:50]}...")
        
        except Exception as e:
            print(f"   ❌ 解析貼文數據失敗: {e}")
        
        return posts

async def main():
    """主函數"""
    print("🚀 修復版內容提取器")
    print(f"🎯 使用新發現的API: {QUERY_NAME}")
    print(f"📋 Doc ID: {FIXED_DOC_ID}")
    
    extractor = FixedContentExtractor()
    
    try:
        # 載入認證
        await extractor.load_auth()
        
        # 測試獲取貼文
        posts = await extractor.get_user_posts(TEST_USERNAME, limit=5)
        
        if posts:
            print(f"\n🎉 修復成功！獲取到 {len(posts)} 篇貼文")
            
            # 保存結果
            result_file = Path(f"fixed_extraction_result_{datetime.now().strftime('%H%M%S')}.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(posts, f, indent=2, ensure_ascii=False)
            print(f"📁 結果已保存: {result_file}")
            
            # 顯示統計
            total_likes = sum(p.get('like_count', 0) for p in posts)
            total_comments = sum(p.get('comment_count', 0) for p in posts)
            print(f"\n📊 統計:")
            print(f"   👍 總按讚數: {total_likes:,}")
            print(f"   💬 總留言數: {total_comments:,}")
            
            print(f"\n✅ API修復完成！現在可以將此邏輯整合到主爬蟲中。")
        else:
            print(f"\n😞 修復測試失敗")
    
    except Exception as e:
        print(f"\n❌ 修復測試過程中發生錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(main())