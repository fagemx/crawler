#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
實時爬蟲+提取器 - 智能滾動收集URLs並立即送Jina API提取
策略: 爬取一個URL → 立即送Jina API → 爬取下一個URL
因為滾動速度慢，自然避免API頻率限制
"""

import asyncio
import json
import requests
import time
import re
import random
import sys
from datetime import datetime
from typing import Dict, Optional, List, AsyncGenerator
import httpx
from pathlib import Path
from common.config import get_auth_file_path

def safe_print(msg, fallback_msg=None):
    """安全的打印函數，避免Unicode編碼錯誤"""
    try:
        print(msg)
    except UnicodeEncodeError:
        if fallback_msg:
            print(fallback_msg)
        else:
            # 移除所有非ASCII字符的安全版本
            ascii_msg = msg.encode('ascii', 'ignore').decode('ascii')
            print(ascii_msg if ascii_msg.strip() else "[編碼錯誤 - 訊息無法顯示]")

class RealtimeCrawlerExtractor:
    """
    實時爬蟲+提取器
    智能滾動收集URLs，收集到立即送Jina API提取
    """
    
    def __init__(self, target_username: str, max_posts: int = 20):
        self.target_username = target_username
        self.max_posts = max_posts
        
        # 爬蟲Agent設定
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.auth_file_path = get_auth_file_path(from_project_root=True)
        
        # Jina API設定
        self.official_reader_url = "https://r.jina.ai"
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        # 本地Reader配置
        self.local_reader_url = "http://localhost:8880"
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
        # NBSP字符和提取模式
        self.NBSP = "\u00A0"
        self.view_patterns = [
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
        
        # 結果統計
        self.results = []
        self.start_time = None
        self.api_success_count = 0
        self.api_failure_count = 0
        self.local_success_count = 0
        self.local_failure_count = 0
    
    def normalize_content(self, text: str) -> str:
        """內容標準化"""
        text = text.replace(self.NBSP, " ").replace("\u2002", " ").replace("\u2003", " ")
        text = text.replace("\u2009", " ").replace("\u200A", " ").replace("\u3000", " ").replace("\t", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text

    def extract_views_count(self, markdown_content: str, post_id: str = "") -> Optional[str]:
        """觀看數提取"""
        normalized_content = self.normalize_content(markdown_content)
        
        for pattern in self.view_patterns:
            match = pattern.search(normalized_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        
        for pattern in self.view_patterns:
            match = pattern.search(markdown_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        return None

    def validate_views_format(self, views: str) -> bool:
        """驗證觀看數格式"""
        if not views: return False
        pattern = re.compile(r'^\d+(?:\.\d+)?[KMB]?$', re.IGNORECASE)
        if not pattern.match(views): return False
        try:
            actual_number = self.convert_to_number(views)
            return 1 <= actual_number <= 100_000_000
        except: return False
    
    def convert_to_number(self, number_str: str) -> int:
        """K/M/B轉數字"""
        number_str = number_str.upper()
        if number_str.endswith('K'): return int(float(number_str[:-1]) * 1000)
        elif number_str.endswith('M'): return int(float(number_str[:-1]) * 1000000)
        elif number_str.endswith('B'): return int(float(number_str[:-1]) * 1000000000)
        else: return int(number_str)

    def extract_post_content(self, content: str) -> Optional[str]:
        """智能提取主貼文內容 - 區分主貼文和回覆"""
        lines = content.split('\n')
        
        # 策略1: 查找主貼文（第一個出現的實質內容）
        main_post_content = self._extract_main_post_from_structure(lines)
        if main_post_content:
            return main_post_content
        
        # 策略2: 回到原始方法作為備選
        return self._extract_content_fallback(lines)
    
    def _extract_main_post_from_structure(self, lines: List[str]) -> Optional[str]:
        """從結構化內容中提取主貼文"""
        # 查找模式：用戶名 → 時間 → 主貼文內容 → Translate → 數字（互動數據）
        main_content_candidates = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 跳過明顯的回覆標識
            if stripped.startswith('>>>') or stripped.startswith('回覆') or stripped.startswith('·Author'):
                continue
            
            # 尋找主貼文內容的模式
            if (stripped and 
                not stripped.startswith('[') and  # 跳過連結
                not stripped.startswith('![') and  # 跳過圖片
                not stripped.startswith('http') and  # 跳過URL
                not stripped.startswith('Log in') and  # 跳過登入提示
                not stripped.startswith('Thread') and  # 跳過Thread標題
                not stripped.startswith('gvmonthly') and  # 跳過用戶名
                not stripped.isdigit() and  # 跳過純數字
                not re.match(r'^\d+[dhm]$', stripped) and  # 跳過時間格式
                not stripped in ['Translate', 'views'] and  # 跳過特殊詞
                len(stripped) > 8):  # 內容要有一定長度
                
                # 檢查這是否可能是主貼文內容
                if self._is_likely_main_post_content(stripped, lines, i):
                    main_content_candidates.append(stripped)
        
        # 返回第一個合理的主貼文候選
        if main_content_candidates:
            return main_content_candidates[0]
        
        return None
    
    def _is_likely_main_post_content(self, content: str, lines: List[str], index: int) -> bool:
        """判斷內容是否可能是主貼文"""
        # 檢查後續是否有 "Translate" 標識（主貼文的典型結構）
        for j in range(index + 1, min(index + 3, len(lines))):
            if 'Translate' in lines[j]:
                return True
        
        # 檢查是否包含常見的主貼文特徵
        if (len(content) > 15 and  # 有一定長度
            not content.startswith('>>>') and  # 不是回覆
            not content.startswith('·') and  # 不是元數據
            '!' in content or '?' in content or '。' in content or '，' in content):  # 包含標點符號
            return True
        
        return False
    
    def _extract_content_fallback(self, lines: List[str]) -> Optional[str]:
        """備選內容提取方法"""
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        if content_start == -1:
            return None
        
        content_lines = []
        for i in range(content_start, min(content_start + 15, len(lines))):
            line = lines[i].strip()
            if (line and 
                not line.startswith('[![Image') and 
                not line.startswith('[Image') and
                not line.startswith('>>>')):  # 排除回覆
                content_lines.append(line)
                
                # 如果找到了合理的內容就停止
                if len(content_lines) >= 2 and len(line) > 10:
                    break
        
        return '\n'.join(content_lines) if content_lines else None

    def extract_engagement_numbers(self, markdown_content: str) -> List[str]:
        """提取所有統計數字序列（按讚、留言、轉發、分享）"""
        lines = markdown_content.split('\n')
        
        # 策略1: 查找貼文內容後的第一個圖片，然後提取後續數字
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到貼文圖片（通常在Translate之後）
            if stripped.startswith('![Image') and not 'profile picture' in stripped:
                numbers = []
                # 在這個圖片後查找連續的數字
                for j in range(i + 1, min(i + 20, len(lines))):
                    candidate = lines[j].strip()
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and not re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate) and candidate != "Pinned":
                        # 遇到非數字行（但跳過Pinned），停止收集
                        break
                
                # 如果找到了數字序列，返回
                if len(numbers) >= 3:
                    return numbers
        
        # 策略2: 如果策略1失敗，查找任何連續的數字序列
        all_numbers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^\d+(?:\.\d+)?[KMB]?$', stripped):
                # 檢查前後文，確保這是統計數字
                context_valid = False
                # 檢查前面10行是否有圖片或貼文內容
                for k in range(max(0, i-10), i):
                    if "![Image" in lines[k] or "Translate" in lines[k]:
                        context_valid = True
                        break
                
                if context_valid:
                    all_numbers.append(stripped)
        
        # 如果找到4個或更多數字，取前4個
        if len(all_numbers) >= 4:
            return all_numbers[:4]
        elif len(all_numbers) >= 3:
            return all_numbers[:3]
        
        return all_numbers

    def extract_likes_count(self, markdown_content: str) -> Optional[str]:
        """提取按讚數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 查找"Like"標籤後的數字（舊格式）
        for i, line in enumerate(lines):
            if line.strip() == "Like" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第一個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 1:
            return numbers[0]
        
        return None

    def extract_comments_count(self, markdown_content: str) -> Optional[str]:
        """提取留言數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Comment標籤
        for i, line in enumerate(lines):
            if line.strip() == "Comment" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第二個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 2:
            return numbers[1]
        
        return None

    def extract_reposts_count(self, markdown_content: str) -> Optional[str]:
        """提取轉發數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Repost標籤
        for i, line in enumerate(lines):
            if line.strip() == "Repost" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第三個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 3:
            return numbers[2]
        
        return None

    def extract_shares_count(self, markdown_content: str) -> Optional[str]:
        """提取分享數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Share標籤
        for i, line in enumerate(lines):
            if line.strip() == "Share" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第四個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 4:
            return numbers[3]
        
        return None

    def fetch_content_jina_api(self, url: str) -> tuple:
        """從Jina API獲取內容"""
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=60)
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def fetch_content_local(self, url: str, use_cache: bool = True, max_retries: int = 2) -> tuple:
        """使用本地Reader獲取內容 - 快速重試機制"""
        headers = self.local_headers.copy()
        if not use_cache: 
            headers['x-no-cache'] = 'true'
        
        for attempt in range(max_retries + 1):
            try:
                # 降低timeout，快速失敗
                timeout = 15 if attempt == 0 else 10  # 第一次15s，重試10s
                response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=timeout)
                if response.status_code == 200:
                    return True, response.text
                else:
                    if attempt < max_retries:
                        continue  # 重試
                    return False, f"HTTP {response.status_code}"
            except Exception as e:
                if attempt < max_retries:
                    # 短暫等待後重試
                    import time
                    time.sleep(0.5)
                    continue
                return False, f"最終失敗: {str(e)}"
        
        return False, "重試耗盡"
    
    def fetch_content_local_fast(self, url: str) -> tuple:
        """快速本地Reader - 專門為回退設計"""
        import concurrent.futures
        
        def try_single_request(instance_id):
            """嘗試單個Reader實例"""
            headers = self.local_headers.copy()
            headers['x-no-cache'] = 'true'  # 強制無快取
            try:
                # 超短timeout，快速失敗
                response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=8)
                return (True, response.text, instance_id) if response.status_code == 200 else (False, f"HTTP {response.status_code}", instance_id)
            except Exception as e:
                return (False, str(e), instance_id)
        
        # 平行嘗試多個實例（模擬負載均衡）
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # 提交2個平行請求（模擬重試）
            futures = [executor.submit(try_single_request, i) for i in range(2)]
            
            # 使用as_completed，誰先完成用誰
            for future in concurrent.futures.as_completed(futures, timeout=12):
                try:
                    success, content, instance_id = future.result()
                    if success:
                        # 取消其他正在執行的請求
                        for f in futures:
                            f.cancel()
                        return True, content
                except Exception:
                    continue
        
        return False, "所有平行請求失敗"
    
    def parse_post(self, url: str, content: str) -> Dict:
        """解析貼文 - 完整版本包含互動數據"""
        post_id = url.split('/')[-1] if '/' in url else url
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content(content)
        
        # 提取互動數據
        likes = self.extract_likes_count(content)
        comments = self.extract_comments_count(content)
        reposts = self.extract_reposts_count(content)
        shares = self.extract_shares_count(content)
        
        return {
            'post_id': post_id,
            'url': url,
            'views': views,
            'content': main_content,
            'likes': likes,
            'comments': comments,
            'reposts': reposts,
            'shares': shares,
            'source': 'jina_api',
            'has_views': views is not None,
            'has_content': main_content is not None,
            'has_likes': likes is not None,
            'has_comments': comments is not None,
            'has_reposts': reposts is not None,
            'has_shares': shares is not None,
            'content_length': len(content),
            'extracted_at': datetime.now().isoformat()
        }

    async def collect_urls_only(self) -> List[str]:
        """直接使用Playwright進行純URL收集，不經過Agent API"""
        from playwright.async_api import async_playwright
        
        # 檢查認證檔案
        if not self.auth_file_path.exists():
            raise FileNotFoundError(f"找不到認證檔案 '{self.auth_file_path}'")
        
        # 讀取認證內容
        with open(self.auth_file_path, "r", encoding="utf-8") as f:
            auth_content = json.load(f)
        
        print(f"🔧 開始直接Playwright滾動收集URLs @{self.target_username}")
        print(f"🎯 目標數量: {self.max_posts} 個URLs")
        print("📋 模式: 純URL收集，跳過所有詳細處理")
        
        urls = []
        
        async with async_playwright() as p:
            try:
                # 啟動瀏覽器
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                
                # 注入認證狀態
                await context.add_cookies(auth_content.get('cookies', []))
                local_storage = auth_content.get('localStorage', [])
                session_storage = auth_content.get('sessionStorage', [])
                
                # 創建頁面並前往目標
                page = await context.new_page()
                await page.goto(f"https://www.threads.com/@{self.target_username}")
                await asyncio.sleep(3)  # 等待頁面載入
                
                # 注入儲存狀態
                if local_storage:
                    for item in local_storage:
                        await page.evaluate(f"localStorage.setItem('{item['name']}', '{item['value']}')")
                if session_storage:
                    for item in session_storage:
                        await page.evaluate(f"sessionStorage.setItem('{item['name']}', '{item['value']}')")
                
                await page.reload()
                await asyncio.sleep(2)
                
                print("🔄 開始智能滾動收集URLs...")
                
                # 增強的滾動收集邏輯
                collected_count = 0
                scroll_rounds = 0
                max_scroll_rounds = 80  # 大幅增加最大滾動次數
                no_new_content_rounds = 0  # 連續無新內容的輪次
                max_no_new_rounds = 15  # 增加連續無新內容的最大容忍輪次（更多耐心）
                last_urls_count = 0
                
                while collected_count < self.max_posts and scroll_rounds < max_scroll_rounds:
                    # 提取當前頁面的URLs（過濾無效URLs）
                    current_urls = await page.evaluate("""
                        () => {
                            const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                            return [...new Set(links.map(link => link.href)
                                .filter(url => url.includes('/post/'))
                                .filter(url => {
                                    const postId = url.split('/post/')[1];
                                    // 過濾掉 media、無效ID等
                                    return postId && 
                                           postId !== 'media' && 
                                           postId.length > 5 && 
                                           /^[A-Za-z0-9_-]+$/.test(postId);
                                }))];
                        }
                    """)
                    
                    before_count = len(urls)
                    
                    # 去重並添加新URLs
                    for url in current_urls:
                        if url not in urls and len(urls) < self.max_posts:
                            urls.append(url)
                            collected_count = len(urls)
                            print(f"   📍 [{collected_count}] 發現: {url.split('/')[-1]}")
                    
                    # 檢查是否有新內容
                    new_urls_found = len(urls) - before_count
                    
                    if new_urls_found == 0:
                        no_new_content_rounds += 1
                        print(f"   ⏳ 第{scroll_rounds+1}輪未發現新URL ({no_new_content_rounds}/{max_no_new_rounds})")
                        
                        # 遞增等待時間（加入隨機性，限制最大3.5秒）
                        base_wait = min(1.2 + (no_new_content_rounds - 1) * 0.3, 3.5)  # 1.2s -> 3.5s
                        random_factor = random.uniform(0.8, 1.2)  # ±20%隨機變化
                        progressive_wait = base_wait * random_factor
                        print(f"   ⏲️ 遞增等待 {progressive_wait:.1f}s...")
                        await asyncio.sleep(progressive_wait)
                        
                        if no_new_content_rounds >= max_no_new_rounds:
                            print(f"   🛑 連續{max_no_new_rounds}輪無新內容，可能已到達底部")
                            
                            # 最後嘗試：多重激進滾動激發載入
                            print("   🚀 最後嘗試：多重激進滾動激發新內容...")
                            
                            # 第一次：大幅向下
                            await page.evaluate("window.scrollBy(0, 2500)")
                            await asyncio.sleep(2)
                            
                            # 第二次：向上再向下（激發載入）
                            await page.evaluate("window.scrollBy(0, -500)")
                            await asyncio.sleep(1)
                            await page.evaluate("window.scrollBy(0, 3000)")
                            await asyncio.sleep(3)
                            
                            # 第三次：滾動到更底部
                            await page.evaluate("window.scrollBy(0, 2000)")
                            await asyncio.sleep(2)
                            
                            print("   ⏳ 等待所有內容載入完成...")
                            await asyncio.sleep(3)
                            
                            # 再次檢查（過濾無效URLs）
                            final_urls = await page.evaluate("""
                                () => {
                                    const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                                    return [...new Set(links.map(link => link.href)
                                        .filter(url => url.includes('/post/'))
                                        .filter(url => {
                                            const postId = url.split('/post/')[1];
                                            // 過濾掉 media、無效ID等
                                            return postId && 
                                                   postId !== 'media' && 
                                                   postId.length > 5 && 
                                                   /^[A-Za-z0-9_-]+$/.test(postId);
                                        }))];
                                }
                            """)
                            
                            final_new_count = 0
                            for url in final_urls:
                                if url not in urls and len(urls) < self.max_posts:
                                    urls.append(url)
                                    collected_count = len(urls)
                                    final_new_count += 1
                                    print(f"   📍 [{collected_count}] 最後發現: {url.split('/')[-1]}")
                            
                            if final_new_count == 0:
                                print("   ✅ 確認已到達頁面底部")
                                break
                            else:
                                print(f"   🎯 最後嘗試發現{final_new_count}個新URL，繼續...")
                                no_new_content_rounds = 0
                    else:
                        no_new_content_rounds = 0  # 重置計數器
                        print(f"   ✅ 第{scroll_rounds+1}輪發現{new_urls_found}個新URL")
                    
                    if collected_count >= self.max_posts:
                        print(f"   🎯 已達到目標數量 {self.max_posts}")
                        break
                    
                    # 優化的人性化滾動策略
                    if scroll_rounds % 6 == 5:  # 每6輪進行一次激進滾動（提高頻率）
                        print("   🚀 執行激進滾動激發載入...")
                        # 模擬用戶快速滾動行為
                        await page.evaluate("window.scrollBy(0, 1600)")
                        await asyncio.sleep(1.2)
                        # 稍微回滾（像用戶滾過頭了）
                        await page.evaluate("window.scrollBy(0, -250)")
                        await asyncio.sleep(0.8)
                        # 再繼續向下
                        await page.evaluate("window.scrollBy(0, 1400)")
                        await asyncio.sleep(3.5)
                        
                    elif scroll_rounds % 3 == 2:  # 每3輪進行一次中度滾動
                        print("   🔄 執行中度滾動...")
                        # 分段滾動，更像人類行為
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1)
                        await page.evaluate("window.scrollBy(0, 600)")
                        await asyncio.sleep(2.8)
                        
                    else:
                        # 正常滾動，加入隨機性和人性化
                        scroll_distance = 900 + (scroll_rounds % 3) * 100  # 900-1100px隨機
                        await page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                        
                        # 短暫暫停（模擬用戶閱讀）
                        await asyncio.sleep(1.8 + (scroll_rounds % 2) * 0.4)  # 1.8-2.2秒隨機
                    
                    # 統一的載入檢測（所有滾動後都檢查）
                    has_loading = await page.evaluate("""
                        () => {
                            const indicators = document.querySelectorAll('[role="progressbar"], .loading, [aria-label*="loading"], [aria-label*="Loading"]');
                            return indicators.length > 0;
                        }
                    """)
                    
                    if has_loading:
                        print("   ⏳ 檢測到載入指示器，額外等待...")
                        # 隨機等待2-3.5秒
                        loading_wait = random.uniform(2.0, 3.5)
                        await asyncio.sleep(loading_wait)
                    
                    scroll_rounds += 1
                    
                    # 每5輪顯示進度
                    if scroll_rounds % 5 == 0:
                        print(f"   📊 滾動進度: 第{scroll_rounds}輪，已收集{collected_count}個URL")
                
                if scroll_rounds >= max_scroll_rounds:
                    print(f"   ⚠️ 達到最大滾動輪次 ({max_scroll_rounds})，停止滾動")
                
                await browser.close()
                
                print(f"✅ URL收集完成，共收集到 {len(urls)} 個URL")
                return urls[:self.max_posts]  # 確保不超過目標數量
                
            except Exception as e:
                print(f"❌ Playwright URL收集錯誤: {e}")
                if 'browser' in locals():
                    await browser.close()
                return []

    async def process_url_realtime(self, url: str, index: int, total: int) -> Optional[Dict]:
        """實時處理單個URL"""
        post_id = url.split('/')[-1]
        
        print(f"🌐 [{index}/{total}] 送Jina API: {post_id}...", end=" ")
        
        # 送Jina API提取
        success, content = self.fetch_content_jina_api(url)
        
        if success:
            result = self.parse_post(url, content)
            if result['has_views']:
                self.api_success_count += 1
                print(f"✅ ({result['views']})")
                return result
            else:
                self.api_failure_count += 1
                print(f"❌ 無觀看數")
                return result
        else:
            # API失敗，快速回退到本地Reader
            print(f"❌ API失敗: {content}")
            print(f"   🔄 快速回退本地Reader: {post_id}...", end=" ")
            
            # 使用快速重試的本地Reader
            local_success, local_content = self.fetch_content_local_fast(url)
            
            if local_success:
                local_result = self.parse_post(url, local_content)
                local_result['source'] = 'local_reader_fallback'
                if local_result['has_views']:
                    self.local_success_count += 1
                    print(f"✅ 本地成功 ({local_result['views']})")
                    return local_result
                else:
                    self.local_failure_count += 1
                    print(f"❌ 本地無觀看數")
                    return local_result
            else:
                self.local_failure_count += 1
                print(f"❌ 本地也失敗: {local_content}")
                self.api_failure_count += 1  # 仍然計入API失敗
                return {
                    'post_id': post_id,
                    'url': url,
                    'api_error': content,
                    'local_error': local_content,
                    'source': 'both_failed',
                    'has_views': False,
                    'extracted_at': datetime.now().isoformat()
                }

    async def run_realtime_extraction(self):
        """執行實時爬取+提取"""
        self.start_time = time.time()
        self.url_collection_time = 0  # 初始化URL收集時間
        
        safe_print("🚀 實時爬蟲+提取器啟動", "[實時爬蟲+提取器啟動]")
        safe_print("策略: 智能滾動收集URLs → 按順序送Jina API", "策略: 智能滾動收集URLs -> 按順序送Jina API")
        print("=" * 80)
        
        # 第一階段：收集所有URLs（快速）
        url_collection_start = time.time()
        urls = await self.collect_urls_only()
        url_collection_time = time.time() - url_collection_start
        
        if not urls:
            safe_print("❌ 沒有收集到任何URL", "[X] 沒有收集到任何URL")
            return

        safe_print(f"✅ URL收集完成！收集到 {len(urls)} 個URL", f"[OK] URL收集完成！收集到 {len(urls)} 個URL")
        safe_print(f"⏱️ URL收集耗時: {url_collection_time:.1f}s", f"[時間] URL收集耗時: {url_collection_time:.1f}s")
        safe_print(f"🏎️ 收集速度: {len(urls)/url_collection_time:.2f} URL/s", f"[速度] 收集速度: {len(urls)/url_collection_time:.2f} URL/s")
        
        # 保存URL收集時間
        self.url_collection_time = url_collection_time
        
        safe_print(f"\n🔄 第二階段：使用輪迴策略快速提取 {len(urls)} 個URL...", f"\n[處理] 第二階段：使用輪迴策略快速提取 {len(urls)} 個URL...")
        print("策略: 10個API → 20個本地 → 輪迴，避免API阻擋")
        print("=" * 60)
        
        # 導入rotation策略
        try:
            from test_reader_rotation import RotationPipelineReader
            
            # 創建rotation實例
            rotation_reader = RotationPipelineReader()
            
            # 準備URLs（確保格式正確）
            formatted_urls = []
            for url in urls:
                if url.startswith('http'):
                    formatted_urls.append(url)
                else:
                    formatted_urls.append(f"https://www.threads.net/t/{url}")
            
            print(f"🔄 開始輪迴策略處理...")
            
            # 執行rotation策略
            rotation_results = rotation_reader.rotation_pipeline(formatted_urls)
            
            # rotation_results 是一個list，直接使用並修正格式
            if isinstance(rotation_results, list):
                # 修正結果格式，確保包含extracted_at和正確的source格式
                fixed_results = []
                for r in rotation_results:
                    fixed_result = r.copy()
                    
                    # 統一source格式
                    if 'API-批次' in r.get('source', ''):
                        fixed_result['source'] = 'jina_api'
                    elif '本地-批次' in r.get('source', ''):
                        fixed_result['source'] = 'local_reader'
                    elif 'API-回退' in r.get('source', ''):
                        fixed_result['source'] = 'local_reader_fallback'
                    
                    # 確保有extracted_at
                    if 'extracted_at' not in fixed_result:
                        fixed_result['extracted_at'] = datetime.now().isoformat()
                    
                    # 如果content為None但有content_length，嘗試重新提取（臨時方案）
                    if not fixed_result.get('content') and fixed_result.get('content_length', 0) > 0:
                        print(f"   ⚠️ {fixed_result['post_id']}: 文字內容遺失，標記為無內容")
                        fixed_result['has_content'] = False
                    
                    fixed_results.append(fixed_result)
                
                self.results = fixed_results
                
                # 統計rotation結果
                self.api_success_count = len([r for r in fixed_results if r.get('source') == 'jina_api' and r.get('has_views')])
                self.local_success_count = len([r for r in fixed_results if r.get('source') in ['local_reader', 'local_reader_fallback'] and r.get('has_views')])
                self.api_failure_count = len([r for r in fixed_results if r.get('source') == 'jina_api' and not r.get('has_views')])
                self.local_failure_count = len([r for r in fixed_results if r.get('source') in ['local_reader', 'local_reader_fallback'] and not r.get('has_views')])
            else:
                # 如果是dict格式（舊版本）
                self.results = rotation_results.get('results', [])
                summary = rotation_results.get('summary', {})
                self.api_success_count = summary.get('api_batch_success', 0)
                self.local_success_count = summary.get('local_batch_success', 0) + summary.get('api_fallback_success', 0)
                self.api_failure_count = summary.get('api_batch_failure', 0)
                self.local_failure_count = summary.get('local_batch_failure', 0)
            
            print("✅ 輪迴策略提取完成！")
            
        except ImportError as e:
            print(f"❌ 無法導入rotation策略: {e}")
            print("🔄 改用原始逐一處理方式...")
            
            # 回退到原始方式
            for i, url in enumerate(urls):
                result = await self.process_url_realtime(url, i+1, len(urls))
                if result:
                    self.results.append(result)
                
                elapsed = time.time() - self.start_time
                success_rate = self.api_success_count / (i+1) * 100
                
                print(f"   📊 進度: {i+1}/{len(urls)} | 成功率: {success_rate:.1f}% | 耗時: {elapsed:.1f}s")
                
                if i < len(urls) - 1:
                    sleep_time = random.choice([1.0, 1.5, 2.0])
                    print(f"   ⏸️ 等待 {sleep_time}s 後處理下一個...")
                    await asyncio.sleep(sleep_time)
        
        # 最終統計
        self.show_final_statistics()

    def show_final_statistics(self):
        """顯示最終統計"""
        total_time = time.time() - self.start_time
        total_processed = len(self.results)
        
        print("\n" + "=" * 80)
        print("🏁 實時爬取+提取完成")
        print("=" * 80)
        
        print(f"📊 處理統計:")
        print(f"   - 總處理數: {total_processed}")
        print(f"   - 🌐 API成功: {self.api_success_count} | API失敗: {self.api_failure_count}")
        print(f"   - ⚡ 本地成功: {self.local_success_count} | 本地失敗: {self.local_failure_count}")
        total_success = self.api_success_count + self.local_success_count
        print(f"   - 📈 整體成功率: {total_success/total_processed*100:.1f}%" if total_processed > 0 else "   - 整體成功率: N/A")
        
        print(f"⏱️ 時間統計:")
        extraction_time = total_time - getattr(self, 'url_collection_time', 0)
        print(f"   - 📡 URL收集: {getattr(self, 'url_collection_time', 0):.1f}s")
        print(f"   - 🔄 內容提取: {extraction_time:.1f}s") 
        print(f"   - 🏁 總耗時: {total_time:.1f}s")
        print(f"   - 📊 收集速度: {total_processed/getattr(self, 'url_collection_time', 1):.2f} URL/s (收集)")
        print(f"   - 🚀 提取速度: {total_processed/extraction_time:.2f} URL/s (提取)" if extraction_time > 0 else "   - 提取速度: N/A")
        print(f"   - 📈 整體速度: {total_processed/total_time:.2f} URL/s (總計)" if total_time > 0 else "   - 整體速度: N/A")
        
        # 顯示成功案例統計
        successful_views = [r for r in self.results if r.get('has_views')]
        successful_content = [r for r in self.results if r.get('has_content')]
        successful_likes = [r for r in self.results if r.get('has_likes')]
        successful_comments = [r for r in self.results if r.get('has_comments')]
        successful_reposts = [r for r in self.results if r.get('has_reposts')]
        successful_shares = [r for r in self.results if r.get('has_shares')]
        
        print(f"\n📈 提取統計:")
        print(f"   - 📊 觀看數成功: {len(successful_views)}/{total_processed} ({len(successful_views)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 觀看數成功: N/A")
        print(f"   - 📝 文字內容成功: {len(successful_content)}/{total_processed} ({len(successful_content)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 文字內容成功: N/A")
        print(f"   - 👍 按讚數成功: {len(successful_likes)}/{total_processed} ({len(successful_likes)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 按讚數成功: N/A")
        print(f"   - 💬 留言數成功: {len(successful_comments)}/{total_processed} ({len(successful_comments)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 留言數成功: N/A")
        print(f"   - 🔄 轉發數成功: {len(successful_reposts)}/{total_processed} ({len(successful_reposts)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 轉發數成功: N/A")
        print(f"   - 📤 分享數成功: {len(successful_shares)}/{total_processed} ({len(successful_shares)/total_processed*100:.1f}%)" if total_processed > 0 else "   - 分享數成功: N/A")
        
        if successful_views:
            print(f"\n🎯 成功提取的貼文 (前5筆詳細):")
            for i, r in enumerate(successful_views[:5]):
                content_preview = r.get('content', '')[:40] + "..." if r.get('content') and len(r.get('content', '')) > 40 else r.get('content', '無內容')
                print(f"   ✅ {r['post_id']}:")
                print(f"      📊 觀看: {r.get('views', 'N/A')} | 👍 讚: {r.get('likes', 'N/A')} | 💬 留言: {r.get('comments', 'N/A')} | 🔄 轉發: {r.get('reposts', 'N/A')} | 📤 分享: {r.get('shares', 'N/A')}")
                print(f"      📝 內容: {content_preview}")
        
        # 保存結果
        self.save_results()

    def save_results(self):
        """保存結果到JSON文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"realtime_extraction_results_{timestamp}.json"
        
        total_time = time.time() - self.start_time
        extraction_time = total_time - getattr(self, 'url_collection_time', 0)
        
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'target_username': self.target_username,
            'max_posts': self.max_posts,
            'total_processed': len(self.results),
            'api_success_count': self.api_success_count,
            'api_failure_count': self.api_failure_count,
            'local_success_count': self.local_success_count,
            'local_failure_count': self.local_failure_count,
            'overall_success_rate': (self.api_success_count + self.local_success_count) / len(self.results) * 100 if self.results else 0,
            'timing': {
                'url_collection_time': getattr(self, 'url_collection_time', 0),
                'content_extraction_time': extraction_time,
                'total_time': total_time,
                'url_collection_speed': len(self.results) / getattr(self, 'url_collection_time', 1) if getattr(self, 'url_collection_time', 0) > 0 else 0,
                'content_extraction_speed': len(self.results) / extraction_time if extraction_time > 0 else 0,
                'overall_speed': len(self.results) / total_time if total_time > 0 else 0
            },
            'views_extraction_count': len([r for r in self.results if r.get('has_views')]),
            'content_extraction_count': len([r for r in self.results if r.get('has_content')]),
            'likes_extraction_count': len([r for r in self.results if r.get('has_likes')]),
            'comments_extraction_count': len([r for r in self.results if r.get('has_comments')]),
            'reposts_extraction_count': len([r for r in self.results if r.get('has_reposts')]),
            'shares_extraction_count': len([r for r in self.results if r.get('has_shares')]),
            'views_extraction_rate': len([r for r in self.results if r.get('has_views')]) / len(self.results) * 100 if self.results else 0,
            'content_extraction_rate': len([r for r in self.results if r.get('has_content')]) / len(self.results) * 100 if self.results else 0,
            'likes_extraction_rate': len([r for r in self.results if r.get('has_likes')]) / len(self.results) * 100 if self.results else 0,
            'comments_extraction_rate': len([r for r in self.results if r.get('has_comments')]) / len(self.results) * 100 if self.results else 0,
            'reposts_extraction_rate': len([r for r in self.results if r.get('has_reposts')]) / len(self.results) * 100 if self.results else 0,
            'shares_extraction_rate': len([r for r in self.results if r.get('has_shares')]) / len(self.results) * 100 if self.results else 0,
            'results': self.results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        safe_print(f"💾 結果已保存到: {filename}", f"[保存] 結果已保存到: {filename}")

async def main():
    """主函數"""
    import argparse
    import sys
    import os
    
    # Windows編碼修正
    if sys.platform == 'win32':
        try:
            # 設置控制台編碼為UTF-8
            os.system('chcp 65001 >nul 2>&1')
            # 重新配置stdout編碼
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass
    
    # 設定命令行參數
    parser = argparse.ArgumentParser(description='實時爬蟲+提取器')
    parser.add_argument('--username', default='gvmonthly', help='目標帳號用戶名')
    parser.add_argument('--max_posts', type=int, default=100, help='要爬取的貼文數量')
    
    args = parser.parse_args()
    
    # 創建並執行實時提取器
    extractor = RealtimeCrawlerExtractor(args.username, args.max_posts)
    await extractor.run_realtime_extraction()

if __name__ == "__main__":
    asyncio.run(main())