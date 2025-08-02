"""
URL 提取器

負責從用戶頁面提取貼文 URLs，保持時間順序
"""

import asyncio
import logging
from typing import List
from playwright.async_api import Page


class URLExtractor:
    """
    從用戶頁面提取貼文 URLs
    """
    
    async def get_ordered_post_urls_from_page(self, page: Page, username: str, max_posts: int) -> List[str]:
        """
        從用戶頁面直接提取貼文 URLs，保持時間順序
        這是解決貼文順序混亂問題的關鍵方法
        """
        user_url = f"https://www.threads.com/@{username}"
        logging.info(f"🔍 正在從用戶頁面獲取有序的貼文 URLs: {user_url}")
        
        await page.goto(user_url, wait_until="networkidle")
        
        # 等待頁面載入
        await asyncio.sleep(3)
        
        # 滾動以載入更多貼文（但不要滾動太多次避免載入過舊的貼文）
        scroll_count = min(3, max(1, max_posts // 10))  # 根據需求動態調整滾動次數
        for i in range(scroll_count):
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(2)
        
        # 提取貼文 URLs，保持原始順序並標準化
        post_urls = await page.evaluate("""
            () => {
                // 標準化 URL 函數 - 移除 /media, /reply 等後綴
                function normalizePostUrl(url) {
                    const match = url.match(/https:\/\/www\.threads\.com\/@([^\/]+)\/post\/([^\/\?]+)/);
                    if (match) {
                        const username = match[1];
                        const postId = match[2];
                        return `https://www.threads.com/@${username}/post/${postId}`;
                    }
                    return url;
                }
                
                // 獲取所有貼文連結，保持DOM中的原始順序
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                const urls = [];
                const seen = new Set();
                
                // 遍歷時保持順序，標準化URL並去重
                for (const link of links) {
                    const originalUrl = link.href;
                    const normalizedUrl = normalizePostUrl(originalUrl);
                    
                    if (originalUrl.includes('/post/') && !seen.has(normalizedUrl)) {
                        seen.add(normalizedUrl);
                        urls.push(normalizedUrl);
                    }
                }
                
                return urls;
            }
        """)
        
        # 限制數量但保持順序
        post_urls = post_urls[:max_posts]
        logging.info(f"   ✅ 按時間順序找到 {len(post_urls)} 個貼文 URLs")
        
        return post_urls