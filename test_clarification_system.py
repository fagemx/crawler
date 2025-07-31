#!/usr/bin/env python3
"""
測試澄清系統的完整流程
"""

import httpx
import json
import asyncio
import uuid
from typing import Dict, Any

class ClarificationSystemTester:
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"
        self.form_api_url = "http://localhost:8010"
        self.session_id = str(uuid.uuid4())
        
    async def test_complete_flow(self):
        """測試完整的澄清流程"""
        print("🚀 開始測試澄清系統完整流程")
        print(f"會話 ID: {self.session_id}")
        print("=" * 60)
        
        # 步驟 1: 發送初始請求
        print("\n📝 步驟 1: 發送初始請求")
        user_request = {
            "text": "我要一篇新品乳霜的推薦貼文",
            "session_id": self.session_id
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.orchestrator_url}/user",
                    json=user_request,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                print(f"✅ Orchestrator 回應: {result['status']}")
                
                if result["status"] == "need_clarification":
                    print(f"🔗 表單 URL: {result['form_url']}")
                    
                    # 步驟 2: 獲取問卷
                    print("\n❓ 步驟 2: 獲取澄清問卷")
                    await self.test_get_questions()
                    
                    # 步驟 3: 提交答案
                    print("\n✅ 步驟 3: 提交答案")
                    await self.test_submit_answers()
                    
                elif result["status"] == "completed":
                    print(f"🎉 直接完成: {result['final_post']}")
                    
            except Exception as e:
                print(f"❌ 初始請求失敗: {e}")
                return
    
    async def test_get_questions(self):
        """測試獲取問卷"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.form_api_url}/form/{self.session_id}",
                    timeout=10
                )
                response.raise_for_status()
                questions_data = response.json()
                
                print(f"✅ 成功獲取 {len(questions_data['questions'])} 個問題")
                
                for i, question in enumerate(questions_data["questions"], 1):
                    print(f"   問題 {i}: {question['question']}")
                    print(f"   選項: {', '.join(question['options'])}")
                
                self.questions = questions_data["questions"]
                
            except Exception as e:
                print(f"❌ 獲取問卷失敗: {e}")
    
    async def test_submit_answers(self):
        """測試提交答案"""
        # 模擬用戶答案 - 針對化妝品貼文
        answers = {
            "style": "分行條列重點",
            "tone": "親身體驗分享", 
            "product_focus": "突出價格優惠",
            "length": "簡潔有力(80-120字)",
            "special_requirements": "自訂:文末加入 #新品推薦 #限時優惠"
        }
        
        print(f"📋 提交的答案: {json.dumps(answers, ensure_ascii=False, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.orchestrator_url}/answers",
                    json={
                        "session_id": self.session_id,
                        "answers": answers
                    },
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                
                print(f"✅ 答案提交成功: {result['status']}")
                
                if result["status"] == "completed":
                    print(f"🎉 最終生成的貼文:")
                    print("-" * 40)
                    print(result["final_post"])
                    print("-" * 40)
                    print(f"📋 使用模板: {result.get('template_used', 'unknown')}")
                
            except Exception as e:
                print(f"❌ 提交答案失敗: {e}")
    
    async def test_health_checks(self):
        """測試所有服務的健康狀態"""
        print("\n🏥 健康檢查")
        print("=" * 30)
        
        services = [
            ("Orchestrator", "http://localhost:8000/health"),
            ("Clarification Agent", "http://localhost:8004/health"),
            ("Content Writer", "http://localhost:8003/health"),
            ("Form API", "http://localhost:8010/health")
        ]
        
        async with httpx.AsyncClient() as client:
            for name, url in services:
                try:
                    response = await client.get(url, timeout=5)
                    if response.status_code == 200:
                        print(f"✅ {name}: 正常")
                    else:
                        print(f"⚠️ {name}: HTTP {response.status_code}")
                except Exception as e:
                    print(f"❌ {name}: 連接失敗 ({e})")

async def main():
    tester = ClarificationSystemTester()
    
    # 先檢查服務健康狀態
    await tester.test_health_checks()
    
    # 測試完整流程
    await tester.test_complete_flow()
    
    print("\n🎯 測試完成！")

if __name__ == "__main__":
    asyncio.run(main())