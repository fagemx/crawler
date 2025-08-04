#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URL收集器
處理Playwright滾動和URL收集
"""

import asyncio
import json
import random
from typing import List, Set
from pathlib import Path
from playwright.async_api import async_playwright

from ..utils.helpers import safe_print

class UrlCollector:
    """URL收集器"""
    
    def __init__(self, target_username: str, max_posts: int, auth_file_path: Path):
        self.target_username = target_username
        self.max_posts = max_posts
        self.auth_file_path = auth_file_path
    
    async def collect_urls(self, existing_post_ids: Set[str] = None, incremental: bool = False) -> List[str]:
        """收集URLs"""
        existing_post_ids = existing_post_ids or set()
        
        # 檢查認證檔案
        if not self.auth_file_path.exists():
            raise FileNotFoundError(f"找不到認證檔案 '{self.auth_file_path}'")
        
        # 讀取認證內容
        with open(self.auth_file_path, "r", encoding="utf-8") as f:
            auth_content = json.load(f)
        
        safe_print(f"🔧 開始直接Playwright滾動收集URLs @{self.target_username}")
        safe_print(f"🎯 目標數量: {self.max_posts} 個URLs")
        safe_print(f"📋 模式: {'增量收集' if incremental else '全量收集'}")
        
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
                
                safe_print("🔄 開始智能滾動收集URLs...")
                
                # 滾動收集邏輯
                urls = await self._scroll_and_collect(page, existing_post_ids, incremental)
                
                await browser.close()
                
                safe_print(f"✅ URL收集完成，共收集到 {len(urls)} 個URL")
                return urls[:self.max_posts]  # 確保不超過目標數量
                
            except Exception as e:
                safe_print(f"❌ Playwright URL收集錯誤: {e}")
                if 'browser' in locals():
                    await browser.close()
                return []
    
    async def _scroll_and_collect(self, page, existing_post_ids: Set[str], incremental: bool) -> List[str]:
        """執行滾動和收集邏輯"""
        urls = []
        
        # 增強的滾動收集邏輯
        scroll_rounds = 0
        max_scroll_rounds = 80  # 大幅增加最大滾動次數
        no_new_content_rounds = 0  # 連續無新內容的輪次
        max_no_new_rounds = 15  # 增加連續無新內容的最大容忍輪次（更多耐心）
        consecutive_existing_rounds = 0  # 增量模式：連續發現已存在貼文的輪次
        max_consecutive_existing = 15  # 增量模式：允許的最大連續已存在輪次（放寬限制）
        
        while len(urls) < self.max_posts and scroll_rounds < max_scroll_rounds:
            # 提取當前頁面的URLs（過濾無效URLs和非目標用戶）
            current_urls = await page.evaluate(f"""
                () => {{
                    const targetUsername = '{self.target_username}';
                    const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                    return [...new Set(links.map(link => link.href)
                        .filter(url => url.includes('/post/'))
                        .filter(url => {{
                            // 檢查URL是否屬於目標用戶
                            const usernamePart = url.split('/@')[1];
                            if (!usernamePart) return false;
                            const extractedUsername = usernamePart.split('/')[0];
                            
                            const postId = url.split('/post/')[1];
                            // 過濾掉 media、無效ID等，並確保是目標用戶的貼文
                            return postId && 
                                   postId !== 'media' && 
                                   postId.length > 5 && 
                                   /^[A-Za-z0-9_-]+$/.test(postId) &&
                                   extractedUsername === targetUsername;
                        }}))];
                }}
            """)
            
            before_count = len(urls)
            
            # 去重並添加新URLs（支持增量檢測）
            new_urls_this_round = 0
            found_existing_this_round = False
            existing_skipped_this_round = 0
            
            for url in current_urls:
                post_id = url.split('/')[-1] if url else None
                
                # 跳過已收集的URL
                if url in urls:
                    continue
                    
                # 增量模式：檢查是否已存在於資料庫
                if incremental and post_id in existing_post_ids:
                    safe_print(f"   🔍 [{len(urls)+1}] 發現已爬取貼文: {post_id} - 跳過 (已在資料庫)")
                    found_existing_this_round = True
                    existing_skipped_this_round += 1
                    continue
                
                # 檢查是否已達到目標數量
                if len(urls) >= self.max_posts:
                    break
                    
                urls.append(url)
                new_urls_this_round += 1
                
                status_icon = "🆕" if incremental else "📍"
                safe_print(f"   {status_icon} [{len(urls)}] 發現: {post_id}")
            
            # 增量模式：智能停止條件
            if incremental:
                if found_existing_this_round:
                    consecutive_existing_rounds += 1
                    if len(urls) >= self.max_posts:
                        safe_print(f"   ✅ 增量檢測: 已收集足夠新貼文 ({len(urls)} 個)")
                        break
                    elif consecutive_existing_rounds >= max_consecutive_existing:
                        safe_print(f"   ⏹️ 增量檢測: 連續 {consecutive_existing_rounds} 輪發現已存在貼文，停止收集")
                        safe_print(f"   📊 最終收集: {len(urls)} 個新貼文 (目標: {self.max_posts})")
                        break
                    else:
                        safe_print(f"   🔍 增量檢測: 發現已存在貼文但數量不足 ({len(urls)}/{self.max_posts})，繼續滾動... (連續發現: {consecutive_existing_rounds}/{max_consecutive_existing})")
                else:
                    # 這輪沒有發現已存在貼文，重置計數器
                    consecutive_existing_rounds = 0
            
            # 檢查是否有新內容
            new_urls_found = len(urls) - before_count
            
            if new_urls_found == 0:
                no_new_content_rounds += 1
                safe_print(f"   ⏳ 第{scroll_rounds+1}輪未發現新URL ({no_new_content_rounds}/{max_no_new_rounds})")
                
                # 遞增等待時間（加入隨機性，限制最大3.5秒）
                base_wait = min(1.2 + (no_new_content_rounds - 1) * 0.3, 3.5)  # 1.2s -> 3.5s
                random_factor = random.uniform(0.8, 1.2)  # ±20%隨機變化
                progressive_wait = base_wait * random_factor
                safe_print(f"   ⏲️ 遞增等待 {progressive_wait:.1f}s...")
                await asyncio.sleep(progressive_wait)
                
                if no_new_content_rounds >= max_no_new_rounds:
                    safe_print(f"   🛑 連續{max_no_new_rounds}輪無新內容，可能已到達底部")
                    
                    # 最後嘗試
                    final_count = await self._final_attempt(page, urls)
                    if final_count == 0:
                        safe_print("   ✅ 確認已到達頁面底部")
                        break
                    else:
                        safe_print(f"   🎯 最後嘗試發現{final_count}個新URL，繼續...")
                        no_new_content_rounds = 0
            else:
                no_new_content_rounds = 0  # 重置計數器
                safe_print(f"   ✅ 第{scroll_rounds+1}輪發現{new_urls_found}個新URL")
            
            if len(urls) >= self.max_posts:
                safe_print(f"   🎯 已達到目標數量 {self.max_posts}")
                break
            
            # 執行滾動
            await self._perform_scroll(page, scroll_rounds)
            
            scroll_rounds += 1
            
            # 每5輪顯示進度
            if scroll_rounds % 5 == 0:
                safe_print(f"   📊 滾動進度: 第{scroll_rounds}輪，已收集{len(urls)}個URL")
        
        if scroll_rounds >= max_scroll_rounds:
            safe_print(f"   ⚠️ 達到最大滾動輪次 ({max_scroll_rounds})，停止滾動")
        
        return urls
    
    async def _final_attempt(self, page, urls: List[str]) -> int:
        """最後嘗試滾動激發新內容"""
        safe_print("   🚀 最後嘗試：多重激進滾動激發新內容...")
        
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
        
        safe_print("   ⏳ 等待所有內容載入完成...")
        await asyncio.sleep(3)
        
        # 再次檢查（過濾無效URLs）
        final_urls = await page.evaluate(f"""
            () => {{
                const targetUsername = '{self.target_username}';
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                return [...new Set(links.map(link => link.href)
                    .filter(url => url.includes('/post/'))
                    .filter(url => {{
                        const usernamePart = url.split('/@')[1];
                        if (!usernamePart) return false;
                        const extractedUsername = usernamePart.split('/')[0];
                        
                        const postId = url.split('/post/')[1];
                        // 過濾掉 media、無效ID等，並確保是目標用戶的貼文
                        return postId && 
                               postId !== 'media' && 
                               postId.length > 5 && 
                               /^[A-Za-z0-9_-]+$/.test(postId) &&
                               extractedUsername === targetUsername;
                    }}))];
            }}
        """)
        
        final_new_count = 0
        for url in final_urls:
            if url not in urls and len(urls) < self.max_posts:
                urls.append(url)
                final_new_count += 1
                safe_print(f"   📍 [{len(urls)}] 最後發現: {url.split('/')[-1]}")
        
        return final_new_count
    
    async def _perform_scroll(self, page, scroll_rounds: int):
        """執行滾動操作"""
        # 優化的人性化滾動策略
        if scroll_rounds % 6 == 5:  # 每6輪進行一次激進滾動（提高頻率）
            safe_print("   🚀 執行激進滾動激發載入...")
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
            safe_print("   🔄 執行中度滾動...")
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
            safe_print("   ⏳ 檢測到載入指示器，額外等待...")
            # 隨機等待2-3.5秒
            loading_wait = random.uniform(2.0, 3.5)
            await asyncio.sleep(loading_wait)