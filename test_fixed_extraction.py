#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試修正後的正式版本提取邏輯
"""

from common.rotation_pipeline import RotationPipelineReader

def test_fixed_extraction():
    """測試修正後的提取邏輯"""
    
    print("🧪 測試正式版本的修正邏輯")
    print("=" * 50)
    
    # 創建rotation實例
    reader = RotationPipelineReader()
    
    # 測試兩個貼文
    test_urls = [
        "https://www.threads.com/@gvmonthly/post/DMzvu4MTpis",  # 主貼文
        "https://www.threads.com/@gvmonthly/post/DMzvyiSzkdc",  # 回覆貼文
    ]
    
    for url in test_urls:
        print(f"\n📍 測試: {url}")
        post_id = url.split('/')[-1]
        
        # 使用Jina API獲取內容
        success, content = reader.fetch_content_jina_api(url)
        
        if success:
            # 使用修正後的提取邏輯
            extracted_content = reader.extract_post_content(content)
            views = reader.extract_views_count(content, post_id)
            
            print(f"✅ 成功獲取內容")
            print(f"📝 提取內容: {extracted_content}")
            print(f"👁️ 觀看數: {views}")
            
            # 驗證結果
            if post_id == "DMzvu4MTpis":
                if "關稅+台幣升值" in (extracted_content or ""):
                    print("✅ 主貼文內容正確！")
                elif ">>>232條款" in (extracted_content or ""):
                    print("❌ 仍然提取到回覆內容")
                else:
                    print(f"⚠️ 提取到其他內容")
            
            elif post_id == "DMzvyiSzkdc":
                if ">>>232條款" in (extracted_content or ""):
                    print("✅ 回覆內容正確！")
                elif "關稅+台幣升值" in (extracted_content or ""):
                    print("❌ 提取到主貼文而非回覆")
                else:
                    print(f"⚠️ 提取到其他內容")
        
        else:
            print(f"❌ 獲取失敗: {content}")

if __name__ == "__main__":
    test_fixed_extraction()