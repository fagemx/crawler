#!/usr/bin/env python3
"""
測試 Gemini 多模態媒體處理
測試圖片媒體是否正確傳遞給 Gemini API
"""

import os
import sys
import asyncio
import base64
from pathlib import Path
import json
from typing import List, Dict, Any

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

try:
    from common.llm_manager import LLMManager
    from services.rustfs_client import RustFSClient
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
except ImportError as e:
    print(f"❌ 導入模組失敗: {e}")
    print("請確保相關模組已安裝")
    sys.exit(1)

class GeminiMediaTester:
    def __init__(self):
        """初始化測試器"""
        # 載入環境變數
        from dotenv import load_dotenv
        load_dotenv()
        
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not self.gemini_api_key:
            raise ValueError("❌ 未找到 GEMINI_API_KEY 環境變數")
        
        # 配置 Gemini
        genai.configure(api_key=self.gemini_api_key)
        
        # 安全設定
        self.safety_settings = [
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
        ]
        
        self.llm_manager = LLMManager()
        self.rustfs_client = RustFSClient()

    def load_test_image(self, image_path: str) -> bytes:
        """載入測試圖片"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"❌ 測試圖片不存在: {image_path}")
        
        with open(image_path, 'rb') as f:
            return f.read()

    def test_direct_gemini_api(self, image_data: bytes, mime_type: str = "image/jpeg"):
        """直接測試 Gemini API（不透過 LLMManager）"""
        print("\n🔬 測試 1: 直接 Gemini API 調用")
        print("=" * 50)
        
        try:
            # 創建 Gemini 模型
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # 準備圖片部分
            image_part = {
                "mime_type": mime_type,
                "data": image_data
            }
            
            # 準備提示
            prompt = "請詳細描述這張圖片的內容，包括主要物件、顏色、場景等。"
            
            print(f"📊 圖片大小: {len(image_data)} bytes")
            print(f"📊 MIME 類型: {mime_type}")
            print(f"📊 模型: gemini-2.0-flash")
            print(f"📊 提示: {prompt}")
            
            # 發送請求
            print("\n⏳ 發送請求到 Gemini...")
            response = model.generate_content([prompt, image_part])
            
            print("\n✅ Gemini 直接 API 調用成功！")
            print("📝 回應內容:")
            print("-" * 30)
            print(response.text)
            print("-" * 30)
            
            return True
            
        except Exception as e:
            print(f"❌ 直接 Gemini API 調用失敗: {e}")
            return False

    def test_gemini_2_5_pro(self, image_data: bytes, mime_type: str = "image/jpeg"):
        """測試 Gemini 2.5 Pro"""
        print("\n🔬 測試 2: Gemini 2.5 Pro 調用")
        print("=" * 50)
        
        try:
            # 創建 Gemini 模型
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            # 準備圖片部分
            image_part = {
                "mime_type": mime_type,
                "data": image_data
            }
            
            # 準備提示
            prompt = "根據這張圖片，寫一篇社群媒體貼文，風格要活潑有趣，長度約100-150字。"
            
            print(f"📊 圖片大小: {len(image_data)} bytes")
            print(f"📊 MIME 類型: {mime_type}")
            print(f"📊 模型: gemini-2.0-flash-exp")
            print(f"📊 提示: {prompt}")
            
            # 發送請求
            print("\n⏳ 發送請求到 Gemini 2.5 Pro...")
            response = model.generate_content([prompt, image_part])
            
            print("\n✅ Gemini 2.5 Pro 調用成功！")
            print("📝 回應內容:")
            print("-" * 30)
            print(response.text)
            print("-" * 30)
            
            return True
            
        except Exception as e:
            print(f"❌ Gemini 2.5 Pro 調用失敗: {e}")
            return False

    async def test_llm_manager_multimodal(self, image_data: bytes, mime_type: str = "image/jpeg"):
        """測試透過 LLMManager 的多模態調用"""
        print("\n🔬 測試 3: 透過 LLMManager 多模態調用")
        print("=" * 50)
        
        try:
            # 準備 Gemini parts
            image_part = {
                "mime_type": mime_type,
                "data": image_data
            }
            
            gemini_parts = [
                "根據這張圖片，創作一篇社群媒體貼文。要求：風格活潑、長度適中、有趣吸引人。",
                image_part
            ]
            
            print(f"📊 圖片大小: {len(image_data)} bytes")
            print(f"📊 MIME 類型: {mime_type}")
            print(f"📊 模型: gemini-2.0-flash")
            print("📊 Gemini Parts 結構:")
            print(f"  - 文字提示: {len(gemini_parts[0])} 字元")
            print(f"  - 圖片部分: {len(image_part['data'])} bytes")
            
            # 調用 LLMManager
            print("\n⏳ 透過 LLMManager 發送請求...")
            response = await self.llm_manager.chat_completion(
                messages=[{"role": "user", "content": "請根據提供的圖片創作貼文"}],
                provider="gemini",
                model="gemini-2.0-flash",
                gemini_parts=gemini_parts,
                usage_scene="media-test"
            )
            
            print("\n✅ LLMManager 多模態調用成功！")
            print("📝 回應內容:")
            print("-" * 30)
            print(response.content)
            print("-" * 30)
            
            return True
            
        except Exception as e:
            print(f"❌ LLMManager 多模態調用失敗: {e}")
            import traceback
            print(f"🔍 錯誤詳情: {traceback.format_exc()}")
            return False

    async def test_rustfs_upload_and_retrieve(self, image_data: bytes, filename: str, mime_type: str):
        """測試 RustFS 上傳和檢索"""
        print("\n🔬 測試 4: RustFS 媒體上傳和檢索")
        print("=" * 50)
        
        try:
            print(f"📊 上傳檔案: {filename}")
            print(f"📊 檔案大小: {len(image_data)} bytes")
            print(f"📊 MIME 類型: {mime_type}")
            
            # 上傳到 RustFS
            print("\n⏳ 上傳到 RustFS...")
            upload_result = await self.rustfs_client.upload_user_media(filename, image_data, mime_type)
            
            print("✅ RustFS 上傳成功！")
            print(f"📝 上傳結果: {upload_result}")
            
            # 獲取 URL
            key = upload_result.get('key')
            if key:
                print(f"\n⏳ 獲取可訪問 URL...")
                url = self.rustfs_client.get_public_or_presigned_url(key, prefer_presigned=True)
                print(f"✅ 獲取 URL 成功: {url}")
                
                # 嘗試下載並驗證
                print(f"\n⏳ 驗證上傳檔案...")
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        downloaded_data = response.content
                        if len(downloaded_data) == len(image_data):
                            print("✅ 檔案驗證成功，上傳下載一致")
                        else:
                            print(f"⚠️ 檔案大小不一致：原始 {len(image_data)} vs 下載 {len(downloaded_data)}")
                    else:
                        print(f"❌ 下載失敗: HTTP {response.status_code}")
            
            return upload_result
            
        except Exception as e:
            print(f"❌ RustFS 測試失敗: {e}")
            import traceback
            print(f"🔍 錯誤詳情: {traceback.format_exc()}")
            return None

    def create_sample_image(self, filename: str = "test_sample.png"):
        """創建一個簡單的測試圖片（如果沒有現成的）"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            
            # 創建一個簡單的測試圖片
            img = Image.new('RGB', (400, 300), color='lightblue')
            draw = ImageDraw.Draw(img)
            
            # 添加一些文字和圖形
            draw.rectangle([50, 50, 350, 250], outline='navy', width=3)
            draw.text((100, 120), "測試圖片", fill='navy')
            draw.text((100, 150), "Test Image", fill='navy')
            draw.text((100, 180), f"檔名: {filename}", fill='darkblue')
            
            # 保存到記憶體
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_data = img_buffer.getvalue()
            
            # 也保存到檔案
            img.save(filename)
            print(f"✅ 創建測試圖片: {filename}")
            
            return img_data
            
        except ImportError:
            print("⚠️ PIL 未安裝，無法創建測試圖片")
            return None

