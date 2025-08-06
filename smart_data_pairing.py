"""
智能數據配對器
從多個JSON數據中正確配對出主貼文的互動數據
"""

import asyncio
import re
from playwright.async_api import async_playwright

async def smart_data_pairing():
    """智能數據配對分析"""
    
    print("🧠 智能數據配對器")
    print("=" * 50)
    
    url = "https://www.threads.com/@netflixtw/post/DM_9ebSBlTh"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="zh-TW"
        )
        
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            html_content = await page.content()
            
            # === 方法1：尋找完整的JSON對象 ===
            print("🎯 方法1：尋找完整JSON對象")
            
            # 尋找包含所有4個指標的完整JSON對象
            complete_json_pattern = r'"like_count":\s*(\d+).*?"direct_reply_count":\s*(\d+).*?"repost_count":\s*(\d+).*?"reshare_count":\s*(\d+)'
            complete_matches = re.findall(complete_json_pattern, html_content, re.DOTALL)
            
            print(f"   📊 找到 {len(complete_matches)} 個完整JSON對象")
            for i, match in enumerate(complete_matches):
                likes, comments, reposts, shares = [int(x) for x in match]
                score = 0
                
                # 評分系統（基於已知目標值 1271, 32, 53, 72）
                if 1200 <= likes <= 1350: score += 50
                if 25 <= comments <= 40: score += 30  
                if 40 <= reposts <= 65: score += 20
                if 65 <= shares <= 80: score += 20
                
                total = likes + comments + reposts + shares
                if total > 1000: score += 10  # 主貼文總數應該較高
                
                print(f"   {i+1}. 讚={likes}, 留言={comments}, 轉發={reposts}, 分享={shares} (得分: {score})")
            
            # === 方法2：基於距離的JSON配對 ===
            print("\n🔗 方法2：基於距離的JSON配對")
            
            # 提取所有JSON指標及其在HTML中的位置
            metrics_with_pos = []
            
            for metric, pattern in [
                ("likes", r'"like_count":\s*(\d+)'),
                ("comments", r'"direct_reply_count":\s*(\d+)'),
                ("reposts", r'"repost_count":\s*(\d+)'),
                ("shares", r'"reshare_count":\s*(\d+)')
            ]:
                for match in re.finditer(pattern, html_content):
                    value = int(match.group(1))
                    position = match.start()
                    metrics_with_pos.append((metric, value, position))
            
            # 按位置排序
            metrics_with_pos.sort(key=lambda x: x[2])
            
            # 尋找距離最近的4個指標組合
            print("   📍 前20個JSON指標及位置:")
            for metric, value, pos in metrics_with_pos[:20]:
                print(f"      {metric}: {value} (位置: {pos})")
            
            # === 方法3：基於內容錨點的精確定位 ===
            print("\n⚓ 方法3：基於TENBLANK錨點定位")
            
            # 尋找TENBLANK內容的位置
            content_matches = list(re.finditer(r'TENBLANK.*?CHROME.*?今天要發新歌', html_content, re.DOTALL))
            
            if content_matches:
                for i, content_match in enumerate(content_matches):
                    print(f"   📍 找到TENBLANK內容 {i+1} (位置: {content_match.start()})")
                    
                    # 在這個內容前後5000字符內尋找JSON數據
                    start = max(0, content_match.start() - 5000)
                    end = min(len(html_content), content_match.end() + 5000)
                    target_area = html_content[start:end]
                    
                    # 在目標區域尋找完整JSON對象
                    area_matches = re.findall(complete_json_pattern, target_area, re.DOTALL)
                    print(f"   🎯 在TENBLANK區域找到 {len(area_matches)} 個JSON對象:")
                    
                    for j, match in enumerate(area_matches):
                        likes, comments, reposts, shares = [int(x) for x in match]
                        # 計算與目標值的相似度
                        target_likes, target_comments, target_reposts, target_shares = 1271, 32, 53, 72
                        similarity = (
                            abs(likes - target_likes) +
                            abs(comments - target_comments) + 
                            abs(reposts - target_reposts) +
                            abs(shares - target_shares)
                        )
                        
                        print(f"      {j+1}. 讚={likes}, 留言={comments}, 轉發={reposts}, 分享={shares} (差異: {similarity})")
            
            # === 方法4：直接元素配對驗證 ===
            print("\n🎯 方法4：元素配對驗證")
            
            try:
                # 獲取頁面上顯示的實際數字
                like_element = page.locator('svg[aria-label="讚"] ~ span').first
                if await like_element.count() > 0:
                    like_text = await like_element.inner_text()
                    print(f"   ❤️ 頁面顯示按讚數: '{like_text}'")
                    
                    # 將頁面顯示的數字與JSON數據對比
                    like_number = int(like_text.replace(',', ''))
                    print(f"   🔍 尋找JSON中匹配 {like_number} 的完整對象...")
                    
                    for match in complete_matches:
                        likes, comments, reposts, shares = [int(x) for x in match]
                        if abs(likes - like_number) <= 5:  # 允許5以內的差異
                            print(f"   ✅ 找到匹配: 讚={likes}, 留言={comments}, 轉發={reposts}, 分享={shares}")
                            
            except Exception as e:
                print(f"   ❌ 元素驗證失敗: {e}")
            
            # === 最終推薦 ===
            print("\n🏆 最終推薦")
            print("-" * 30)
            
            # 基於所有分析，推薦最佳候選
            if complete_matches:
                # 選擇得分最高的組合
                best_match = None
                best_score = -1
                
                for match in complete_matches:
                    likes, comments, reposts, shares = [int(x) for x in match]
                    
                    # 綜合評分
                    score = 0
                    if 1200 <= likes <= 1350: score += 50
                    if 25 <= comments <= 40: score += 30
                    if 40 <= reposts <= 65: score += 20  
                    if 65 <= shares <= 80: score += 20
                    if likes + comments + reposts + shares > 1000: score += 10
                    
                    if score > best_score:
                        best_score = score
                        best_match = (likes, comments, reposts, shares)
                
                if best_match:
                    likes, comments, reposts, shares = best_match
                    print(f"🎯 推薦數據: 讚={likes}, 留言={comments}, 轉發={reposts}, 分享={shares}")
                    print(f"📊 置信度: {best_score}/130")
                    
                    # 與目標值對比
                    target = (1271, 32, 53, 72)
                    actual = best_match
                    diff = sum(abs(a - t) for a, t in zip(actual, target))
                    print(f"🎯 與目標值差異: {diff} (越小越好)")
            
        except Exception as e:
            print(f"❌ 分析過程出錯: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(smart_data_pairing())