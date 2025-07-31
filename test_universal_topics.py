#!/usr/bin/env python3
"""
測試通用主題支持
驗證系統能夠處理各種不同主題的貼文生成需求
"""

import httpx
import json
import asyncio
import uuid
from typing import Dict, Any

class UniversalTopicTester:
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"
        self.form_api_url = "http://localhost:8010"
        
    async def test_topic_detection(self, test_input: str, expected_topic: str = None):
        """測試主題檢測和問題生成"""
        session_id = str(uuid.uuid4())
        
        print(f"\n🧪 測試輸入: {test_input}")
        print(f"🎯 預期主題: {expected_topic or '自動檢測'}")
        print("-" * 50)
        
        try:
            # 發送到 Orchestrator
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.orchestrator_url}/user",
                    json={"text": test_input, "session_id": session_id},
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                if result["status"] == "need_clarification":
                    print("✅ 需要澄清，獲取問卷...")
                    
                    # 獲取問卷
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
                    
                    return True, questions_data["questions"]
                    
                elif result["status"] == "completed":
                    print("✅ 直接完成，無需澄清")
                    print(f"📝 生成內容: {result['final_post'][:100]}...")
                    return True, []
                    
        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            return False, []
    
    async def run_comprehensive_test(self):
        """運行全面的主題測試"""
        print("🎯 通用主題支持測試")
        print("=" * 60)
        
        test_cases = [
            # 美妝保養
            {
                "input": "我要寫一篇新品精華液的推薦貼文",
                "expected_topic": "美妝保養",
                "description": "美妝保養類貼文"
            },
            
            # 美食分享
            {
                "input": "推薦一家新開的咖啡店，環境很棒",
                "expected_topic": "美食分享", 
                "description": "美食分享類貼文"
            },
            
            # 旅遊生活
            {
                "input": "分享上週末去台北旅遊的心得",
                "expected_topic": "旅遊生活",
                "description": "旅遊生活類貼文"
            },
            
            # 時尚穿搭
            {
                "input": "今天的穿搭分享，秋冬搭配技巧",
                "expected_topic": "時尚穿搭",
                "description": "時尚穿搭類貼文"
            },
            
            # 科技數碼
            {
                "input": "新款手機開箱體驗，性能很不錯",
                "expected_topic": "科技數碼",
                "description": "科技數碼類貼文"
            },
            
            # 健康運動
            {
                "input": "分享我的健身心得和運動計劃",
                "expected_topic": "健康運動",
                "description": "健康運動類貼文"
            },
            
            # 商品推廣
            {
                "input": "新品上市限時優惠，現在買最划算",
                "expected_topic": "商品推廣",
                "description": "商品推廣類貼文"
            },
            
            # 生活日常
            {
                "input": "今天心情很好，想和大家分享一些感想",
                "expected_topic": "生活日常",
                "description": "生活日常類貼文"
            },
            
            # 教育學習
            {
                "input": "分享一些學習程式設計的心得和技巧",
                "expected_topic": "教育學習",
                "description": "教育學習類貼文"
            },
            
            # 娛樂休閒
            {
                "input": "最近看了一部很棒的電影，推薦給大家",
                "expected_topic": "娛樂休閒",
                "description": "娛樂休閒類貼文"
            },
            
            # 通用內容
            {
                "input": "我想要一個貼文",
                "expected_topic": "通用內容",
                "description": "模糊需求測試"
            }
        ]
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 測試案例 {i}: {test_case['description']}")
            success, questions = await self.test_topic_detection(
                test_case["input"], 
                test_case["expected_topic"]
            )
            
            results.append({
                "case": test_case["description"],
                "input": test_case["input"],
                "success": success,
                "questions_count": len(questions),
                "questions": [q["question"] for q in questions]
            })
            
            # 間隔一下避免請求過快
            await asyncio.sleep(1)
        
        # 總結報告
        self.print_summary_report(results)
        
        return results
    
    def print_summary_report(self, results):
        """打印總結報告"""
        print("\n" + "=" * 60)
        print("📊 通用主題支持測試總結")
        print("=" * 60)
        
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r["success"])
        
        print(f"總測試案例: {total_tests}")
        print(f"成功案例: {successful_tests}")
        print(f"成功率: {successful_tests/total_tests*100:.1f}%")
        print()
        
        print("📋 詳細結果:")
        for i, result in enumerate(results, 1):
            status = "✅" if result["success"] else "❌"
            print(f"{i:2d}. {status} {result['case']}")
            print(f"     輸入: {result['input']}")
            print(f"     問題數: {result['questions_count']}")
            if result["questions"]:
                print(f"     問題: {', '.join(result['questions'][:2])}{'...' if len(result['questions']) > 2 else ''}")
            print()
        
        if successful_tests == total_tests:
            print("🎉 所有測試通過！通用主題支持功能正常運作！")
        else:
            print(f"⚠️ {total_tests - successful_tests} 個測試失敗，需要檢查")

async def main():
    tester = UniversalTopicTester()
    
    # 先檢查服務健康狀態
    print("🏥 檢查服務健康狀態...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5)
            if response.status_code == 200:
                print("✅ Orchestrator 服務正常")
            else:
                print("⚠️ Orchestrator 服務異常")
                return
    except:
        print("❌ 無法連接到 Orchestrator 服務")
        return
    
    # 運行測試
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())