async def main():
    """主測試函數"""
    print("🧪 Gemini 多模態媒體測試")
    print("=" * 60)
    
    try:
        tester = GeminiMediaTester()
        
        # 尋找測試圖片或創建一個
        test_image_path = "test_sample.png"
        image_data = None
        
        if os.path.exists(test_image_path):
            print(f"📁 使用現有測試圖片: {test_image_path}")
            image_data = tester.load_test_image(test_image_path)
        else:
            print("📁 未找到測試圖片，嘗試創建...")
            image_data = tester.create_sample_image(test_image_path)
            
        if not image_data:
            print("❌ 無法獲取測試圖片，請手動放置一張圖片到 test_sample.png")
            return
        
        mime_type = "image/png"
        
        # 執行所有測試
        results = []
        
        # 測試 1: 直接 Gemini API
        result1 = tester.test_direct_gemini_api(image_data, mime_type)
        results.append(("直接 Gemini API", result1))
        
        # 測試 2: Gemini 2.5 Pro
        result2 = tester.test_gemini_2_5_pro(image_data, mime_type)
        results.append(("Gemini 2.5 Pro", result2))
        
        # 測試 3: LLMManager 多模態
        result3 = await tester.test_llm_manager_multimodal(image_data, mime_type)
        results.append(("LLMManager 多模態", result3))
        
        # 測試 4: RustFS 上傳檢索
        result4 = await tester.test_rustfs_upload_and_retrieve(image_data, test_image_path, mime_type)
        results.append(("RustFS 上傳檢索", result4 is not None))
        
        # 總結報告
        print("\n" + "=" * 60)
        print("📊 測試結果總結")
        print("=" * 60)
        
        for test_name, success in results:
            status = "✅ 成功" if success else "❌ 失敗"
            print(f"{test_name:<20} {status}")
        
        success_count = sum(1 for _, success in results if success)
        print(f"\n🎯 成功率: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
        
        if success_count == len(results):
            print("🎉 所有測試通過！多模態功能運作正常。")
        else:
            print("⚠️ 部分測試失敗，請檢查錯誤訊息。")
        
    except Exception as e:
        print(f"❌ 測試執行失敗: {e}")
        import traceback
        print(f"🔍 錯誤詳情: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(main())
