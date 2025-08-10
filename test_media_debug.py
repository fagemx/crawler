#!/usr/bin/env python3
"""
除錯用：測試媒體傳遞給 Gemini 的完整流程
專門檢查我們系統中的媒體處理邏輯
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

def load_test_image():
    """載入指定的測試圖片"""
    test_image_path = "tests/Configscreenshot.png"
    
    if not os.path.exists(test_image_path):
        print(f"❌ 找不到測試圖片: {test_image_path}")
        print("請確認圖片路徑是否正確")
        return None
    
    try:
        with open(test_image_path, 'rb') as f:
            image_data = f.read()
        
        print(f"✅ 成功載入測試圖片: {test_image_path}")
        print(f"   圖片大小: {len(image_data)} bytes")
        
        return image_data
        
    except Exception as e:
        print(f"❌ 載入圖片失敗: {e}")
        return None

async def test_system_media_flow():
    """測試系統的媒體處理流程"""
    
    print("🔍 測試系統媒體處理流程")
    print("=" * 50)
    
    # 載入測試圖片
    print("1️⃣ 載入測試圖片...")
    image_data = load_test_image()
    if not image_data:
        print("   ❌ 無法載入測試圖片，測試中斷")
        return False
    
    # 模擬媒體上傳結果
    print("\n2️⃣ 模擬媒體上傳...")
    mock_media_result = {
        'key': 'test/Configscreenshot.png',
        'url': 'http://localhost:9000/social-media-content/test/Configscreenshot.png',
        'size': len(image_data),
        'mime_type': 'image/png'
    }
    print(f"   ✅ 模擬上傳結果: {mock_media_result}")
    
    # 模擬 generation_data
    print("\n3️⃣ 構建生成請求...")
    generation_data = {
        'user_prompt': '根據這張配置截圖寫一篇社群貼文，介紹這個界面的功能',
        'llm_config': {
            'provider': 'Gemini (Google)',
            'model': 'gemini-2.5-pro'
        },
        'settings': {
            'writing_style': '活潑有趣',
            'content_type': '社群貼文',
            'target_length': '中等',
            'tone': '友善親切',
            'post_count': 1,
            'media_enabled': True
        },
        'media': {
            'enabled': True,
            'images': [mock_media_result],
            'videos': []
        }
    }
    
    print(f"   ✅ 生成請求結構:")
    print(f"      - 提示: {generation_data['user_prompt']}")
    print(f"      - 模型: {generation_data['llm_config']['model']}")
    print(f"      - 媒體啟用: {generation_data['media']['enabled']}")
    print(f"      - 圖片數量: {len(generation_data['media']['images'])}")
    
    # 測試內容生成服務
    print("\n4️⃣ 測試內容生成服務...")
    try:
        import httpx
        
        print("   📡 發送請求到 content-generator...")
        print(f"   🔗 URL: http://localhost:8008/generate-content")
        print(f"   📦 請求大小: {len(json.dumps(generation_data))} 字元")
        
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "http://localhost:8008/generate-content",
                json=generation_data,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"   📊 回應狀態: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                generated_posts = result.get('generated_posts', [])
                
                print(f"   ✅ 成功生成 {len(generated_posts)} 篇貼文")
                
                for i, post in enumerate(generated_posts):
                    print(f"\n   📝 貼文 {i+1}:")
                    print(f"   {'-' * 40}")
                    print(f"   {post}")
                    print(f"   {'-' * 40}")
                
                # 檢查是否真的使用了圖片內容
                for post in generated_posts:
                    has_image_ref = any(keyword in post.lower() for keyword in [
                        '圖片', '圖像', '照片', '影像', '視覺', '顏色', '看到', '顯示',
                        'image', 'photo', 'picture', 'visual', 'color', 'see', 'show'
                    ])
                    
                    if has_image_ref:
                        print(f"   🎯 檢測到圖片相關內容：✅")
                    else:
                        print(f"   ⚠️ 未檢測到明顯的圖片相關內容")
                
                return True
            else:
                print(f"   ❌ 請求失敗: {response.status_code}")
                print(f"   📄 錯誤內容: {response.text}")
                return False
                
    except Exception as e:
        print(f"   ❌ 測試失敗: {e}")
        import traceback
        print(f"   🔍 詳細錯誤: {traceback.format_exc()}")
        return False

async def test_direct_gemini_with_our_logic():
    """直接測試我們的 Gemini 邏輯"""
    
    print("\n\n🔬 直接測試 Gemini 處理邏輯")
    print("=" * 50)
    
    try:
        # 導入我們的模組
        from common.llm_manager import LLMManager
        
        # 載入測試圖片
        image_data = load_test_image()
        if not image_data:
            print("❌ 無法載入測試圖片，測試中斷")
            return False
        
        # 準備 Gemini parts（模擬我們系統的邏輯）
        image_part = {
            "mime_type": "image/png", 
            "data": image_data
        }
        
        prompt_text = """
你是一個專業的社群媒體內容創作者。
請嚴格遵守以下規則：
1. 必須參照提供的媒體內容（圖片或影片）進行創作。
2. 風格要活潑有趣，長度約100-150字。
3. 輸出必須以「【版本1】」開頭。
4. 只輸出貼文內容，不要包含任何分析、解釋或額外對話。

根據這張配置截圖，創作一篇社群媒體貼文，介紹這個界面的功能特色。
"""
        
        gemini_parts = [prompt_text, image_part]
        
        print(f"📊 測試資料:")
        print(f"   - 圖片大小: {len(image_data)} bytes")
        print(f"   - 提示長度: {len(prompt_text)} 字元")
        print(f"   - Gemini Parts: {len(gemini_parts)} 個")
        
        # 透過 LLMManager 調用
        print("\n📡 透過 LLMManager 調用...")
        llm_manager = LLMManager()
        
        response = await llm_manager.chat_completion(
            messages=[{"role": "user", "content": "請根據圖片創作貼文"}],
            provider="gemini",
            model="gemini-2.5-pro",
            gemini_parts=gemini_parts,
            usage_scene="debug-test"
        )
        
        print(f"✅ LLMManager 調用成功！")
        print(f"📝 生成內容:")
        print("-" * 40)
        print(response.content)
        print("-" * 40)
        
        return True
        
    except Exception as e:
        print(f"❌ 直接測試失敗: {e}")
        import traceback
        print(f"🔍 詳細錯誤: {traceback.format_exc()}")
        return False

def main():
    """主函數"""
    print("🐛 媒體傳遞除錯測試")
    print("=" * 60)
    print("目的：檢查圖片是否正確傳遞給 Gemini，並產生相關內容")
    print("=" * 60)
    
    async def run_tests():
        # 測試1：系統完整流程
        result1 = await test_system_media_flow()
        
        # 測試2：直接 LLMManager 調用
        result2 = await test_direct_gemini_with_our_logic()
        
        # 總結
        print("\n" + "=" * 60)
        print("📊 測試結果總結")
        print("=" * 60)
        print(f"系統完整流程: {'✅ 成功' if result1 else '❌ 失敗'}")
        print(f"直接 LLMManager: {'✅ 成功' if result2 else '❌ 失敗'}")
        
        if result1 and result2:
            print("\n🎉 所有測試通過！媒體處理正常運作。")
        elif result1 or result2:
            print("\n⚠️ 部分測試成功，請檢查失敗的部分。")
        else:
            print("\n❌ 所有測試失敗，請檢查配置和服務狀態。")
    
    asyncio.run(run_tests())

if __name__ == "__main__":
    main()
