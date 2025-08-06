"""
智能滑動策略模組
將 realtime_crawler 的智能機制移植給 playwright_crawler_component_v2.py 使用
"""

import asyncio
import random
from typing import Dict, List, Optional

class SmartScrollingStrategy:
    """智能滾動策略類"""
    
    def __init__(self):
        self.scroll_rounds = 0
        self.max_scroll_rounds = 80
        self.no_new_content_rounds = 0
        self.max_no_new_rounds = 15
        self.consecutive_existing_rounds = 0
        self.max_consecutive_existing = 15
        
    async def smart_scroll_and_collect(
        self, 
        page, 
        target_username: str, 
        max_posts: int, 
        existing_post_ids: set = None,
        is_incremental: bool = True
    ) -> List[str]:
        """
        智能滑動並收集URLs
        採用 realtime_crawler 的策略
        """
        urls = []
        existing_post_ids = existing_post_ids or set()
        
        print("🔄 開始智能滾動收集URLs...")
        print(f"📋 模式: {'增量收集' if is_incremental else '全量收集'}")
        
        while len(urls) < max_posts and self.scroll_rounds < self.max_scroll_rounds:
            # 提取當前頁面的URLs
            current_urls = await self._extract_current_urls(page, target_username)
            
            before_count = len(urls)
            new_urls_this_round = 0
            found_existing_this_round = False
            
            # 處理新發現的URLs
            for url in current_urls:
                if len(urls) >= max_posts:
                    break
                    
                post_id = url.split('/')[-1] if url else None
                
                # 跳過已收集的URL
                if url in urls:
                    continue
                    
                # 增量模式：檢查是否已存在於資料庫
                if is_incremental and post_id in existing_post_ids:
                    print(f"   🔍 [{len(urls)+1}] 發現已爬取貼文: {post_id} - 跳過 (增量模式)")
                    found_existing_this_round = True
                    continue
                
                urls.append(url)
                new_urls_this_round += 1
                
                status_icon = "🆕" if is_incremental else "📍"
                print(f"   {status_icon} [{len(urls)}] 發現: {post_id}")
            
            # 增量模式：智能停止條件
            if is_incremental and found_existing_this_round:
                self.consecutive_existing_rounds += 1
                if len(urls) >= max_posts:
                    print(f"   ✅ 增量檢測: 已收集足夠新貼文 ({len(urls)} 個)")
                    break
                elif self.consecutive_existing_rounds >= self.max_consecutive_existing:
                    print(f"   ⏹️ 增量檢測: 連續 {self.consecutive_existing_rounds} 輪發現已存在貼文，停止收集")
                    print(f"   📊 最終收集: {len(urls)} 個新貼文 (目標: {max_posts})")
                    break
                else:
                    print(f"   🔍 增量檢測: 發現已存在貼文但數量不足 ({len(urls)}/{max_posts})，繼續滾動... (連續發現: {self.consecutive_existing_rounds}/{self.max_consecutive_existing})")
            else:
                self.consecutive_existing_rounds = 0
            
            # 檢查是否有新內容
            new_urls_found = len(urls) - before_count
            
            if new_urls_found == 0:
                self.no_new_content_rounds += 1
                print(f"   ⏳ 第{self.scroll_rounds+1}輪未發現新URL ({self.no_new_content_rounds}/{self.max_no_new_rounds})")
                
                if self.no_new_content_rounds >= self.max_no_new_rounds:
                    # 執行最後嘗試
                    final_new_count = await self._final_attempt_scroll(page, target_username, urls, max_posts, existing_post_ids, is_incremental)
                    if final_new_count == 0:
                        print("   ✅ 確認已到達頁面底部")
                        break
                    else:
                        print(f"   🎯 最後嘗試發現{final_new_count}個新URL，繼續...")
                        self.no_new_content_rounds = 0
                else:
                    # 遞增等待時間
                    await self._progressive_wait()
            else:
                self.no_new_content_rounds = 0
                print(f"   ✅ 第{self.scroll_rounds+1}輪發現{new_urls_found}個新URL")
            
            if len(urls) >= max_posts:
                print(f"   🎯 已達到目標數量 {max_posts}")
                break
            
            # 執行智能滾動
            await self._execute_smart_scroll(page)
            
            # 統一的載入檢測
            await self._wait_for_loading(page)
            
            self.scroll_rounds += 1
            
            # 每5輪顯示進度
            if self.scroll_rounds % 5 == 0:
                print(f"   📊 滾動進度: 第{self.scroll_rounds}輪，已收集{len(urls)}個URL")
        
        if self.scroll_rounds >= self.max_scroll_rounds:
            print(f"   ⚠️ 達到最大滾動輪次 ({self.max_scroll_rounds})，停止滾動")
        
        print(f"✅ URL收集完成：{len(urls)} 個URL，滾動 {self.scroll_rounds} 輪")
        return urls[:max_posts]
    
    async def _extract_current_urls(self, page, target_username: str) -> List[str]:
        """提取當前頁面的URLs"""
        current_urls = await page.evaluate(f"""
            () => {{
                const targetUsername = '{target_username}';
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
        return current_urls
    
    async def _execute_smart_scroll(self, page):
        """執行智能滾動策略"""
        if self.scroll_rounds % 6 == 5:  # 每6輪進行一次激進滾動
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
            
        elif self.scroll_rounds % 3 == 2:  # 每3輪進行一次中度滾動
            print("   🔄 執行中度滾動...")
            # 分段滾動，更像人類行為
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(2.8)
            
        else:
            # 正常滾動，加入隨機性和人性化
            scroll_distance = 900 + (self.scroll_rounds % 3) * 100  # 900-1100px隨機
            await page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            
            # 短暫暫停（模擬用戶閱讀）
            await asyncio.sleep(1.8 + (self.scroll_rounds % 2) * 0.4)  # 1.8-2.2秒隨機
    
    async def _wait_for_loading(self, page):
        """等待載入完成"""
        has_loading = await page.evaluate("""
            () => {
                const indicators = document.querySelectorAll(
                    '[role="progressbar"], .loading, [aria-label*="loading"], [aria-label*="Loading"]'
                );
                return indicators.length > 0;
            }
        """)
        
        if has_loading:
            print("   ⏳ 檢測到載入指示器，額外等待...")
            # 隨機等待2-3.5秒
            loading_wait = random.uniform(2.0, 3.5)
            await asyncio.sleep(loading_wait)
    
    async def _progressive_wait(self):
        """遞增等待時間"""
        base_wait = min(1.2 + (self.no_new_content_rounds - 1) * 0.3, 3.5)  # 1.2s -> 3.5s
        random_factor = random.uniform(0.8, 1.2)  # ±20%隨機變化
        progressive_wait = base_wait * random_factor
        print(f"   ⏲️ 遞增等待 {progressive_wait:.1f}s...")
        await asyncio.sleep(progressive_wait)
    
    async def _final_attempt_scroll(self, page, target_username: str, urls: List[str], max_posts: int, existing_post_ids: set, is_incremental: bool) -> int:
        """最後嘗試：多重激進滾動激發載入"""
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
        
        # 再次檢查新URLs
        final_urls = await self._extract_current_urls(page, target_username)
        
        final_new_count = 0
        for url in final_urls:
            post_id = url.split('/')[-1] if url else None
            
            if url not in urls and len(urls) < max_posts:
                # 增量模式檢查
                if is_incremental and post_id in existing_post_ids:
                    continue
                    
                urls.append(url)
                final_new_count += 1
                print(f"   📍 [{len(urls)}] 最後發現: {post_id}")
        
        return final_new_count
