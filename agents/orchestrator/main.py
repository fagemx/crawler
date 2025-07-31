#!/usr/bin/env python3
"""
Orchestrator Agent - 總協調器
協調整個澄清 → 表單 → 生成流程
"""

import json
import uuid
import httpx
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.redis_client import get_async_redis_client
from common.settings import get_settings
from common.nats_client import get_nats_client

app = FastAPI(title="Orchestrator Agent", version="1.0.0")

class UserRequest(BaseModel):
    text: str
    session_id: str = None

class UserAnswers(BaseModel):
    session_id: str
    answers: Dict[str, str]

class OrchestratorAgent:
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = None
        
    async def get_redis(self):
        """獲取 Redis 客戶端"""
        if not self.redis_client:
            self.redis_client = await get_async_redis_client()
        return self.redis_client
    
    async def call_clarification_agent(self, session_id: str, text: str) -> Dict[str, Any]:
        """調用澄清代理"""
        async with httpx.AsyncClient() as client:
            clarification_url = f"{self.settings.service_urls.clarification_url}/clarify"
            response = await client.post(
                clarification_url,
                json={"session_id": session_id, "text": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
    
    async def call_form_api(self, session_id: str, questions: List[Dict[str, Any]]):
        """調用表單 API 存儲問卷"""
        async with httpx.AsyncClient() as client:
            form_api_url = f"{self.settings.service_urls.form_api_url}/form/{session_id}/questions"
            response = await client.post(
                form_api_url,
                json={"session_id": session_id, "questions": questions},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
    
    async def call_content_writer(self, session_id: str, template_style: str, 
                                requirements_json: Dict[str, Any], original_text: str) -> Dict[str, Any]:
        """調用內容寫手代理"""
        async with httpx.AsyncClient() as client:
            content_writer_url = f"{self.settings.service_urls.content_writer_url}/generate"
            response = await client.post(
                content_writer_url,
                json={
                    "session_id": session_id,
                    "template_style": template_style,
                    "requirements_json": requirements_json,
                    "original_text": original_text
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()
    
    def synthesize_requirements(self, original_text: str, answers: Dict[str, str]) -> Dict[str, Any]:
        """智能合成完整的 JSON 結構需求"""
        # 基礎模板結構
        requirements = {
            "post_id": str(uuid.uuid4())[:8],
            "main_topic": "用戶自訂內容",
            "summary": f"根據用戶需求生成: {original_text}",
            "paragraph_count_range": [1, 3],
            "sentence_length": {
                "short_sentence_ratio": 0.4,
                "short_sentence_word_range": [6, 15],
                "long_sentence_ratio": 0.6,
                "long_sentence_word_range": [16, 35]
            },
            "minimal_cues": [],
            "few_shot": [],
            "custom_user_requirements": []
        }
        
        # 根據答案調整結構
        custom_reqs = []
        
        # 處理風格選擇
        if "style" in answers:
            if "連貫敘事" in answers["style"]:
                requirements["sentence_length"]["short_sentence_ratio"] = 0.2
                requirements["sentence_length"]["long_sentence_ratio"] = 0.8
                requirements["minimal_cues"].append("使用連貫敘事風格，語句自然流暢銜接")
                custom_reqs.append("採用連貫敘事風格，避免過多分行")
            elif "分行條列" in answers["style"]:
                requirements["sentence_length"]["short_sentence_ratio"] = 0.9
                requirements["sentence_length"]["long_sentence_ratio"] = 0.1
                requirements["minimal_cues"].append("使用分行條列格式，每行一個重點")
                custom_reqs.append("採用分行條列格式，每個重點獨立成行")
            elif answers["style"].startswith("自訂"):
                custom_style = answers["style"].replace("自訂:", "").strip()
                if custom_style:
                    custom_reqs.append(f"風格要求: {custom_style}")
        
        # 處理語氣要求
        if "tone" in answers:
            if "親身" in answers["tone"] or "體驗" in answers["tone"]:
                custom_reqs.append("必須以親身經歷視角描述，使用第一人稱")
                requirements["minimal_cues"].append("以個人體驗角度分享，語氣親切自然")
            elif "客觀" in answers["tone"] or "介紹" in answers["tone"]:
                custom_reqs.append("使用客觀介紹語氣，提供實用資訊")
                requirements["minimal_cues"].append("客觀介紹產品特色，避免過度主觀")
            elif answers["tone"].startswith("自訂"):
                custom_tone = answers["tone"].replace("自訂:", "").strip()
                if custom_tone:
                    custom_reqs.append(f"語氣要求: {custom_tone}")
        
        # 處理長度要求
        if "length" in answers:
            if "80-120" in answers["length"] or "簡潔" in answers["length"]:
                requirements["paragraph_count_range"] = [1, 2]
                custom_reqs.append("內容簡潔有力，控制在80-120字")
            elif "200-300" in answers["length"] or "詳細" in answers["length"]:
                requirements["paragraph_count_range"] = [2, 4]
                custom_reqs.append("內容詳細豐富，約200-300字")
            elif answers["length"].startswith("自訂"):
                custom_length = answers["length"].replace("自訂:", "").strip()
                if custom_length:
                    custom_reqs.append(f"字數要求: {custom_length}")
        
        # 處理產品相關需求
        if "product_focus" in answers:
            if "效果" in answers["product_focus"]:
                custom_reqs.append("重點強調產品使用效果和體驗")
            elif "價格" in answers["product_focus"]:
                custom_reqs.append("突出價格優惠和性價比")
            elif answers["product_focus"].startswith("自訂"):
                custom_focus = answers["product_focus"].replace("自訂:", "").strip()
                if custom_focus:
                    custom_reqs.append(f"產品重點: {custom_focus}")
        
        # 處理特殊要求
        if "special_requirements" in answers:
            if "hashtag" in answers["special_requirements"]:
                custom_reqs.append("文末必須加入相關 hashtag")
            elif "避免價格" in answers["special_requirements"]:
                custom_reqs.append("禁止提及具體價格資訊")
            elif answers["special_requirements"].startswith("自訂"):
                custom_special = answers["special_requirements"].replace("自訂:", "").strip()
                if custom_special:
                    custom_reqs.append(f"特殊要求: {custom_special}")
        
        # 從原始文本中提取額外需求
        original_lower = original_text.lower()
        if "打折" in original_text or "優惠" in original_text:
            custom_reqs.append("必須提及優惠或折扣資訊")
        if "新品" in original_text:
            custom_reqs.append("強調新品上市的特色")
        if "簡單" in original_text:
            custom_reqs.append("語言表達簡潔明瞭")
        
        # 處理其他自訂答案
        for key, value in answers.items():
            if key not in ["style", "tone", "length", "product_focus", "special_requirements"]:
                if value.startswith("自訂:"):
                    custom_req = value.replace("自訂:", "").strip()
                    if custom_req:
                        custom_reqs.append(f"{key}: {custom_req}")
                else:
                    custom_reqs.append(f"{key}: {value}")
        
        # 設置 custom_user_requirements
        requirements["custom_user_requirements"] = custom_reqs
        
        return requirements
    
    async def store_session_data(self, session_id: str, data: Dict[str, Any]):
        """存儲會話數據"""
        redis = await self.get_redis()
        key = f"session:{session_id}"
        await redis.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()})
        await redis.expire(key, 3600)  # 1小時過期

# 全域 orchestrator 實例
orchestrator = OrchestratorAgent()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "orchestrator-agent",
        "version": "1.0.0"
    }

@app.post("/user")
async def handle_user_request(request: UserRequest):
    """處理用戶初始請求"""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        
        # 存儲原始請求
        await orchestrator.store_session_data(session_id, {
            "raw_input": request.text,
            "status": "clarifying"
        })
        
        # 調用澄清代理
        clarification_result = await orchestrator.call_clarification_agent(session_id, request.text)
        
        if clarification_result["need_clarification"]:
            # 需要澄清，存儲問卷到 Form API
            await orchestrator.call_form_api(session_id, clarification_result["questions"])
            
            return {
                "session_id": session_id,
                "status": "need_clarification",
                "message": "需要進一步澄清，請查看問卷",
                "form_url": f"http://localhost:8010/form/{session_id}"
            }
        else:
            # 不需要澄清，直接生成內容
            default_requirements = orchestrator.synthesize_requirements(request.text, {})
            final_post = await orchestrator.call_content_writer(
                session_id=session_id,
                template_style="narrative",  # 預設風格
                requirements_json=default_requirements,
                original_text=request.text
            )
            
            return {
                "session_id": session_id,
                "status": "completed",
                "final_post": final_post["final_post"]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理用戶請求失敗: {str(e)}")

@app.post("/answers")
async def handle_user_answers(request: UserAnswers):
    """處理用戶答案並生成最終內容"""
    try:
        # 獲取原始請求
        redis = await orchestrator.get_redis()
        session_data = await redis.hgetall(f"session:{request.session_id}")
        
        if not session_data:
            raise HTTPException(status_code=404, detail="會話不存在或已過期")
        
        original_text = session_data.get("raw_input", "")
        
        # 智能合成完整需求結構
        requirements_json = orchestrator.synthesize_requirements(original_text, request.answers)
        
        # 決定模板風格
        template_style = "narrative"  # 預設
        if "style" in request.answers:
            if "分行條列" in request.answers["style"]:
                template_style = "line_break_list"
        
        # 調用內容寫手
        content_result = await orchestrator.call_content_writer(
            session_id=request.session_id,
            template_style=template_style,
            requirements_json=requirements_json,
            original_text=original_text
        )
        
        # 更新會話狀態
        await orchestrator.store_session_data(request.session_id, {
            "status": "completed",
            "final_post": content_result["final_post"],
            "template_used": template_style,
            "requirements_json": requirements_json,
            "user_answers": request.answers
        })
        
        return {
            "session_id": request.session_id,
            "status": "completed",
            "final_post": content_result["final_post"],
            "template_used": template_style
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理用戶答案失敗: {str(e)}")

# === 新增：SSE 進度流端點 ===
@app.get("/stream/{task_id}")
async def stream_progress(task_id: str):
    """SSE 端點：流式傳輸指定 task_id 的進度更新"""
    import asyncio
    
    async def event_generator():
        """事件生成器"""
        message_queue = asyncio.Queue()
        subscription = None
        
        try:
            # 連接到 NATS 並訂閱進度頻道
            nc = await get_nats_client()
            if nc is None:
                yield f"data: {json.dumps({'error': 'NATS not available', 'task_id': task_id})}\n\n"
                return
            
            # 訊息處理器
            async def message_handler(msg):
                try:
                    data = json.loads(msg.data.decode())
                    # 只處理指定 task_id 的訊息
                    if data.get("task_id") == task_id:
                        await message_queue.put(data)
                except Exception as e:
                    print(f"處理訊息錯誤: {e}")
            
            # 訂閱進度主題
            subscription = await nc.subscribe("crawler.progress", cb=message_handler)
            
            # 發送初始連接確認
            yield f"data: {json.dumps({{'task_id': '{task_id}', 'stage': 'connected', 'message': 'SSE connection established'}})}\n\n"
            
            # 持續監聽訊息
            timeout_counter = 0
            while timeout_counter < 600:  # 10分鐘超時
                try:
                    # 等待訊息，設置短超時以保持連接活躍
                    data = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                    yield f"data: {json.dumps(data)}\n\n"
                    timeout_counter = 0  # 重置超時計數器
                    
                    # 如果收到完成或錯誤訊息，結束流
                    if data.get("stage") in ["completed", "error"]:
                        break
                        
                except asyncio.TimeoutError:
                    # 發送心跳保持連接
                    timeout_counter += 1
                    if timeout_counter % 30 == 0:  # 每30秒發送一次心跳
                        yield f"data: {json.dumps({{'task_id': '{task_id}', 'stage': 'heartbeat'}})}\n\n"
                    continue
                    
        except Exception as e:
            yield f"data: {json.dumps({{'error': str(e), 'task_id': '{task_id}'}})}\n\n"
        finally:
            # 清理訂閱
            if subscription:
                try:
                    await subscription.unsubscribe()
                except:
                    pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 相容性
        }
    )

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {"status": "healthy", "service": "Orchestrator Agent"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)