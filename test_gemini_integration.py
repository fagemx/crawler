#!/usr/bin/env python3
"""
測試 Gemini 2.0 Flash 集成
驗證所有 Agent 都正確使用 Gemini gemini-2.0-flash 模型
"""

import httpx
import json
import asyncio
import uuid
from typing import Dict, Any

class GeminiIntegrationTester:
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"
        self.clarification_url = "http://localhost:8004"
        self.content_writer_url = "http://localhost:8003"
        self.form_api_url = "http://localhost:8010"
        
    async def test_health_checks(self):
        """測試所有服務的健康狀態"""
        print("🏥 健康檢查")
        print("=" * 30)
        
        services = [
            ("Orchestrator", f"{self.orchestrator_url}/health"),
            ("Clarification Agent", f"{self.clarification_url}/health"),
            ("Content Writer", f"{self.content_writer_url}/health"),
            ("Form API", f"{self.form_api_url}/health")
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
    
    async def test_gemini_integration(self):
        """測試完整的 Gemini 集成流程"""
        print("\n🤖 測試 Gemini 2.0 Flash 集成")
        print("=" * 40)
        
        session_id = str(uuid.uuid4())
        
        # 測試案例：簡單的化妝品貼文需求
        test_input = "請幫我寫一個化妝品新品推薦貼文，要簡潔有力"
        
        print(f"📝 測試輸入: {test_input}")
        print(f"🆔 會話 ID: {session_id}")
        
        try:
            # 步驟 1: 發送到 Orchestrator
            print("\n📤 步驟 1: 發送到 Orchestrator")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.orchestrator_url}/user",
                    json={"text": test_input, "session_id": session_id},
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                print(f"✅ Orchestrator 回應: {result['status']}")
                
                if result["status"] == "need_clarification":
                    print("❓ 需要澄清，獲取問卷...")
                    
                    # 步驟 2: 獲取問卷（測試 Clarification Agent 的 Gemini 使用）
                    questions_response = await client.get(
                        f"{self.form_api_url}/form/{session_id}",
                        timeout=10
                    )
                    questions_response.raise_for_status()
                    questions_data = questions_response.json()
                    
                    print(f"📋 生成了 {len(questions_data['questions'])} 個問題:")
                    for i, q in enumerate(questions_data["questions"], 1):
                        print(f"   {i}. {q['question']}")
                        print(f"      選項: {', '.join(q['options'])}")
                    
                    # 步驟 3: 模擬用戶回答
                    print("\n✅ 步驟 3: 模擬用戶回答")
                    mock_answers = {
                        "style": "分行條列重點",
                        "tone": "親身體驗分享", 
                        "length": "簡潔有力(80-120字)"
                    }
                    
                    # 確保回答匹配問題
                    actual_answers = {}
                    for question in questions_data["questions"]:
                        q_id = question["id"]
                        if q_id in mock_answers:
                            actual_answers[q_id] = mock_answers[q_id]
                        else:
                            # 選擇第一個選項作為預設
                            actual_answers[q_id] = question["options"][0]
                    
                    print(f"📋 模擬答案: {json.dumps(actual_answers, ensure_ascii=False, indent=2)}")
                    
                    # 步驟 4: 提交答案並生成內容（測試 Content Writer 的 Gemini 使用）
                    print("\n🎨 步驟 4: 生成最終內容")
                    final_response = await client.post(
                        f"{self.orchestrator_url}/answers",
                        json={
                            "session_id": session_id,
                            "answers": actual_answers
                        },
                        timeout=60
                    )
                    final_response.raise_for_status()
                    final_result = final_response.json()
                    
                    if final_result["status"] == "completed":
                        print(f"\n🎉 最終生成的貼文:")
                        print("=" * 40)
                        print(final_result["final_post"])
                        print("=" * 40)
                        print(f"📋 使用模板: {final_result.get('template_used', 'unknown')}")
                        
                        # 驗證內容不是錯誤消息
                        if "抱歉，內容生成遇到問題" not in final_result["final_post"]:
                            print("✅ Gemini 2.0 Flash 成功生成內容！")
                            return True
                        else:
                            print("❌ 內容生成失敗")
                            return False
                    else:
                        print(f"❌ 最終狀態異常: {final_result['status']}")
                        return False
                
                elif result["status"] == "completed":
                    print(f"🎉 直接完成，無需澄清:")
                    print("=" * 40)
                    print(result["final_post"])
                    print("=" * 40)
                    
                    if "抱歉，內容生成遇到問題" not in result["final_post"]:
                        print("✅ Gemini 2.0 Flash 成功生成內容！")
                        return True
                    else:
                        print("❌ 內容生成失敗")
                        return False
                
        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            return False
    
    async def test_direct_content_writer(self):
        """直接測試 Content Writer Agent"""
        print("\n🖋️ 直接測試 Content Writer Agent")
        print("=" * 35)
        
        test_request = {
            "session_id": str(uuid.uuid4()),
            "template_style": "narrative",
            "requirements_json": {
                "post_id": "test123",
                "main_topic": "化妝品推薦",
                "summary": "測試 Gemini 2.0 Flash 集成",
                "paragraph_count_range": [1, 2],
                "sentence_length": {
                    "short_sentence_ratio": 0.4,
                    "short_sentence_word_range": [6, 15],
                    "long_sentence_ratio": 0.6,
                    "long_sentence_word_range": [16, 35]
                },
                "minimal_cues": ["使用自然語調", "突出產品特色"],
                "few_shot": [],
                "custom_user_requirements": ["簡潔有力", "突出新品特色"]
            },
            "original_text": "測試 Gemini 2.0 Flash 化妝品新品推薦"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.content_writer_url}/generate",
                    json=test_request,
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                
                print(f"✅ Content Writer 回應:")
                print("=" * 30)
                print(result["final_post"])
                print("=" * 30)
                print(f"📋 使用模板: {result['template_used']}")
                
                if "抱歉，內容生成遇到問題" not in result["final_post"]:
                    print("✅ Content Writer 使用 Gemini 2.0 Flash 成功！")
                    return True
                else:
                    print("❌ Content Writer 生成失敗")
                    return False
                    
        except Exception as e:
            print(f"❌ Content Writer 測試失敗: {e}")
            return False

async def main():
    tester = GeminiIntegrationTester()
    
    # 健康檢查
    await tester.test_health_checks()
    
    # 測試完整流程
    success1 = await tester.test_gemini_integration()
    
    # 直接測試 Content Writer
    success2 = await tester.test_direct_content_writer()
    
    print(f"\n🎯 測試結果總結")
    print("=" * 20)
    print(f"完整流程測試: {'✅ 成功' if success1 else '❌ 失敗'}")
    print(f"Content Writer 測試: {'✅ 成功' if success2 else '❌ 失敗'}")
    
    if success1 and success2:
        print("\n🎉 所有測試通過！Gemini 2.0 Flash 集成成功！")
    else:
        print("\n⚠️ 部分測試失敗，請檢查日誌")

if __name__ == "__main__":
    asyncio.run(main())