"""
使用 JSON 檔案測試 Vision Agent 的圖像內容描述功能

直接從 crawl_data JSON 檔案讀取圖片和影片 URL，進行內容分析
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List

# 載入 .env 檔案
from dotenv import load_dotenv
load_dotenv()

# 設定環境變數（如果 .env 中沒有的話）
os.environ.setdefault("RUSTFS_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("RUSTFS_ACCESS_KEY", "rustfsadmin")
os.environ.setdefault("RUSTFS_SECRET_KEY", "rustfsadmin")

from agents.vision.gemini_vision import GeminiVisionAnalyzer
from common.rustfs_client import get_rustfs_client


async def load_json_data(json_file_path: str) -> Dict[str, Any]:
    """載入 JSON 檔案"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 載入 JSON 檔案失敗: {str(e)}")
        return {}


async def analyze_single_media(analyzer: GeminiVisionAnalyzer, media_url: str, media_type: str) -> Dict[str, Any]:
    """分析單一媒體檔案"""
    try:
        print(f"📥 下載媒體: {media_url[:80]}...")
        
        # 下載媒體
        rustfs_client = get_rustfs_client()
        media_bytes, mime_type = await rustfs_client.download_media(media_url)
        
        print(f"   - 檔案大小: {len(media_bytes)} bytes")
        print(f"   - MIME 類型: {mime_type}")
        
        # 使用 Gemini 分析內容
        print(f"🤖 使用 Gemini 分析{media_type}內容...")
        content_description = await analyzer.analyze_media(media_bytes, mime_type)
        
        return {
            "success": True,
            "media_url": media_url,
            "media_type": media_type,
            "mime_type": mime_type,
            "file_size": len(media_bytes),
            "content_description": content_description
        }
        
    except Exception as e:
        return {
            "success": False,
            "media_url": media_url,
            "media_type": media_type,
            "error": str(e)
        }


async def process_post_media(analyzer: GeminiVisionAnalyzer, post: Dict[str, Any]) -> Dict[str, Any]:
    """處理單一貼文的所有媒體"""
    print(f"\n🔍 處理貼文: {post['url']}")
    print(f"   內容: {post['content'][:100]}...")
    
    results = {
        "post_url": post['url'],
        "post_content": post['content'],
        "images": [],
        "videos": []
    }
    
    # 處理圖片
    if post.get('images'):
        print(f"📸 發現 {len(post['images'])} 張圖片")
        for img_url in post['images']:
            result = await analyze_single_media(analyzer, img_url, "圖片")
            results['images'].append(result)
    
    # 處理影片
    if post.get('videos'):
        print(f"🎬 發現 {len(post['videos'])} 個影片")
        for video_url in post['videos']:
            result = await analyze_single_media(analyzer, video_url, "影片")
            results['videos'].append(result)
    
    if not post.get('images') and not post.get('videos'):
        print("   ℹ️  此貼文沒有圖片或影片")
    
    return results


async def main():
    """主測試函數"""
    print("🚀 開始測試 Vision Agent 圖像內容描述功能")
    print("=" * 60)
    
    # 檢查必要的環境變數
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("❌ 請設定 GOOGLE_API_KEY 或 GEMINI_API_KEY 環境變數")
        return False
    
    # 載入 JSON 數據
    json_file = "agents/playwright_crawler/debug/crawl_data_20250725_140924_test_cra.json"
    print(f"📄 載入 JSON 檔案: {json_file}")
    
    data = await load_json_data(json_file)
    if not data:
        return False
    
    print(f"✅ 載入成功，共 {len(data.get('posts', []))} 個貼文")
    
    # 初始化 Gemini Vision 分析器
    try:
        analyzer = GeminiVisionAnalyzer()
        print("✅ Gemini Vision 分析器初始化成功")
    except Exception as e:
        print(f"❌ Gemini Vision 分析器初始化失敗: {str(e)}")
        return False
    
    # 統計媒體數量
    total_images = sum(len(post.get('images', [])) for post in data.get('posts', []))
    total_videos = sum(len(post.get('videos', [])) for post in data.get('posts', []))
    
    print(f"📊 媒體統計: {total_images} 張圖片, {total_videos} 個影片")
    
    if total_images == 0 and total_videos == 0:
        print("⚠️  沒有找到任何媒體檔案")
        return True
    
    # 處理每個貼文
    all_results = []
    
    for i, post in enumerate(data.get('posts', []), 1):
        print(f"\n📝 處理第 {i}/{len(data['posts'])} 個貼文")
        
        try:
            result = await process_post_media(analyzer, post)
            all_results.append(result)
            
            # 顯示分析結果摘要
            success_images = sum(1 for img in result['images'] if img['success'])
            success_videos = sum(1 for vid in result['videos'] if vid['success'])
            
            print(f"   ✅ 成功分析: {success_images} 張圖片, {success_videos} 個影片")
            
        except Exception as e:
            print(f"   ❌ 處理失敗: {str(e)}")
            continue
    
    # 保存結果
    output_file = "vision_analysis_results.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 分析結果已保存到: {output_file}")
    except Exception as e:
        print(f"⚠️  保存結果失敗: {str(e)}")
    
    # 總結
    total_success_images = sum(
        sum(1 for img in result['images'] if img['success']) 
        for result in all_results
    )
    total_success_videos = sum(
        sum(1 for vid in result['videos'] if vid['success']) 
        for result in all_results
    )
    
    print("\n" + "=" * 60)
    print("📊 最終統計:")
    print(f"   成功分析圖片: {total_success_images}/{total_images}")
    print(f"   成功分析影片: {total_success_videos}/{total_videos}")
    print(f"   總成功率: {(total_success_images + total_success_videos)/(total_images + total_videos)*100:.1f}%")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)