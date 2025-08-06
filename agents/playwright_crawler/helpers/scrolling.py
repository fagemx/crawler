"""
滾動和貼文定位輔助函式

實現智能滾動邏輯，支持 NEW-POST 和 HIST-BACKFILL 兩種模式
"""

import asyncio
import logging
import random
from typing import List, Tuple, Set
from playwright.async_api import Page


async def extract_current_post_ids(page: Page) -> List[str]:
    """
    提取當前視窗內的貼文IDs，保持DOM順序
    
    Returns:
        按DOM出現順序的post_id列表 (不含username前綴)
    """
    try:
        post_ids = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                const ids = [];
                const seen = new Set();
                
                for (const link of links) {
                    const match = link.href.match(/\/post\/([^\/\?]+)/);
                    if (match && !seen.has(match[1])) {
                        seen.add(match[1]);
                        ids.push(match[1]);
                    }
                }
                
                return ids;
            }
        """)
        
        logging.debug(f"📋 提取到 {len(post_ids)} 個貼文ID")
        return post_ids
        
    except Exception as e:
        logging.warning(f"⚠️ 提取貼文ID失敗: {e}")
        return []


async def check_page_bottom(page: Page) -> bool:
    """
    檢查是否已滾動到頁面底部
    
    Returns:
        True 如果已到底部
    """
    try:
        is_bottom = await page.evaluate("""
            () => {
                const threshold = 100;  // 容忍100px誤差
                return (window.scrollY + window.innerHeight) >= (document.body.scrollHeight - threshold);
            }
        """)
        
        if is_bottom:
            logging.debug("📄 已到達頁面底部")
        
        return is_bottom
        
    except Exception as e:
        logging.warning(f"⚠️ 檢查頁面底部失敗: {e}")
        return False


async def scroll_once(page: Page, delta: int = 1000) -> None:
    """
    執行一次智能滾動
    
    Args:
        page: Playwright頁面對象
        delta: 滾動距離 (像素)
    """
    try:
        # 隨機化滾動距離 ±20%
        actual_delta = int(delta * random.uniform(0.8, 1.2))
        
        await page.mouse.wheel(0, actual_delta)
        
        # 隨機化等待時間
        sleep_time = random.uniform(0.6, 1.2)
        await asyncio.sleep(sleep_time)
        
        logging.debug(f"🔄 滾動 {actual_delta}px，等待 {sleep_time:.2f}s")
        
    except Exception as e:
        logging.warning(f"⚠️ 滾動失敗: {e}")


async def enhanced_scroll_with_strategy(page: Page, scroll_round: int) -> None:
    """
    增強的人性化滾動策略 - 採用Realtime Crawler優秀策略
    
    Args:
        page: Playwright頁面對象
        scroll_round: 當前滾動輪次
    """
    try:
        if scroll_round % 6 == 5:  # 每6輪進行一次激進滾動
            logging.debug("   🚀 執行激進滾動激發載入...")
            # 模擬用戶快速滾動行為
            await page.mouse.wheel(0, 1600)
            await asyncio.sleep(1.2)
            # 稍微回滾（像用戶滾過頭了）
            await page.mouse.wheel(0, -250)
            await asyncio.sleep(0.8)
            # 再繼續向下
            await page.mouse.wheel(0, 1400)
            await asyncio.sleep(3.5)
            
        elif scroll_round % 3 == 2:  # 每3輪進行一次中度滾動
            logging.debug("   🔄 執行中度滾動...")
            # 分段滾動，更像人類行為
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(1)
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(2.8)
            
        else:
            # 正常滾動，加入隨機性和人性化
            scroll_distance = 900 + (scroll_round % 3) * 100  # 900-1100px隨機
            await page.mouse.wheel(0, scroll_distance)
            
            # 短暫暫停（模擬用戶閱讀）
            await asyncio.sleep(1.8 + (scroll_round % 2) * 0.4)  # 1.8-2.2秒隨機
        
        # 統一的載入檢測（所有滾動後都檢查）
        await wait_for_content_loading(page)
        
    except Exception as e:
        logging.warning(f"⚠️ 增強滾動失敗: {e}")


async def wait_for_content_loading(page: Page) -> None:
    """
    等待內容載入完成 - 檢測載入指示器
    """
    try:
        has_loading = await page.evaluate("""
            () => {
                const indicators = document.querySelectorAll(
                    '[role="progressbar"], .loading, [aria-label*="loading"], [aria-label*="Loading"]'
                );
                return indicators.length > 0;
            }
        """)
        
        if has_loading:
            logging.debug("   ⏳ 檢測到載入指示器，額外等待...")
            # 隨機等待2-3.5秒
            loading_wait = random.uniform(2.0, 3.5)
            await asyncio.sleep(loading_wait)
            
    except Exception as e:
        logging.warning(f"⚠️ 載入檢測失敗: {e}")


def is_anchor_visible(post_ids: List[str], anchor: str) -> Tuple[bool, int]:
    """
    檢查錨點是否在當前貼文列表中
    
    Args:
        post_ids: 當前視窗的貼文ID列表
        anchor: 要查找的錨點貼文ID (不含username前綴)
        
    Returns:
        (是否找到, 在列表中的索引位置) 
        未找到時索引為-1
    """
    if not anchor:
        return False, -1
        
    # 移除可能的username前綴
    anchor_clean = anchor.split('_')[-1] if '_' in anchor else anchor
    
    for i, post_id in enumerate(post_ids):
        if post_id == anchor_clean:
            logging.debug(f"🎯 找到錨點 {anchor_clean} 在位置 {i}/{len(post_ids)}")
            return True, i
            
    return False, -1


async def collect_urls_from_dom(page: Page, existing_set: Set[str], target_username: str = None) -> List[str]:
    """
    從DOM收集新的貼文URLs，過濾已存在的
    
    Args:
        page: Playwright頁面對象
        existing_set: 已存在的貼文ID集合 (用於去重)
        
    Returns:
        新發現的貼文URLs列表
    """
    try:
        new_urls = await page.evaluate("""
            (existingIds, targetUsername) => {
                // 使用與原始url_extractor完全相同的邏輯
                function normalizePostUrl(url) {
                    const match = url.match(/https:\\/\\/www\\.threads\\.com\\/@([^\\/]+)\\/post\\/([^\\/\\?]+)/);
                    if (match) {
                        const username = match[1];
                        const postId = match[2];
                        return `https://www.threads.com/@${username}/post/${postId}`;
                    }
                    return url;
                }
                
                // 獲取所有貼文連結，保持DOM中的原始順序（與url_extractor相同）
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                const urls = [];
                const seen = new Set();
                
                // 遍歷時保持順序，標準化URL並去重（與url_extractor相同）
                for (const link of links) {
                    const originalUrl = link.href;
                    const normalizedUrl = normalizePostUrl(originalUrl);
                    
                    if (originalUrl.includes('/post/') && !seen.has(normalizedUrl)) {
                        // 提取URL中的實際用戶名
                        const match = normalizedUrl.match(/https:\/\/www\.threads\.com\/@([^\/]+)\/post\/([^\/\?]+)/);
                        if (match) {
                            const urlUsername = match[1];
                            const postId = match[2];
                            
                            // 只收集目標用戶的貼文（過濾轉貼）
                            if (!targetUsername || urlUsername === targetUsername) {
                                const fullId = `${urlUsername}_${postId}`;
                                
                                if (!existingIds.includes(fullId)) {
                                    seen.add(normalizedUrl);
                                    urls.push(normalizedUrl);
                                }
                            }
                        }
                    }
                }
                
                return urls;
            }
        """, list(existing_set), target_username)
        
        logging.debug(f"🔗 收集到 {len(new_urls)} 個新URLs (目標用戶: {target_username})")
        return new_urls
        
    except Exception as e:
        logging.warning(f"⚠️ 收集URLs失敗: {e}")
        return []


def should_stop_new_mode(found_anchor: bool, collected: List[str], target_count: int) -> bool:
    """
    判斷NEW模式是否應該停止滾動
    
    Args:
        found_anchor: 是否已找到錨點
        collected: 已收集的貼文列表
        target_count: 目標收集數量
        
    Returns:
        True 如果應該停止
    """
    # 條件1: 已達到目標數量
    if len(collected) >= target_count:
        logging.debug(f"✅ NEW模式達標: {len(collected)}/{target_count}")
        return True
        
    # 條件2: 找到錨點 (意味著不再有新貼文)
    if found_anchor:
        logging.debug(f"🎯 NEW模式遇到錨點，停止滾動: {len(collected)}/{target_count}")
        return True
        
    return False


def should_stop_hist_mode(
    found_anchor: bool, 
    passed_anchor: bool,
    collected: List[str], 
    target_count: int,
    scroll_round: int,
    max_scroll_rounds: int
) -> bool:
    """
    判斷HIST模式是否應該停止滾動
    
    Args:
        found_anchor: 是否已找到錨點
        passed_anchor: 是否已越過錨點
        collected: 已收集的貼文列表
        target_count: 目標收集數量  
        scroll_round: 當前滾動輪次
        max_scroll_rounds: 最大滾動輪次
        
    Returns:
        True 如果應該停止
    """
    # 條件1: 已達到目標數量
    if passed_anchor and len(collected) >= target_count:
        logging.debug(f"✅ HIST模式達標: {len(collected)}/{target_count}")
        return True
        
    # 條件2: 達到最大滾動次數
    if scroll_round >= max_scroll_rounds:
        logging.warning(f"⚠️ HIST模式達到滾動上限: {scroll_round}/{max_scroll_rounds}")
        return True
        
    return False