#!/usr/bin/env python3
"""
Clarification Agent - 智能澄清問卷生成服務
根據用戶模糊需求，智能生成問題表單，最終填寫完整的 JSON 結構
"""

import json
import uuid
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.llm_manager import get_llm_manager, chat_completion
from common.settings import get_settings
from common.mcp_client import init_mcp_client, agent_startup, agent_shutdown

app = FastAPI(title="Clarification Agent", version="1.0.0")

class ClarifyRequest(BaseModel):
    session_id: str
    text: str

class ClarifyResponse(BaseModel):
    session_id: str
    need_clarification: bool
    questions: List[Dict[str, Any]]

class ClarificationAgent:
    def __init__(self):
        self.settings = get_settings()
        self.llm_manager = get_llm_manager()
    
    def _parse_llm_json_response(self, response_content: str) -> Dict[str, Any]:
        """解析 LLM 的 JSON 響應"""
        import re
        
        # 首先嘗試找到 ```json ... ``` 塊
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # 如果沒找到，找第一個 '{' 和最後一個 '}'
            start_index = response_content.find('{')
            end_index = response_content.rfind('}')
            if start_index != -1 and end_index != -1 and end_index > start_index:
                json_str = response_content[start_index:end_index+1]
            else:
                raise json.JSONDecodeError("No valid JSON object found in the response.", response_content, 0)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON string: {json_str}")
            raise e
        
    def analyze_user_input(self, text: str) -> Dict[str, Any]:
        """智能分析用戶輸入，識別明確和模糊的部分"""
        analysis = {
            "explicit_requirements": [],  # 明確提到的需求
            "missing_fields": [],         # 缺失的關鍵欄位
            "detected_topic": "",         # 檢測到的主題
            "detected_style_hints": []    # 風格暗示
        }
        
        text_lower = text.lower()
        
        # 智能檢測主題類別
        topic_keywords = {
            "美妝保養": ["化妝", "保養", "護膚", "美妝", "乳霜", "精華", "面膜", "粉底", "口紅", "眼影"],
            "時尚穿搭": ["服裝", "穿搭", "時尚", "衣服", "搭配", "風格", "流行", "配件"],
            "美食分享": ["美食", "餐廳", "料理", "食物", "菜單", "味道", "烹飪", "食譜", "咖啡", "甜點"],
            "旅遊生活": ["旅遊", "旅行", "景點", "度假", "出遊", "風景", "體驗", "探索"],
            "科技數碼": ["科技", "數碼", "手機", "電腦", "軟體", "應用", "AI", "程式"],
            "健康運動": ["健康", "運動", "健身", "瑜伽", "跑步", "鍛鍊", "營養", "減肥"],
            "生活日常": ["生活", "日常", "心情", "分享", "感想", "體驗", "故事"],
            "商品推廣": ["推薦", "新品", "優惠", "折扣", "限時", "特價", "促銷", "活動"],
            "教育學習": ["學習", "教育", "課程", "知識", "技能", "教學", "分享"],
            "娛樂休閒": ["電影", "音樂", "遊戲", "娛樂", "休閒", "興趣", "愛好"]
        }
        
        detected_topics = []
        for topic, keywords in topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                detected_topics.append(topic)
        
        # 選擇最匹配的主題，如果沒有匹配則為通用
        if detected_topics:
            analysis["detected_topic"] = detected_topics[0]  # 取第一個匹配的主題
        else:
            analysis["detected_topic"] = "通用內容"
        
        # 檢測明確需求
        if "打折" in text or "優惠" in text or "%" in text:
            analysis["explicit_requirements"].append("包含優惠資訊")
        if "新品" in text:
            analysis["explicit_requirements"].append("強調新品特色")
        if "簡單" in text:
            analysis["explicit_requirements"].append("語言簡潔明瞭")
        
        # 檢測缺失欄位
        missing_fields = []
        if not any(word in text_lower for word in ["風格", "排版", "分行", "連貫"]):
            missing_fields.append("style")
        if not any(word in text_lower for word in ["字數", "長度", "簡短", "詳細"]):
            missing_fields.append("length")
        if not any(word in text_lower for word in ["語氣", "視角", "我", "親身", "客觀"]):
            missing_fields.append("tone")
        if "#" not in text and "hashtag" not in text_lower and "標籤" not in text:
            missing_fields.append("hashtags")
        if "emoji" not in text_lower and "表情" not in text and "😊" not in text:
            missing_fields.append("emoji")
        
        analysis["missing_fields"] = missing_fields
        return analysis
    
    def build_intelligent_prompt(self, text: str, analysis: Dict[str, Any]) -> str:
        """構建智能提示詞，根據分析結果生成問題"""
        prompt = f"""你是一個專業的社交媒體內容顧問。用戶提出了一個貼文需求，你需要根據缺失的資訊生成 3-5 個問題來完善需求。

用戶原始需求: "{text}"

檢測到的主題: {analysis['detected_topic']}
明確提到的需求: {', '.join(analysis['explicit_requirements']) if analysis['explicit_requirements'] else '無'}
需要澄清的欄位: {', '.join(analysis['missing_fields'])}

請生成 3-5 個問題，每個問題提供 2 個智能建議選項 + 1 個"自訂"選項。
問題要針對缺失的欄位，選項要符合檢測到的主題和用戶需求。

回應格式（必須是有效的 JSON）:
{{
  "need_clarification": true,
  "questions": [
    {{
      "id": "style",
      "question": "你希望貼文的呈現風格是？",
      "options": ["連貫敘事風格", "分行條列重點", "自訂"]
    }},
    {{
      "id": "tone",
      "question": "語氣偏好？",
      "options": ["親身體驗分享", "客觀產品介紹", "自訂"]
    }},
    {{
      "id": "length",
      "question": "內容長度偏好？",
      "options": ["簡潔有力(80-120字)", "詳細介紹(200-300字)", "自訂"]
    }},
    {{
      "id": "special_requirements",
      "question": "有什麼特殊要求嗎？",
      "options": ["需要加入 hashtag", "避免提及價格", "自訂"]
    }}
  ]
}}

請確保問題針對性強，選項實用，JSON 格式正確。"""
        
        return prompt
    
    async def generate_clarification(self, text: str) -> Dict[str, Any]:
        """智能生成澄清問卷"""
        try:
            # 分析用戶輸入
            analysis = self.analyze_user_input(text)
            
            # 如果沒有缺失欄位，不需要澄清
            if not analysis["missing_fields"]:
                return {
                    "need_clarification": False,
                    "questions": []
                }
            
            # 構建智能提示詞
            prompt = self.build_intelligent_prompt(text, analysis)
            
            messages = [
                {"role": "system", "content": "你是一個專業的社交媒體內容顧問，擅長根據用戶需求生成精準的澄清問題。"},
                {"role": "user", "content": prompt}
            ]
            
            # 使用新的 LLM 管理器
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",  # 明確指定模型
                temperature=0.3,
                max_tokens=1500,
                provider="gemini",
                usage_scene="clarification"
            )
            
            # 解析 JSON 響應
            result = self._parse_llm_json_response(content)
            
            # 確保問題數量在 3-5 之間
            if len(result.get("questions", [])) > 5:
                result["questions"] = result["questions"][:5]
            elif len(result.get("questions", [])) < 3:
                # 如果問題太少，使用預設問題補充
                default_questions = self.get_default_questions_for_topic(analysis["detected_topic"])
                result["questions"].extend(default_questions["questions"][:5-len(result["questions"])])
            
            return result
                
        except Exception as e:
            print(f"生成澄清問卷失敗: {e}")
            # 回退到預設問卷
            return self.get_default_questions_for_topic(self.analyze_user_input(text)["detected_topic"])
    
    def get_default_questions_for_topic(self, topic: str) -> Dict[str, Any]:
        """根據主題獲取預設問卷"""
        
        # 通用基礎問題
        base_questions = [
            {
                "id": "style",
                "question": "你希望貼文的呈現風格是？",
                "options": ["連貫敘事風格", "分行條列重點", "自訂"]
            },
            {
                "id": "tone",
                "question": "語氣偏好？",
                "options": ["親身體驗分享", "客觀資訊介紹", "自訂"]
            },
            {
                "id": "length",
                "question": "內容長度偏好？",
                "options": ["簡潔有力(80-120字)", "詳細描述(200-300字)", "自訂"]
            }
        ]
        
        # 根據主題添加特定問題
        topic_specific_questions = {
            "美妝保養": [
                {
                    "id": "product_focus",
                    "question": "產品資訊重點？",
                    "options": ["強調效果體驗", "突出價格優惠", "自訂"]
                }
            ],
            "商品推廣": [
                {
                    "id": "promotion_focus",
                    "question": "推廣重點？",
                    "options": ["突出產品特色", "強調優惠價格", "自訂"]
                }
            ],
            "美食分享": [
                {
                    "id": "food_aspect",
                    "question": "美食分享重點？",
                    "options": ["味道體驗", "環境氛圍", "自訂"]
                }
            ],
            "旅遊生活": [
                {
                    "id": "travel_focus",
                    "question": "旅遊分享重點？",
                    "options": ["景點介紹", "個人體驗", "自訂"]
                }
            ],
            "時尚穿搭": [
                {
                    "id": "fashion_focus",
                    "question": "穿搭分享重點？",
                    "options": ["搭配技巧", "單品推薦", "自訂"]
                }
            ]
        }
        
        # 組合問題
        questions = base_questions.copy()
        if topic in topic_specific_questions:
            questions.extend(topic_specific_questions[topic])
        
        # 添加通用的特殊要求問題
        questions.append({
            "id": "special_requirements",
            "question": "有什麼特殊要求嗎？",
            "options": ["需要加入 hashtag", "避免提及價格", "自訂"]
        })
        
        return {
            "need_clarification": True,
            "questions": questions[:5]  # 限制最多5個問題
        }

# 全域 agent 實例
clarification_agent = ClarificationAgent()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "clarification-agent",
        "version": "1.0.0"
    }

@app.post("/clarify", response_model=ClarifyResponse)
async def clarify_request(request: ClarifyRequest):
    """處理澄清請求"""
    try:
        result = await clarification_agent.generate_clarification(request.text)
        
        return ClarifyResponse(
            session_id=request.session_id,
            need_clarification=result["need_clarification"],
            questions=result["questions"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"澄清處理失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
else:
    # 在服務模式下掛載 MCP 註冊與心跳
    @app.on_event("startup")
    async def _mcp_startup():
        import os
        port = int(os.getenv("AGENT_PORT", 8004))
        init_mcp_client(agent_name="clarification", agent_role="clarification", agent_port=port)
        await agent_startup(capabilities={"clarify": True}, metadata={"service": "clarification"}, heartbeat_interval=30)

    @app.on_event("shutdown")
    async def _mcp_shutdown():
        await agent_shutdown()