"""
測試三層備用提取系統：HTML → GraphQL → DOM
驗證我們修復的數據提取是否正常工作
"""

import asyncio
import logging
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from agents.playwright_crawler.extractors.details_extractor import DetailsExtractor
from common.models import PostMetrics

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_triple_backup_extraction():
    """測試三層備用提取系統"""
    
    print("🧪 測試三層備用數據提取系統")
    print("=" * 50)
    
    # 測試URL
    test_url = "https://www.threads.com/@netflixtw/post/DM_vwNio_wb"  # 有影片的貼文
    
    async with async_playwright() as p:
        # 啟動瀏覽器（非headless模式，避免反爬蟲）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-TW"
        )
        
        try:
            # 創建測試用的PostMetrics（添加required字段）
            test_post = PostMetrics(
                post_id="DM_9ebSBlTh",
                url=test_url,
                username="netflixtw",
                content="",
                likes_count=0,
                comments_count=0,
                reposts_count=0,
                shares_count=0,
                created_at=datetime.now(timezone.utc)  # 添加required字段
            )
            
            print(f"🎯 測試目標: {test_url}")
            print(f"📊 初始數據: 讚={test_post.likes_count}, 留言={test_post.comments_count}, 轉發={test_post.reposts_count}, 分享={test_post.shares_count}")
            print("-" * 50)
            
            # 使用修復的 DetailsExtractor
            extractor = DetailsExtractor()
            
            print("🚀 開始三層備用提取...")
            
            # 額外調試：先載入頁面一次，然後復用HTML內容
            print("🔍 載入頁面並分析HTML內容...")
            debug_page = await context.new_page()
            await debug_page.goto(test_url, wait_until="domcontentloaded")
            html_content = await debug_page.content()
            
            # 直接測試HTML解析
            html_result = extractor.html_parser.extract_from_html(html_content)
            print(f"   📊 HTML解析器結果: {html_result}")
            
            # 測試HTML解析一致性
            print("   🔄 再次解析同一HTML內容...")
            html_result2 = extractor.html_parser.extract_from_html(html_content)
            print(f"   📊 第二次解析結果: {html_result2}")
            
            if html_result == html_result2:
                print("   ✅ HTML解析結果一致")
            else:
                print("   ❌ HTML解析結果不一致！有Bug")
            
            # 尋找當前實際數據組合 (1271, 32, 53, 72)
            import re
            current_combo_search = re.search(r'1,?2[6-8][0-9]\s*\n?\s*3[0-5]\s*\n?\s*[4-6][0-9]\s*\n?\s*7[0-5]', html_content)
            if current_combo_search:
                print(f"   🎯 找到接近的數據組合: '{current_combo_search.group(0)}'")
            else:
                print(f"   🔍 搜索數字模式...")
                
                # 尋找包含1200+的任何模式
                pattern_1200 = re.findall(r'1,?[2-3][0-9][0-9][^0-9]*\d+[^0-9]*\d+[^0-9]*\d+', html_content)
                if pattern_1200:
                    print(f"   🎯 找到1200+的模式: {pattern_1200[:2]}")
                
                # 尋找所有4個數字的組合，按讚數在1000以上
                all_combos = re.findall(r'(\d{1,3}(?:,\d{3})*)[^0-9]+(\d+)[^0-9]+(\d+)[^0-9]+(\d+)', html_content)
                high_combos = []
                for combo in all_combos:
                    likes = int(combo[0].replace(',', ''))
                    if likes >= 1000:
                        high_combos.append(combo)
                
                if high_combos:
                    print(f"   📊 找到高互動組合: {high_combos[:3]}")
                
            await debug_page.close()
            print("-" * 30)
            
            filled_posts = await extractor.fill_post_details_from_page(
                [test_post], 
                context, 
                task_id="test_triple_backup",
                username="netflixtw"
            )
            
            # 檢查結果
            if filled_posts:
                result_post = filled_posts[0]
                print("=" * 50)
                print("🎉 提取結果:")
                print(f"   ❤️ 按讚數: {result_post.likes_count}")
                print(f"   💬 留言數: {result_post.comments_count}")
                print(f"   🔄 轉發數: {result_post.reposts_count}")
                print(f"   📤 分享數: {result_post.shares_count}")
                print(f"   👁️ 瀏覽數: {result_post.views_count}")
                print(f"   📊 計算分數: {result_post.calculated_score}")
                print(f"   📝 內容: {result_post.content[:100] if result_post.content else '無'}...")
                
                # === 顯示媒體內容 ===
                print(f"\n🎬 媒體內容:")
                if hasattr(result_post, 'images') and result_post.images:
                    print(f"   🖼️ 圖片數量: {len(result_post.images)}")
                    for i, img in enumerate(result_post.images[:3], 1):  # 只顯示前3個
                        print(f"      圖片{i}: {img[:80]}...")
                else:
                    print(f"   🖼️ 圖片數量: 0")
                    
                if hasattr(result_post, 'videos') and result_post.videos:
                    print(f"   🎥 影片數量: {len(result_post.videos)}")
                    for i, video in enumerate(result_post.videos, 1):
                        if video.startswith("POSTER::"):
                            print(f"      影片{i}(縮圖): {video[8:]}")  # 移除POSTER::前綴
                        else:
                            print(f"      🎬 影片{i}(完整URL): {video}")
                else:
                    print(f"   🎥 影片數量: 0")
                
                # 與目標JSON對比
                print("\n🎯 與目標JSON對比:")
                target_data = {
                    "likes_count": 172, "comments_count": 9, "reposts_count": 3, 
                    "shares_count": 8, "views_count": 36100, "calculated_score": 36155.4
                }
                actual_data = {
                    "likes_count": result_post.likes_count,
                    "comments_count": result_post.comments_count,
                    "reposts_count": result_post.reposts_count,
                    "shares_count": result_post.shares_count,
                    "views_count": result_post.views_count,
                    "calculated_score": result_post.calculated_score
                }
                
                print(f"   目標: {target_data}")
                print(f"   實際: {actual_data}")
                
                # 分析數據完整性
                missing_fields = []
                if not result_post.views_count: missing_fields.append("瀏覽數")
                if not result_post.calculated_score: missing_fields.append("計算分數")
                
                if missing_fields:
                    print(f"   ⚠️ 缺失欄位: {missing_fields}")
                else:
                    print(f"   ✅ 所有關鍵欄位都已填充")
                
                # 驗證成功標準
                total_interactions = (result_post.likes_count + result_post.comments_count + 
                                    result_post.reposts_count + result_post.shares_count)
                
                if total_interactions > 0:
                    print("✅ 測試成功！三層備用系統正常工作")
                    
                    # 詳細分析哪個方法成功了
                    if result_post.likes_count > 0:
                        print("   🎯 按讚數提取成功")
                    if result_post.comments_count > 0:
                        print("   🎯 留言數提取成功")
                    if result_post.reposts_count > 0:
                        print("   🎯 轉發數提取成功")
                    if result_post.shares_count > 0:
                        print("   🎯 分享數提取成功")
                        
                else:
                    print("❌ 測試失敗：沒有提取到任何互動數據")
                    print("   可能原因：")
                    print("   1. 頁面載入失敗")
                    print("   2. 所有三層方法都失敗")
                    print("   3. 網頁結構變化")
            else:
                print("❌ 測試失敗：沒有返回結果")
                
        except Exception as e:
            print(f"❌ 測試過程中發生錯誤: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    print("🚀 啟動三層備用系統測試...")
    asyncio.run(test_triple_backup_extraction())