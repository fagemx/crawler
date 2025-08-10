#!/usr/bin/env python3
"""
最簡單的測試：讓 Gemini 描述圖片
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

try:
    import google.generativeai as genai
    from dotenv import load_dotenv
except ImportError as e:
    print(f"❌ 導入失敗: {e}")
    sys.exit(1)

def main():
    """簡單測試：描述圖片"""
    
    # 載入環境變數
    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ 未找到 GEMINI_API_KEY")
        return
    
    # 配置 Gemini
    genai.configure(api_key=api_key)
    
    # 載入圖片
    image_path = "tests/Configscreenshot.png"
    if not os.path.exists(image_path):
        print(f"❌ 找不到圖片: {image_path}")
        return
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"📷 圖片大小: {len(image_data)} bytes")
    
    # 準備圖片
    image_part = {
        "mime_type": "image/png",
        "data": image_data
    }
    
    # 簡單提示
    prompt = "描述這張圖片"
    
    print(f"💬 提示: {prompt}")
    print("\n⏳ 請求 Gemini...")
    
    try:
        # 使用 gemini-2.5-pro
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content([prompt, image_part])
        
        print("✅ 成功！")
        print("\n📝 Gemini 的描述:")
        print("=" * 60)
        print(response.text)
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 失敗: {e}")

if __name__ == "__main__":
    main()
