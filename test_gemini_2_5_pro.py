#!/usr/bin/env python3
"""
專門測試 gemini-2.5-pro 多模態功能
簡化版本，專注於圖片媒體處理
"""

import os
import sys
import base64
from pathlib import Path
import json

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    from dotenv import load_dotenv
except ImportError as e:
    print(f"❌ 導入模組失敗: {e}")
    print("請安裝: pip install google-generativeai python-dotenv pillow")
    sys.exit(1)

def create_test_image():
    """創建測試圖片"""
    try:
        from PIL import Image, ImageDraw
        import io
        
        # 創建一個簡單的測試圖片
        img = Image.new('RGB', (600, 400), color='skyblue')
        draw = ImageDraw.Draw(img)
        
        # 添加一些視覺元素
        draw.rectangle([50, 50, 550, 350], outline='darkblue', width=5)
        draw.ellipse([200, 150, 400, 250], fill='yellow', outline='orange', width=3)
        draw.rectangle([100, 300, 200, 320], fill='red')
        draw.rectangle([250, 300, 350, 320], fill='green')
        draw.rectangle([400, 300, 500, 320], fill='blue')
        
        # 保存到記憶體
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_data = img_buffer.getvalue()
        
        # 也保存到檔案
        img.save("test_image.png")
        print(f"✅ 創建測試圖片: test_image.png (大小: {len(img_data)} bytes)")
        
        return img_data
        
    except ImportError:
        print("❌ PIL 未安裝，請安裝: pip install pillow")
        return None

def test_gemini_models(image_data):
    """測試不同的 Gemini 模型"""
    
    # 載入環境變數
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ 未找到 GEMINI_API_KEY 環境變數")
        return
    
    # 配置 Gemini
    genai.configure(api_key=api_key)
    
    # 要測試的模型
    models_to_test = [
        "gemini-2.0-flash", 
        "gemini-2.0-flash-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]
    
    # 準備圖片部分
    image_part = {
        "mime_type": "image/png",
        "data": image_data
    }
    
    # 測試提示
    prompts = [
        "請詳細描述這張圖片的內容，包括顏色、形狀和佈局。",
        "根據這張圖片，寫一篇活潑有趣的社群媒體貼文，約100字。",
        "這張圖片適合用於什麼類型的內容？請給出3個建議。"
    ]
    
    results = {}
    
    for model_name in models_to_test:
        print(f"\n🔬 測試模型: {model_name}")
        print("=" * 50)
        
        try:
            model = genai.GenerativeModel(model_name)
            
            for i, prompt in enumerate(prompts, 1):
                print(f"\n📝 測試 {i}: {prompt[:50]}...")
                
                try:
                    # 發送請求
                    response = model.generate_content([prompt, image_part])
                    
                    print(f"✅ 成功！回應長度: {len(response.text)} 字元")
                    print("📄 回應內容:")
                    print("-" * 30)
                    print(response.text)
                    print("-" * 30)
                    
                    # 記錄結果
                    if model_name not in results:
                        results[model_name] = []
                    results[model_name].append({
                        "prompt": prompt,
                        "response": response.text,
                        "success": True
                    })
                    
                except Exception as e:
                    print(f"❌ 失敗: {e}")
                    if model_name not in results:
                        results[model_name] = []
                    results[model_name].append({
                        "prompt": prompt,
                        "error": str(e),
                        "success": False
                    })
                    
        except Exception as e:
            print(f"❌ 模型 {model_name} 初始化失敗: {e}")
            results[model_name] = [{"error": f"模型初始化失敗: {e}", "success": False}]
    
    return results

def print_summary(results):
    """列印測試總結"""
    print("\n" + "=" * 60)
    print("📊 測試總結")
    print("=" * 60)
    
    for model_name, model_results in results.items():
        success_count = sum(1 for r in model_results if r.get("success", False))
        total_count = len(model_results)
        success_rate = success_count / total_count * 100 if total_count > 0 else 0
        
        status = "✅" if success_rate == 100 else "⚠️" if success_rate > 0 else "❌"
        print(f"{status} {model_name:<20} {success_count}/{total_count} ({success_rate:.1f}%)")
    
    print("\n🎯 建議:")
    best_models = [name for name, results in results.items() 
                   if all(r.get("success", False) for r in results)]
    
    if best_models:
        print(f"✅ 推薦使用: {', '.join(best_models)}")
    else:
        print("⚠️ 所有模型都有部分問題，請檢查 API 金鑰和網路連線")

def main():
    """主函數"""
    print("🧪 Gemini 2.5 Pro 多模態測試")
    print("=" * 60)
    
    # 創建或載入測試圖片
    if os.path.exists("test_image.png"):
        print("📁 使用現有測試圖片")
        with open("test_image.png", "rb") as f:
            image_data = f.read()
    else:
        print("📁 創建新的測試圖片")
        image_data = create_test_image()
    
    if not image_data:
        print("❌ 無法獲取測試圖片")
        return
    
    print(f"📊 圖片大小: {len(image_data)} bytes")
    
    # 執行測試
    results = test_gemini_models(image_data)
    
    # 列印總結
    print_summary(results)
    
    # 保存詳細結果
    with open("gemini_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 詳細結果已保存到: gemini_test_results.json")

if __name__ == "__main__":
    main()
