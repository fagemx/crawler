#!/usr/bin/env python3
"""
Form API - 表單處理服務
處理問卷展示和答案收集
"""

import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.redis_client import get_async_redis_client

app = FastAPI(title="Form API", version="1.0.0")

class FormQuestions(BaseModel):
    session_id: str
    questions: list

class FormAnswers(BaseModel):
    answers: Dict[str, str]

class FormAPI:
    def __init__(self):
        self.redis_client = None
        
    async def get_redis(self):
        """獲取 Redis 客戶端"""
        if not self.redis_client:
            self.redis_client = await get_async_redis_client()
        return self.redis_client
    
    async def store_questions(self, session_id: str, questions: list):
        """存儲問卷到 Redis"""
        redis = await self.get_redis()
        key = f"form:questions:{session_id}"
        await redis.set(key, json.dumps(questions), ex=3600)  # 1小時過期
    
    async def get_questions(self, session_id: str) -> Optional[list]:
        """從 Redis 獲取問卷"""
        redis = await self.get_redis()
        key = f"form:questions:{session_id}"
        data = await redis.get(key)
        return json.loads(data) if data else None
    
    async def store_answers(self, session_id: str, answers: Dict[str, str]):
        """存儲答案到 Redis"""
        redis = await self.get_redis()
        key = f"form:answers:{session_id}"
        await redis.set(key, json.dumps(answers), ex=3600)  # 1小時過期

# 全域 API 實例
form_api = FormAPI()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "form-api",
        "version": "1.0.0"
    }

@app.post("/form/{session_id}/questions")
async def push_questions(session_id: str, questions: FormQuestions):
    """接收並存儲問卷（由 orchestrator 調用）"""
    try:
        await form_api.store_questions(session_id, questions.questions)
        return {"status": "success", "message": "問卷已存儲"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"存儲問卷失敗: {str(e)}")

@app.get("/form/{session_id}")
async def get_form(session_id: str):
    """獲取問卷（前端調用）"""
    try:
        questions = await form_api.get_questions(session_id)
        if not questions:
            raise HTTPException(status_code=404, detail="問卷不存在或已過期")
        
        return {
            "session_id": session_id,
            "questions": questions
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取問卷失敗: {str(e)}")

@app.post("/form/{session_id}/answer")
async def submit_answers(session_id: str, answers: FormAnswers):
    """提交答案（前端調用）"""
    try:
        # 1. 保存答案到 Redis
        await form_api.store_answers(session_id, answers.answers)
        
        # 2. 自動調用 Orchestrator 處理答案
        import os
        orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{orchestrator_url}/answers",
                    json={
                        "session_id": session_id,
                        "answers": answers.answers
                    },
                    timeout=60
                )
                response.raise_for_status()
                orchestrator_result = response.json()
                
                return {
                    "status": "success", 
                    "message": "答案已提交並處理完成",
                    "session_id": session_id,
                    "result": orchestrator_result
                }
            except Exception as e:
                print(f"調用 Orchestrator 失敗: {e}")
                return {
                    "status": "partial_success", 
                    "message": "答案已保存，但後續處理失敗",
                    "session_id": session_id,
                    "error": str(e)
                }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交答案失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)