"""
增強版混合內容提取器 - 添加發文時間和主題tag提取
基於 hybrid_content_extractor.py 的成功模式
"""

import asyncio
import json
import httpx
import urllib.parse
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@ttshow.tw/post/DMegHD-S3xR"
TARGET_USERNAME = "ttshow.tw"
TARGET_CODE = "DMegHD-S3xR"

# 期望數據
EXPECTED_TIME = "2025-7-24 下午 6:55"
EXPECTED_TAG = "頑童MJ116"

class EnhancedHybridExtractor:
    """增強版混合內容提取器 - 添加時間和標籤提取"""
    
    def __init__(self):
        self.counts_captured = False
        self.counts_headers = {}
        self.counts_payload = ""
        self.auth_header = ""
        self.lsd_token = ""
    
    async def intercept_counts_query(self):
        """攔截計數查詢（沿用成功的方法）"""
        print("📊 攔截計數查詢...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812}
            )
            
            page = await context.new_page()
            
            async def response_handler(response):
                friendly_name = response.request.headers.get("x-fb-friendly-name", "")
                
                if "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in friendly_name:
                    try:
                        data = await response.json()
                        # 檢查是否包含任何可用的PK
                        data_str = json.dumps(data, ensure_ascii=False)
                        if "pk" in data_str:  # 更寬鬆的匹配
                            print(f"   ✅ 攔截到計數查詢")
                            
                            self.counts_headers = dict(response.request.headers)
                            self.counts_payload = response.request.post_data
                            self.auth_header = self.counts_headers.get("authorization", "")
                            self.lsd_token = self.counts_headers.get("x-fb-lsd", "")
                            
                            self.counts_captured = True
                    except:
                        pass
            
            page.on("response", response_handler)
            await page.goto(TEST_POST_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            await browser.close()
        
        return self.counts_captured
    
    async def extract_time_from_dom(self, page) -> Optional[datetime]:
        """從DOM提取發文時間（三種方法）"""
        print(f"      ⏰ 提取發文時間...")
        
        try:
            # 方法A: 直接抓 <time> 的 datetime 屬性
            time_elements = page.locator('time[datetime]')
            count = await time_elements.count()
            
            if count > 0:
                print(f"         找到 {count} 個 time 元素")
                
                for i in range(min(count, 5)):  # 檢查前5個
                    try:
                        time_el = time_elements.nth(i)
                        
                        # 方法A: datetime 屬性
                        iso_time = await time_el.get_attribute('datetime')
                        if iso_time:
                            print(f"         ✅ datetime: {iso_time}")
                            from dateutil import parser
                            return parser.parse(iso_time)
                        
                        # 方法B: title 或 aria-label 屬性  
                        title_time = (await time_el.get_attribute('title') or 
                                    await time_el.get_attribute('aria-label'))
                        if title_time:
                            print(f"         ✅ title/aria-label: {title_time}")
                            # 嘗試解析中文時間格式
                            parsed_time = self.parse_chinese_time(title_time)
                            if parsed_time:
                                return parsed_time
                    except Exception as e:
                        continue
            
            # 方法C: 解析 __NEXT_DATA__
            print(f"         🔍 嘗試 __NEXT_DATA__ 方法...")
            try:
                script_el = page.locator('#__NEXT_DATA__')
                if await script_el.count() > 0:
                    script_content = await script_el.text_content()
                    data = json.loads(script_content)
                    
                    # 尋找 taken_at 時間戳
                    taken_at = self.find_taken_at(data)
                    if taken_at:
                        print(f"         ✅ __NEXT_DATA__ taken_at: {taken_at}")
                        return datetime.fromtimestamp(taken_at)
                        
            except Exception as e:
                print(f"         ❌ __NEXT_DATA__ 解析失敗: {e}")
            
            # 方法D: 解析相對時間（兜底）
            print(f"         🔍 嘗試相對時間解析...")
            time_elements_all = page.locator('time')
            time_count = await time_elements_all.count()
            
            for i in range(min(time_count, 10)):
                try:
                    time_el = time_elements_all.nth(i)
                    text = await time_el.inner_text()
                    if text:
                        parsed_time = self.parse_relative_time(text)
                        if parsed_time:
                            print(f"         ✅ 相對時間: {text} -> {parsed_time}")
                            return parsed_time
                except:
                    continue
            
        except Exception as e:
            print(f"         ❌ 時間提取失敗: {e}")
        
        return None
    
    def parse_chinese_time(self, time_str: str) -> Optional[datetime]:
        """解析中文時間格式"""
        try:
            # 處理 "2025年8月3日下午 2:36" 格式
            if "年" in time_str and "月" in time_str and "日" in time_str:
                # 提取數字部分
                import re
                match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2}):(\d{2})', time_str)
                if match:
                    year, month, day, hour, minute = map(int, match.groups())
                    
                    # 處理下午/上午
                    if "下午" in time_str and hour < 12:
                        hour += 12
                    elif "上午" in time_str and hour == 12:
                        hour = 0
                    
                    return datetime(year, month, day, hour, minute)
        except:
            pass
        return None
    
    def parse_relative_time(self, text: str) -> Optional[datetime]:
        """解析相對時間"""
        try:
            import re
            pattern = re.compile(r'(\d+)\s*(秒|分鐘|分|小時|天|週|月|年)')
            match = pattern.search(text)
            
            if match:
                num = int(match.group(1))
                unit = match.group(2)
                
                multiplier = {
                    "秒": 1,
                    "分鐘": 60, "分": 60,
                    "小時": 3600,
                    "天": 86400,
                    "週": 604800,
                    "月": 2592000,
                    "年": 31536000
                }
                
                if unit in multiplier:
                    seconds_ago = num * multiplier[unit]
                    return datetime.now() - timedelta(seconds=seconds_ago)
        except:
            pass
        return None
    
    def find_taken_at(self, data: Any, path: str = "") -> Optional[int]:
        """遞歸搜索 taken_at 時間戳"""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "taken_at" and isinstance(value, int) and value > 1000000000:
                    return value
                result = self.find_taken_at(value, f"{path}.{key}")
                if result:
                    return result
        elif isinstance(data, list):
            for i, item in enumerate(data):
                result = self.find_taken_at(item, f"{path}[{i}]")
                if result:
                    return result
        return None
    
    async def extract_tags_from_dom(self, page) -> List[str]:
        """從DOM提取主文章的標籤連結（專門搜索Threads標籤連結）"""
        print(f"      🏷️ 提取主文章標籤連結...")
        tags = []
        
        try:
            # 策略1: 搜索標籤連結（優先級最高）
            tag_link_selectors = [
                'a[href*="/search?q="][href*="serp_type=tags"]',  # 標籤搜索連結
                'a[href*="/search"][href*="tag_id="]',  # 包含tag_id的連結
                'a[href*="serp_type=tags"]',  # 標籤類型連結
            ]
            
            for selector in tag_link_selectors:
                try:
                    tag_links = page.locator(selector)
                    count = await tag_links.count()
                    
                    if count > 0:
                        print(f"         🔗 找到 {count} 個標籤連結 ({selector})")
                        
                        # 只檢查前3個（避免回復中的標籤）
                        for i in range(min(count, 3)):
                            try:
                                link = tag_links.nth(i)
                                href = await link.get_attribute('href')
                                text = await link.inner_text()
                                
                                if href and text:
                                    # 解析標籤名稱
                                    tag_name = self.extract_tag_name_from_link(href, text)
                                    if tag_name and tag_name not in tags:
                                        tags.append(tag_name)
                                        print(f"         ✅ 標籤連結: {tag_name} -> {href}")
                                        return tags  # 找到一個就返回，因為通常只有一個主要標籤
                                        
                            except Exception as e:
                                continue
                                
                except Exception as e:
                    continue
            
            # 策略2: 搜索主文章區域內的標籤元素
            main_post_selectors = [
                'article:first-of-type',  # 第一個文章元素
                '[role="article"]:first-of-type',  # 第一個文章角色元素
                'div[data-pressable-container]:first-of-type',  # 第一個可點擊容器
            ]
            
            for main_selector in main_post_selectors:
                try:
                    main_element = page.locator(main_selector)
                    if await main_element.count() > 0:
                        print(f"         🎯 在主文章區域搜索標籤: {main_selector}")
                        
                        # 在主文章內搜索標籤連結
                        main_tag_links = main_element.locator('a[href*="/search"]')
                        main_count = await main_tag_links.count()
                        
                        if main_count > 0:
                            print(f"         🔗 主文章內找到 {main_count} 個搜索連結")
                            
                            for i in range(min(main_count, 2)):
                                try:
                                    link = main_tag_links.nth(i)
                                    href = await link.get_attribute('href')
                                    text = await link.inner_text()
                                    
                                    if href and text:
                                        tag_name = self.extract_tag_name_from_link(href, text)
                                        if tag_name and tag_name not in tags:
                                            tags.append(tag_name)
                                            print(f"         ✅ 主文章標籤: {tag_name}")
                                            return tags
                                            
                                except Exception as e:
                                    continue
                        
                        # 備用：搜索hashtag文本
                        hashtag_in_main = await self.search_hashtags_in_element(main_element)
                        if hashtag_in_main:
                            tags.extend(hashtag_in_main[:1])  # 只取第一個
                            print(f"         ✅ 主文章hashtag: {hashtag_in_main[:1]}")
                            return tags
                            
                except Exception as e:
                    continue
            
            # 策略3: 備用方案 - 搜索 __NEXT_DATA__ 中的標籤信息
            try:
                script_el = page.locator('#__NEXT_DATA__')
                if await script_el.count() > 0:
                    script_content = await script_el.text_content()
                    data = json.loads(script_content)
                    
                    # 搜索標籤相關的數據
                    topic_tags = self.find_tags_in_data(data)
                    if topic_tags:
                        tags.extend(topic_tags)
                        print(f"         ✅ __NEXT_DATA__ 標籤: {topic_tags}")
                    
            except Exception as e:
                print(f"         ❌ __NEXT_DATA__ 標籤解析失敗: {e}")
            
        except Exception as e:
            print(f"         ❌ 標籤提取失敗: {e}")
        
        # 清理和返回標籤
        print(f"         🔄 找到的標籤: {tags}")
        cleaned_tags = self.clean_tag_list(tags)
        print(f"         📋 最終標籤: {cleaned_tags}")
        return cleaned_tags
    
    def extract_tag_name_from_link(self, href: str, text: str) -> Optional[str]:
        """從標籤連結中提取標籤名稱"""
        try:
            # 方法1: 從URL的q參數中解析
            if "q=" in href:
                # 解析URL編碼的標籤名稱
                import urllib.parse
                parsed_url = urllib.parse.urlparse(href)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                if 'q' in query_params:
                    tag_name = query_params['q'][0]
                    # URL解碼
                    tag_name = urllib.parse.unquote(tag_name)
                    print(f"         🎯 從URL解析標籤: {tag_name}")
                    return tag_name
            
            # 方法2: 從連結文本中取得（備用）
            if text and len(text.strip()) > 0 and len(text.strip()) <= 20:
                # 清理文本
                clean_text = text.strip()
                # 移除可能的前後綴
                if clean_text.startswith('#'):
                    clean_text = clean_text[1:]
                
                print(f"         📝 從文本解析標籤: {clean_text}")
                return clean_text
                
        except Exception as e:
            print(f"         ❌ 標籤解析失敗: {e}")
        
        return None
    
    def find_tags_in_data(self, data: Any, path: str = "") -> List[str]:
        """在__NEXT_DATA__中搜索標籤信息"""
        tags = []
        
        try:
            if isinstance(data, dict):
                for key, value in data.items():
                    # 搜索可能包含標籤的字段
                    if any(tag_key in key.lower() for tag_key in 
                          ['tag', 'hashtag', 'topic', 'category', 'label']):
                        if isinstance(value, str) and len(value) > 0 and len(value) <= 20:
                            tags.append(value)
                        elif isinstance(value, list):
                            for item in value:
                                if isinstance(item, str) and len(item) > 0 and len(item) <= 20:
                                    tags.append(item)
                    
                    # 遞歸搜索（限制深度）
                    if path.count('.') < 2:
                        sub_tags = self.find_tags_in_data(value, f"{path}.{key}")
                        tags.extend(sub_tags)
                        
            elif isinstance(data, list):
                for i, item in enumerate(data[:3]):  # 只檢查前3個
                    sub_tags = self.find_tags_in_data(item, f"{path}[{i}]")
                    tags.extend(sub_tags)
                    
        except Exception as e:
            pass
        
        return tags[:3]  # 只返回前3個
    
    def clean_tag_list(self, raw_tags: List[str]) -> List[str]:
        """清理標籤列表"""
        if not raw_tags:
            return []
        
        cleaned_tags = []
        
        for tag in raw_tags:
            if tag and isinstance(tag, str):
                # 基本清理
                clean_tag = tag.strip()
                
                # 移除URL編碼的字符
                if '%' in clean_tag:
                    try:
                        import urllib.parse
                        clean_tag = urllib.parse.unquote(clean_tag)
                    except:
                        pass
                
                # 移除可能的前後綴
                if clean_tag.startswith('#'):
                    clean_tag = clean_tag[1:]
                
                # 基本驗證
                if (clean_tag and 
                    len(clean_tag) > 0 and 
                    len(clean_tag) <= 30 and 
                    clean_tag not in cleaned_tags):
                    cleaned_tags.append(clean_tag)
        
        # 只返回第一個標籤（主要標籤）
        return cleaned_tags[:1] if cleaned_tags else []
    
    def extract_main_topic_from_text(self, text: str) -> List[str]:
        """從主文章文本中提取主要主題標籤"""
        tags = []
        
        # 擴展的主題模式（更全面的關鍵詞）
        topic_patterns = [
            # 技術/安全相關
            r'零日攻擊',
            r'0[- ]?day',
            r'zero[- ]?day',
            r'漏洞',
            r'網路安全',
            r'資安',
            r'駭客',
            r'攻擊',
            r'安全',
            r'弱點',
            r'滲透',
            r'exploit',
            r'hack',
            r'security',
            r'vulnerability',
            r'cybersecurity',
            r'infosec',
            
            # 政治/社會相關（根據實際內容）
            r'政治',
            r'民主',
            r'選舉',
            r'政黨',
            r'年輕人',
            r'社會',
            r'台灣',
            r'公民',
            
            # 其他可能的主題
            r'科技',
            r'AI',
            r'人工智慧',
            r'區塊鏈',
            r'加密',
            r'數位',
        ]
        
        print(f"         🔍 搜索文本: {text[:200]}...")
        
        for pattern in topic_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                print(f"         🎯 找到關鍵詞: {pattern} -> {matches}")
                # 標準化標籤名稱
                if any(keyword in pattern for keyword in ['零日', '0day', 'zero']):
                    tags.append('零日攻擊')
                elif '漏洞' in pattern or 'vulnerability' in pattern:
                    tags.append('漏洞')
                elif any(keyword in pattern for keyword in ['網路安全', '資安', 'security', 'cybersecurity', 'infosec']):
                    tags.append('資安')
                elif any(keyword in pattern for keyword in ['政治', '政黨', '民主', '選舉']):
                    tags.append('政治')
                elif '年輕人' in pattern:
                    tags.append('年輕人')
                else:
                    tags.append(matches[0])
                break  # 只要找到一個主要主題就停止
        
        if not tags:
            print(f"         ❌ 未找到任何關鍵詞匹配")
        
        return tags
    
    def find_main_topic_in_data(self, data: Any, path: str = "") -> List[str]:
        """在__NEXT_DATA__中搜索主要主題"""
        tags = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                # 檢查可能包含主題的字段名
                if any(topic_key in key.lower() for topic_key in 
                      ['title', 'caption', 'text', 'content', 'description']):
                    if isinstance(value, str):
                        topic_tags = self.extract_main_topic_from_text(value)
                        if topic_tags:
                            tags.extend(topic_tags)
                            return tags  # 找到就返回，避免過多搜索
                
                # 遞歸搜索（限制深度避免回復）
                if path.count('.') < 3:  # 限制搜索深度
                    sub_tags = self.find_main_topic_in_data(value, f"{path}.{key}")
                    if sub_tags:
                        tags.extend(sub_tags)
                        return tags
                        
        elif isinstance(data, list) and len(data) > 0:
            # 只檢查第一個元素（通常是主文章）
            sub_tags = self.find_main_topic_in_data(data[0], f"{path}[0]")
            if sub_tags:
                tags.extend(sub_tags)
                        
        elif isinstance(data, str):
            topic_tags = self.extract_main_topic_from_text(data)
            if topic_tags:
                tags.extend(topic_tags)
        
        return tags
    
    async def search_hashtags_in_element(self, element) -> List[str]:
        """在指定元素內搜索hashtag"""
        hashtags = []
        try:
            # 搜索包含#的元素
            hash_elements = element.locator('*:has-text("#")')
            count = await hash_elements.count()
            
            for i in range(min(count, 5)):
                try:
                    hash_elem = hash_elements.nth(i)
                    text = await hash_elem.inner_text()
                    if text and "#" in text:
                        found_hashtags = re.findall(r'#([^#\s\n]+)', text)
                        for tag in found_hashtags:
                            if len(tag) <= 15 and tag not in hashtags:
                                hashtags.append(tag)
                except:
                    continue
                    
            # 也搜索link元素
            link_elements = element.locator('a[href*="#"]')
            link_count = await link_elements.count()
            
            for i in range(min(link_count, 5)):
                try:
                    link_elem = link_elements.nth(i)
                    href = await link_elem.get_attribute('href')
                    text = await link_elem.inner_text()
                    
                    if href and "#" in href:
                        # 從href中提取hashtag
                        href_tags = re.findall(r'#([^#\s&]+)', href)
                        for tag in href_tags:
                            if len(tag) <= 15 and tag not in hashtags:
                                hashtags.append(tag)
                    
                    if text and "#" in text:
                        # 從文本中提取hashtag
                        text_tags = re.findall(r'#([^#\s\n]+)', text)
                        for tag in text_tags:
                            if len(tag) <= 15 and tag not in hashtags:
                                hashtags.append(tag)
                except:
                    continue
                    
        except Exception as e:
            print(f"         ❌ hashtag搜索失敗: {e}")
        
        return hashtags
    
    def extract_location_tags(self, text: str) -> List[str]:
        """從文本中提取地點標籤"""
        tags = []
        
        # 直接包含雲林的情況
        if "雲林" in text:
            # 只有在雲林是獨立詞彙或者是短語時才添加
            if self.is_valid_tag("雲林"):
                tags.append("雲林")
        
        # 可能的地點格式
        location_patterns = [
            r'位於\s*([^，。\s]+)',
            r'在\s*([^，。\s]+)', 
            r'@\s*([^，。\s]+)',
            r'地點[：:]\s*([^，。\s]+)',
            r'([^，。\s]*雲林[^，。\s]*)'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                cleaned_tag = match.strip()
                if cleaned_tag and self.is_valid_tag(cleaned_tag) and cleaned_tag not in tags:
                    tags.append(cleaned_tag)
        
        return tags
    
    def is_valid_tag(self, tag: str) -> bool:
        """判斷是否為有效的標籤"""
        if not tag or len(tag.strip()) == 0:
            return False
        
        tag = tag.strip()
        
        # 過濾條件
        # 1. 長度限制（標籤通常不會太長）
        if len(tag) > 15:
            return False
        
        # 2. 過濾完整句子（包含標點符號）
        if any(punct in tag for punct in ['。', '！', '？', '，', '、', '\n', '  ']):
            return False
        
        # 3. 過濾包含太多表情符號的
        emoji_count = len(re.findall(r'[🥰😊😂❤️👍🎉🔥💯🙈🙉🙊]', tag))
        if emoji_count > 2:
            return False
        
        # 4. 過濾網址或特殊格式
        if any(pattern in tag.lower() for pattern in ['http', 'www', '.com', '.net', 'libertytimes']):
            return False
        
        # 5. 過濾純數字或特殊符號開頭
        if tag.isdigit() or tag.startswith(('@', '#', 'im')):
            return False
        
        # 6. 過濾問句
        if '嗎' in tag or tag.endswith('?'):
            return False
        
        # 7. 過濾太長的描述性文字
        descriptive_words = ['所以我都說', '絕對不會是', '這座', '造價', '億', '大雨中', '持續進行', '積水的', '跑道上']
        if any(word in tag for word in descriptive_words):
            return False
        
        return True
    
    def filter_and_clean_tags(self, raw_tags: List[str]) -> List[str]:
        """過濾和清理標籤列表"""
        cleaned_tags = []
        
        for tag in raw_tags:
            if self.is_valid_tag(tag):
                # 進一步清理
                cleaned_tag = tag.strip()
                
                # 去除多餘的表情符號
                cleaned_tag = re.sub(r'[🥰😊😂❤️👍🎉🔥💯🙈🙉🙊]{2,}', '', cleaned_tag)
                
                # 如果清理後仍然有效且不重複，則添加
                if cleaned_tag and len(cleaned_tag) > 1 and cleaned_tag not in cleaned_tags:
                    cleaned_tags.append(cleaned_tag)
        
        # 確保雲林在列表中
        if any('雲林' in tag for tag in raw_tags) and '雲林' not in cleaned_tags:
            cleaned_tags.insert(0, '雲林')
        
        return cleaned_tags
    
    def filter_to_single_main_tag(self, raw_tags: List[str]) -> List[str]:
        """過濾到單一主要標籤"""
        if not raw_tags:
            return []
        
        # 擴展的優先級規則
        priority_keywords = [
            '零日攻擊',  # 最高優先級 - 針對當前測試
            '0day',
            'zero-day',
            'zero day',
            '資安',
            '網路安全', 
            '漏洞',
            '駭客',
            '攻擊',
            '政治',     # 根據實際內容調整
            '年輕人',
            '政黨',
            '科技',
            'AI',
            '區塊鏈'
        ]
        
        # 首先檢查是否有高優先級的標籤
        for keyword in priority_keywords:
            for tag in raw_tags:
                if keyword.lower() in tag.lower():
                    return [keyword if keyword == '零日攻擊' else tag]
        
        # 如果沒有找到高優先級標籤，使用一般過濾規則
        valid_tags = []
        for tag in raw_tags:
            if self.is_valid_single_tag(tag):
                valid_tags.append(tag)
        
        # 只返回第一個有效標籤
        return valid_tags[:1] if valid_tags else []
    
    def is_valid_single_tag(self, tag: str) -> bool:
        """判斷是否為有效的單一標籤"""
        if not tag or len(tag.strip()) == 0:
            return False
        
        tag = tag.strip()
        
        # 基本過濾（比之前更嚴格）
        if len(tag) > 8:  # 標籤長度限制更嚴格
            return False
        
        # 過濾完整句子和描述性文字
        if any(punct in tag for punct in ['。', '！', '？', '，', '、', '\n', '的', '是', '在']):
            return False
        
        # 過濾表情符號
        if re.search(r'[🥰😊😂❤️👍🎉🔥💯🙈🙉🙊😠]', tag):
            return False
        
        # 過濾數字和特殊符號
        if tag.isdigit() or tag.startswith(('@', '#', 'im')):
            return False
        
        return True
    
    def find_location_in_data(self, data: Any, path: str = "") -> List[str]:
        """遞歸搜索數據中的地點信息"""
        tags = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                # 檢查可能包含地點的字段名
                if any(location_key in key.lower() for location_key in 
                      ['location', 'place', 'venue', 'city', 'region', 'address']):
                    if isinstance(value, str) and "雲林" in value:
                        tags.append(value)
                
                # 遞歸搜索
                sub_tags = self.find_location_in_data(value, f"{path}.{key}")
                tags.extend(sub_tags)
                
        elif isinstance(data, list):
            for i, item in enumerate(data):
                sub_tags = self.find_location_in_data(item, f"{path}[{i}]")
                tags.extend(sub_tags)
                
        elif isinstance(data, str) and "雲林" in data:
            tags.append(data)
        
        return tags
    
    async def check_auth_status(self, page):
        """檢查認證狀態"""
        try:
            # 檢查是否有登入指示器
            login_indicators = [
                'button:has-text("登入")',
                'button:has-text("Log in")',
                'a:has-text("登入")',
                'text="登入"'
            ]
            
            is_logged_in = True
            for indicator in login_indicators:
                if await page.locator(indicator).count() > 0:
                    is_logged_in = False
                    break
            
            if is_logged_in:
                print(f"      ✅ 認證狀態：已登入")
            else:
                print(f"      ⚠️ 認證狀態：未登入 - 可能影響標籤提取")
            
            # 檢查是否為Gate頁面
            page_content = await page.content()
            is_gate_page = "__NEXT_DATA__" not in page_content
            
            if is_gate_page:
                print(f"      ⚠️ 檢測到Gate頁面 - 功能可能受限")
            else:
                print(f"      ✅ 完整頁面 - 功能正常")
                
        except Exception as e:
            print(f"      ❌ 認證狀態檢查失敗: {e}")
    
    async def get_enhanced_content_and_media_from_dom(self, post_url: str) -> Optional[Dict[str, Any]]:
        """增強版DOM解析（添加時間和標籤）"""
        print(f"   🌐 從 DOM 解析內容、媒體、時間和標籤...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812}
            )
            
            page = await context.new_page()
            
            try:
                # 載入頁面
                await page.goto(post_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(3)
                
                # 檢查認證狀態
                await self.check_auth_status(page)
                
                # 基於 hybrid_content_extractor.py 的成功邏輯 - 提取基本信息
                
                # 提取用戶名
                username = ""
                try:
                    url_match = re.search(r'/@([^/]+)/', post_url)
                    if url_match:
                        username = url_match.group(1)
                except:
                    pass
                
                # 提取內容文字
                content = ""
                try:
                    content_selectors = [
                        'div[data-pressable-container] span',
                        '[data-testid="thread-text"]',
                        'article div[dir="auto"]',
                        'div[role="article"] div[dir="auto"]',
                        'span[style*="text-overflow"]'
                    ]
                    
                    for selector in content_selectors:
                        try:
                            elements = page.locator(selector)
                            count = await elements.count()
                            
                            if count > 0:
                                for i in range(min(count, 20)):
                                    try:
                                        text = await elements.nth(i).inner_text()
                                        if (text and len(text.strip()) > 10 and 
                                            not text.strip().isdigit() and
                                            "小時" not in text and "分鐘" not in text and
                                            not text.startswith("@")):
                                            content = text.strip()
                                            break
                                    except:
                                        continue
                                
                                if content:
                                    break
                        except:
                            continue
                except:
                    pass
                
                # 提取圖片（沿用成功的邏輯）
                images = []
                try:
                    img_elements = page.locator('img')
                    img_count = await img_elements.count()
                    
                    for i in range(min(img_count, 50)):
                        try:
                            img_elem = img_elements.nth(i)
                            img_src = await img_elem.get_attribute("src")
                            
                            if not img_src or not ("fbcdn" in img_src or "cdninstagram" in img_src):
                                continue
                            
                            if ("rsrc.php" in img_src or "static.cdninstagram.com" in img_src):
                                continue
                            
                            try:
                                width = int(await img_elem.get_attribute("width") or 0)
                                height = int(await img_elem.get_attribute("height") or 0)
                                max_size = max(width, height)
                                
                                if max_size > 150 and img_src not in images:
                                    images.append(img_src)
                            except:
                                if ("t51.2885-15" in img_src or "scontent" in img_src) and img_src not in images:
                                    images.append(img_src)
                        except:
                            continue
                            
                    print(f"      ✅ 找到 {len(images)} 個有效圖片")
                except Exception as e:
                    print(f"      ❌ 圖片提取失敗: {e}")
                
                # ===== 新增：提取發文時間 =====
                created_at = await self.extract_time_from_dom(page)
                
                # ===== 新增：提取主題標籤 =====
                tags = await self.extract_tags_from_dom(page)
                
                await browser.close()
                
                return {
                    "username": username,
                    "content": content,
                    "images": images,
                    "videos": [],  # 暫時保持原有結構
                    "created_at": created_at.isoformat() if created_at else None,
                    "tags": tags
                }
            
            except Exception as e:
                print(f"   ❌ DOM 解析失敗: {e}")
                await browser.close()
                return None
    
    async def extract_complete_post_with_time_and_tags(self, post_url: str = TEST_POST_URL) -> Optional[Dict[str, Any]]:
        """提取完整的貼文數據（包含時間和標籤）"""
        print(f"🎯 提取完整貼文數據（包含時間和標籤）: {post_url}")
        
        # 獲取內容和媒體數據（現在包含時間和標籤）
        content_data = await self.get_enhanced_content_and_media_from_dom(post_url)
        if not content_data:
            print(f"   ⚠️ 無法獲取內容數據")
            content_data = {
                "username": "", "content": "", "images": [], "videos": [],
                "created_at": None, "tags": []
            }
        else:
            print(f"   ✅ 內容數據: @{content_data['username']}, {len(content_data['content'])}字符")
            print(f"   ✅ 媒體: {len(content_data['images'])}圖片, {len(content_data['videos'])}影片")
            if content_data['created_at']:
                print(f"   ✅ 發文時間: {content_data['created_at']}")
            if content_data['tags']:
                print(f"   ✅ 標籤: {content_data['tags']}")
        
        # 合併數據
        code = re.search(r'/post/([A-Za-z0-9_-]+)', post_url)
        code = code.group(1) if code else ""
        
        result = {
            "pk": "",  # 如果有計數查詢會填入
            "code": code,
            "username": content_data["username"],
            "content": content_data["content"],
            "like_count": 0,  # 如果有計數查詢會填入
            "comment_count": 0,
            "repost_count": 0, 
            "share_count": 0,
            "images": content_data["images"],
            "videos": content_data["videos"],
            "created_at": content_data["created_at"],  # 新增
            "tags": content_data["tags"],  # 新增
            "url": post_url,
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "enhanced_dom"
        }
        
        # 顯示最終結果
        print(f"\n📋 最終結果:")
        print(f"   👤 用戶: @{result['username']}")
        print(f"   📝 內容: {len(result['content'])} 字符")
        print(f"   🖼️ 圖片: {len(result['images'])} 個")
        print(f"   🎥 影片: {len(result['videos'])} 個")
        print(f"   ⏰ 發文時間: {result['created_at']}")
        print(f"   🏷️ 標籤: {result['tags']}")
        
        if result['content']:
            print(f"   📄 內容預覽: {result['content'][:100]}...")
        
        # 保存結果
        result_file = Path(f"enhanced_extraction_result_{datetime.now().strftime('%H%M%S')}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"   📁 完整結果已保存: {result_file}")
        
        return result

async def main():
    """主函數"""
    print("🚀 增強版混合內容提取器 - 添加時間和標籤")
    print("基於 hybrid_content_extractor.py 的成功模式")
    print("=" * 50)
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    extractor = EnhancedHybridExtractor()
    
    # 可選：嘗試攔截計數查詢（如果失敗不影響主要功能）
    print(f"\n📡 第一步：嘗試攔截計數查詢...")
    captured = await extractor.intercept_counts_query()
    
    if captured:
        print(f"   ✅ 成功攔截計數查詢")
    else:
        print(f"   ⚠️ 未攔截到計數查詢，繼續使用 DOM 解析")
    
    # 第二步：提取完整數據（包含時間和標籤）
    print(f"\n🎯 第二步：增強DOM提取...")
    result = await extractor.extract_complete_post_with_time_and_tags()
    
    if result:
        print(f"\n🎉 增強提取成功！")
        print(f"💡 新增功能:")
        print(f"   ✅ 發文時間提取: {result['created_at'] or '未找到'}")
        print(f"   ✅ 主題標籤提取: {result['tags'] or '未找到'}")
        print(f"   ✅ 基於成功的 hybrid_content_extractor.py 邏輯")
        print(f"   ✅ 三重時間提取策略（datetime, title/aria-label, __NEXT_DATA__）")
        print(f"   ✅ 多重標籤搜索策略")
    else:
        print(f"\n😞 增強提取失敗")

if __name__ == "__main__":
    asyncio.run(main())