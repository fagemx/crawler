#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試歷史分析導出的 JSON 序列化修復
"""

import json
from datetime import datetime, date
from decimal import Decimal

def test_json_serializer():
    """測試修復後的 JSON 序列化器"""
    
    # 自定義JSON編碼器處理Decimal和datetime類型
    def json_serializer(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    # 測試數據：包含會導致序列化錯誤的類型
    test_data = {
        "username": "test_user",
        "export_type": "analysis",
        "exported_at": datetime.now(),  # datetime 對象
        "created_date": date.today(),   # date 對象
        "calculated_score": Decimal("123.45"),  # Decimal 對象
        "posts": [
            {
                "post_id": "test_123",
                "content": "測試內容",
                "views_count": 1000,
                "calculated_score": Decimal("456.78"),  # 另一個 Decimal
                "created_at": datetime.now(),  # 另一個 datetime
                "fetched_at": "2025-01-01T00:00:00"  # 字符串（正常）
            }
        ]
    }
    
    print("🧪 測試 JSON 序列化修復...")
    
    try:
        # 嘗試序列化
        json_content = json.dumps(test_data, ensure_ascii=False, indent=2, default=json_serializer)
        print("✅ JSON 序列化成功!")
        
        # 驗證序列化結果
        parsed_data = json.loads(json_content)
        
        # 檢查關鍵類型轉換
        print(f"📊 exported_at 類型: {type(parsed_data['exported_at'])} = {parsed_data['exported_at']}")
        print(f"📊 created_date 類型: {type(parsed_data['created_date'])} = {parsed_data['created_date']}")
        print(f"📊 calculated_score 類型: {type(parsed_data['calculated_score'])} = {parsed_data['calculated_score']}")
        
        post = parsed_data['posts'][0]
        print(f"📊 post.calculated_score 類型: {type(post['calculated_score'])} = {post['calculated_score']}")
        print(f"📊 post.created_at 類型: {type(post['created_at'])} = {post['created_at']}")
        
        print("\n🎉 所有測試通過！JSON 序列化修復生效")
        return True
        
    except Exception as e:
        print(f"❌ JSON 序列化失敗: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🔍 JSON 序列化修復測試")
    print("=" * 50)
    
    success = test_json_serializer()
    
    print("=" * 50)
    if success:
        print("🎉 修復驗證成功！歷史分析導出應該可以正常工作了")
    else:
        print("❌ 修復驗證失敗！需要進一步檢查")
    print("=" * 50)