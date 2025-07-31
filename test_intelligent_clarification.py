#!/usr/bin/env python3
"""
測試智能澄清系統 - 完整流程
測試案例：「請幫我創建貼文，簡單一點，然後化妝新品月底前打8折」
"""

import httpx
import json
import asyncio
import uuid
from typing import Dict, Any

class IntelligentClarificationTester:
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"
        self.form_api_url = "http://localhost:8010"
        self.session_id = str(uuid.uuid4())
        
    async def test_complete_intelligent_flow(self):
        """測試完整的智能澄清流程"""
        print("🎯 測試智能澄清系統")
        print(f"會話 ID: {self.session_id}")
        print("=" * 60)
        
        # 測試案例
        test_cases = [
            {
                "name": "化妝品優惠貼文",
                "input": "請幫我創建貼文，簡單一點，然後化妝新品月底前打8折",
                "expected_questions": ["style", "tone", "length"]
            },
            {
                "name": "模糊需求測試",
                "input": "我想要一個貼文",
                "expected_questions": ["style", "tone", "length", "topic"]
            },
            {
                "name": "詳細需求測試", 
                "input": "我要寫一篇連貫敘事風格的美妝保養貼文，用親身經歷的語氣，大概200字，要提到新品上市和限時優惠",
                "expected_questions": []  # 應該不需要澄清
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n🧪 測試案例 {i}: {test_case['name']}")
            print(f"輸入: {test_case['input']}")
            print("-" * 40)
            
            await self.run_single_test(test_case)
            
            if i < len(test_cases):
                print("\n" + "="*60)
                await asyncio.sleep(2)  # 間隔一下
    
    async def run_single_test(self, test_case: Dict[str, Any]):
        """運行單個測試案例"""
        session_id = str(uuid.uuid4())
        
        # 步驟 1: 發送初始請求
        print("📝 步驟 1: 發送用戶需求")
        user_request = {
            "text": test_case["input"],
            "session_id": session_id
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
                    print("❓ 需要澄清，獲取問卷...")
                    
                    # 步驟 2: 獲取問卷
                    questions_data = await self.get_questions(session_id)
                    if questions_data:
                        print(f"📋 生成了 {len(questions_data['questions'])} 個問題:")
                        for j, q in enumerate(questions_data["questions"], 1):
                            print(f"   {j}. {q['question']}")
                            print(f"      選項: {', '.join(q['options'])}")
                        
                        # 步驟 3: 模擬用戶回答
                        print("\n✅ 步驟 3: 模擬用戶回答")
                        answers = self.generate_smart_answers(questions_data["questions"], test_case["input"])
                        print(f"📋 模擬答案: {json.dumps(answers, ensure_ascii=False, indent=2)}")
                        
                        # 步驟 4: 提交答案並生成內容
                        final_result = await self.submit_answers(session_id, answers)
                        if final_result:
                            print(f"\n🎉 最終生成的貼文:")
                            print("=" * 40)
                            print(final_result["final_post"])
                            print("=" * 40)
                            print(f"📋 使用模板: {final_result.get('template_used', 'unknown')}")
                
                elif result["status"] == "completed":
                    print(f"🎉 直接完成，無需澄清:")
                    print("=" * 40)
                    print(result["final_post"])
                    print("=" * 40)
                    
            except Exception as e:
                print(f"❌ 測試失敗: {e}")
    
    async def get_questions(self, session_id: str) -> Dict[str, Any]:
        """獲取問卷"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.form_api_url}/form/{session_id}",
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"❌ 獲取問卷失敗: {e}")
                return None
    
    async def submit_answers(self, session_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
        """提交答案"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.orchestrator_url}/answers",
                    json={
                        "session_id": session_id,
                        "answers": answers
                    },
                    timeout=60
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"❌ 提交答案失敗: {e}")
                return None
    
    def generate_smart_answers(self, questions: list, original_input: str) -> Dict[str, str]:
        """根據問題和原始輸入智能生成答案"""
        answers = {}
        
        for question in questions:
            q_id = question["id"]
            options = question["options"]
            
            # 根據原始輸入和問題類型智能選擇答案
            if q_id == "style":
                if "簡單" in original_input:
                    answers[q_id] = "分行條列重點"
                else:
                    answers[q_id] = "連貫敘事風格"
            
            elif q_id == "tone":
                if "化妝" in original_input or "保養" in original_input:
                    answers[q_id] = "親身體驗分享"
                else:
                    answers[q_id] = "客觀產品介紹"
            
            elif q_id == "length":
                if "簡單" in original_input:
                    answers[q_id] = "簡潔有力(80-120字)"
                else:
                    answers[q_id] = "詳細介紹(200-300字)"
            
            elif q_id == "product_focus":
                if "打折" in original_input or "優惠" in original_input:
                    answers[q_id] = "突出價格優惠"
                else:
                    answers[q_id] = "強調效果體驗"
            
            elif q_id == "special_requirements":
                if "新品" in original_input:
                    answers[q_id] = "自訂:強調新品上市，文末加入 #新品推薦"
                else:
                    answers[q_id] = "需要加入 hashtag"
            
            else:
                # 預設選擇第一個非自訂選項
                non_custom_options = [opt for opt in options if opt != "自訂"]
                if non_custom_options:
                    answers[q_id] = non_custom_options[0]
                else:
                    answers[q_id] = options[0]
        
        return answers
    
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
    tester = IntelligentClarificationTester()
    
    # 先檢查服務健康狀態
    await tester.test_health_checks()
    
    # 測試完整流程
    await tester.test_complete_intelligent_flow()
    
    print("\n🎯 智能澄清系統測試完成！")

if __name__ == "__main__":
    asyncio.run(main())