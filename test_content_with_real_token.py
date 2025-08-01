"""
使用真實的 LSD token 測試內容查詢
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import sys
sys.path.append(str(Path(__file__).parent))

# 直接從成功的實例中復制必要部分
from test_full_post_strategy import ThreadsFullPostFetcher

async def test_content_queries_with_real_token():
    """使用真實 LSD token 測試內容查詢"""
    print("🚀 使用真實 LSD token 測試內容查詢...")
    
    # 讀取認證
    from common.config import get_auth_file_path
    auth_file_path = get_auth_file_path()
    
    # 創建 fetcher 實例
    fetcher = ThreadsFullPostFetcher(auth_file_path)
    
    try:
        # 步驟1: 獲取真實的 LSD token (從 GraphQL 響應中)
        print("   🔑 獲取真實 LSD token...")
        test_url = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
        pk, captured_pks = await fetcher.extract_pk_from_gate_page(test_url)
        
        if not fetcher.lsd_token:
            print("   ❌ 無法獲取 LSD token")
            return
        
        print(f"   ✅ 成功獲取 LSD token: {fetcher.lsd_token[:10]}...")
        
        # 步驟2: 測試各種內容查詢 doc_id
        print("\n🧪 使用真實 token 測試內容查詢...")
        
        # 擴展的 doc_id 測試列表
        test_doc_ids = [
            "7428920450586442",  # SingleThreadQuery
            "7248604598467997",  # BarcelonaPostPageContentQuery  
            "7439738349112860",  # ProfileThreadsTabQuery
            "6981243555252543",  # BarcelonaPostPageFeedMediaQuery
            "7127871700615871",  # BarcelonaPostPageDirectQuery
            "7268729639845570",  # ThreadQuery
            "7395825420492230",  # MediaQuery
            "7396485793756116",  # BarcelonaPostPageRefetchableDirectQuery
            "25924527474041776", # 較新的查詢ID
            "8523948474355533",  # 另一個可能的ID
            # 添加一些可能的新 ID
            "8234567890123456",
            "7567890123456789",
            "6789012345678901",
        ]
        
        test_pk = pk  # 使用真實的 PK
        valid_doc_ids = []
        
        for doc_id in test_doc_ids:
            print(f"\n   🧪 測試 doc_id: {doc_id}")
            
            # 測試新格式變數
            try:
                variables = json.dumps({
                    "postID_pk": test_pk,
                    "withShallowTree": False,
                    "includePromotedPosts": False
                })
                
                data = f"lsd={fetcher.lsd_token}&doc_id={doc_id}&variables={variables}"
                headers = {"x-fb-lsd": fetcher.lsd_token}
                
                response = await fetcher.http_client.post(
                    "https://www.threads.com/graphql/query",
                    data=data,
                    headers=headers
                )
                
                print(f"      新格式: HTTP {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        print(f"      📋 響應鍵: {list(result.keys())}")
                        
                        # 如果有錯誤，顯示錯誤訊息
                        if "errors" in result:
                            errors = result["errors"]
                            print(f"      ❌ 錯誤訊息: {errors[:1]}")  # 只顯示第一個錯誤
                        
                        if "data" in result and result["data"]:
                            data_keys = list(result["data"].keys())
                            print(f"      📋 data 鍵: {data_keys}")
                            
                            # 檢查各種可能的內容結構
                            content_found = False
                            
                            if "media" in result["data"]:
                                media = result["data"]["media"]
                                if media:
                                    print(f"      ✅ 找到 media 內容!")
                                    print(f"         媒體類型: {media.get('__typename')}")
                                    if "caption" in media:
                                        caption_text = media.get("caption", {}).get("text", "")
                                        print(f"         內容長度: {len(caption_text)}")
                                        print(f"         內容預覽: {caption_text[:100]}...")
                                    content_found = True
                            
                            elif "containing_thread" in result["data"]:
                                thread = result["data"]["containing_thread"]
                                if thread and "thread_items" in thread:
                                    print(f"      ✅ 找到 thread_items 內容!")
                                    content_found = True
                            
                            elif "post" in result["data"]:
                                post = result["data"]["post"]
                                if post:
                                    print(f"      ✅ 找到 post 內容!")
                                    content_found = True
                            
                            if content_found:
                                valid_doc_ids.append((doc_id, "new_format", result))
                                print(f"      🎉 有效的內容查詢 (新格式): {doc_id}")
                                
                                # 保存響應用於分析
                                debug_file = Path(f"valid_content_response_{doc_id}_{datetime.now().strftime('%H%M%S')}.json")
                                with open(debug_file, 'w', encoding='utf-8') as f:
                                    json.dump(result, f, indent=2, ensure_ascii=False)
                                print(f"      📁 已保存響應到: {debug_file}")
                            else:
                                print(f"      ⚠️ 有響應但無識別的內容結構")
                        else:
                            print(f"      ❌ 空 data 或錯誤響應")
                    except Exception as e:
                        print(f"      ❌ 解析響應失敗: {e}")
                        
                elif response.status_code == 400:
                    print(f"      ❌ 400 錯誤 - 可能是錯誤的變數格式")
                elif response.status_code == 401:
                    print(f"      ❌ 401 錯誤 - 認證問題")
                elif response.status_code == 500:
                    print(f"      ❌ 500 錯誤 - 伺服器錯誤")
                else:
                    print(f"      ❌ 其他錯誤: {response.status_code}")
                    
            except Exception as e:
                print(f"      ❌ 新格式測試失敗: {e}")
                
            # 如果新格式失敗，測試舊格式
            if doc_id in ["7428920450586442", "7248604598467997", "7439738349112860"]:
                try:
                    variables = json.dumps({
                        "postID": test_pk,
                        "includePromotedPosts": False
                    })
                    
                    data = f"lsd={fetcher.lsd_token}&doc_id={doc_id}&variables={variables}"
                    headers = {"x-fb-lsd": fetcher.lsd_token}
                    
                    response = await fetcher.http_client.post(
                        "https://www.threads.com/graphql/query",
                        data=data,
                        headers=headers
                    )
                    
                    print(f"      舊格式: HTTP {response.status_code}")
                    
                    if response.status_code == 200:
                        try:
                            result = response.json()
                            if ("data" in result and result["data"] and 
                                any(key in result["data"] for key in ["media", "containing_thread", "post"])):
                                valid_doc_ids.append((doc_id, "old_format", result))
                                print(f"      🎉 有效的內容查詢 (舊格式): {doc_id}")
                        except:
                            pass
                            
                except Exception as e:
                    print(f"      ❌ 舊格式測試失敗: {e}")
        
        # 報告結果
        print(f"\n📊 測試結果:")
        if valid_doc_ids:
            print(f"   ✅ 找到 {len(valid_doc_ids)} 個有效的內容查詢:")
            for doc_id, format_type, _ in valid_doc_ids:
                print(f"      🎯 {doc_id} ({format_type})")
            
            # 使用第一個有效的 doc_id 進行完整測試
            best_doc_id, best_format, best_response = valid_doc_ids[0]
            print(f"\n🧪 使用最佳 doc_id {best_doc_id} 進行完整測試...")
            
            # 分析響應結構
            if "data" in best_response and "media" in best_response["data"]:
                media = best_response["data"]["media"]
                print(f"   📝 媒體內容分析:")
                print(f"      類型: {media.get('__typename')}")
                print(f"      ID: {media.get('id')}")
                
                if "caption" in media:
                    caption = media["caption"]
                    if caption:
                        text = caption.get("text", "")
                        print(f"      文字內容: {len(text)} 字符")
                        print(f"      內容預覽: {text[:200]}...")
                
                if "image_versions2" in media:
                    images = media["image_versions2"]
                    if images and "candidates" in images:
                        candidates = images["candidates"]
                        print(f"      圖片: {len(candidates)} 個版本")
                        for i, candidate in enumerate(candidates[:3]):
                            print(f"         圖片 {i+1}: {candidate.get('width')}x{candidate.get('height')} - {candidate.get('url', '')[:50]}...")
                
                if "video_versions" in media:
                    videos = media["video_versions"]
                    print(f"      影片: {len(videos)} 個版本")
                    
            return best_doc_id
            
        else:
            print(f"   ❌ 未找到任何有效的內容查詢")
            return None
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        await fetcher.close()

async def main():
    """主函數"""
    doc_id = await test_content_queries_with_real_token()
    if doc_id:
        print(f"\n🎉 找到最佳內容查詢 doc_id: {doc_id}")
        print(f"💡 請將此 doc_id 更新到 test_full_post_strategy.py 中")
    else:
        print(f"\n😞 未找到有效的內容查詢 doc_id")

if __name__ == "__main__":
    asyncio.run(main())