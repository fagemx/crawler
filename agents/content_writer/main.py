#!/usr/bin/env python3
"""
Content Writer Agent - 內容生成服務
根據模板和用戶需求生成最終貼文
"""

import json
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.llm_manager import get_llm_manager, chat_completion
from common.settings import get_settings

app = FastAPI(title="Content Writer Agent", version="1.0.0")

class ContentRequest(BaseModel):
    session_id: str
    template_style: str  # "narrative" or "line_break_list"
    requirements_json: Dict[str, Any]  # 完整的 JSON 結構
    original_text: str

class ContentResponse(BaseModel):
    session_id: str
    final_post: str
    template_used: str

class ContentWriterAgent:
    def __init__(self):
        self.settings = get_settings()
        self.llm_manager = get_llm_manager()
        self.templates = self.load_templates()
    
    def load_templates(self) -> Dict[str, Any]:
        """載入貼文模板"""
        try:
            # 嘗試從配置文件載入
            import os
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "post_templates.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    templates_list = json.load(f)
                    return {template["style"]: template for template in templates_list}
        except Exception as e:
            print(f"載入模板配置失敗，使用預設模板: {e}")
        
        # 預設模板
        return {
            "narrative": {
                "style": "narrative",
                "description": "自然敘事、語句連貫、段落以複合句為主，較少分行。",
                "main_topic": "日常保養＋新品分享",
                "summary": "以自然語句連貫介紹新品及個人經驗，資訊整合於長句，語感流暢。",
                "paragraph_count_range": [1, 2],
                "sentence_length": {
                    "short_sentence_ratio": 0.2,
                    "short_sentence_word_range": [8, 15],
                    "long_sentence_ratio": 0.8,
                    "long_sentence_word_range": [16, 35]
                },
                "sentence_connection": "多用逗號、連詞或破折號將細節串成一到兩句長句，語感流暢、自然銜接。",
                "minimal_cues": [
                    "開頭交代分享動機或背景，主句結構明顯。",
                    "產品資訊（名稱、價格、評價等）融合在長句裡，用逗號或破折號隔開。",
                    "評論或推薦語在最後，通常作為收尾。",
                    "全段多為一兩句即可，不宜分行。"
                ],
                "few_shot": [
                    "最近新入手一瓶保濕精華液，容量30ml，現場體驗價只要980元，覺得性價比超高。",
                    "今天特地來和大家推薦這款清爽型化妝水，瓶身設計很有質感，價格也很親民。"
                ],
                "custom_user_requirements": []
            },
            "line_break_list": {
                "style": "line_break_list",
                "description": "單句分行，每個重點獨立成一行，語氣更口語或帶強調感。",
                "main_topic": "日常保養＋新品分享",
                "summary": "分行條列，每行一重點，語氣口語，強調重點細節。",
                "paragraph_count_range": [1, 2],
                "sentence_length": {
                    "short_sentence_ratio": 0.9,
                    "short_sentence_word_range": [6, 15],
                    "long_sentence_ratio": 0.1,
                    "long_sentence_word_range": [16, 22]
                },
                "sentence_connection": "每個重點獨立成句，不用連接詞、不用逗號，各行之間只用換行分隔。",
                "minimal_cues": [
                    "每句話只帶一個重點，不合併資訊。",
                    "產品名、價格、評價等全部單獨一行。",
                    "感受或評價獨立成行，最後一句常見感嘆或強調。",
                    "允許開頭短句，也可全段分行。"
                ],
                "few_shot": [
                    "新產品入手\\n清透保濕精華液\\n30ml\\n體驗價980元\\n很推！",
                    "剛收到這款卸妝水\\n大容量500ml\\n溫和無負擔\\n用過就回不去"
                ],
                "custom_user_requirements": []
            }
        }
    
    def build_generation_prompt(self, final_requirements: Dict[str, Any], original_text: str) -> str:
        """構建內容生成提示詞"""
        requirements_json = json.dumps(final_requirements, ensure_ascii=False, indent=2)
        
        prompt = f"""你是一位專業的社群寫手，請根據以下完整的需求結構生成一篇社交媒體貼文。

用戶原始需求: "{original_text}"

完整需求結構:
{requirements_json}

請特別注意：
1. 嚴格遵守 custom_user_requirements 中的所有要求
2. 按照 sentence_length 的比例控制句子長度
3. 遵循 minimal_cues 中的寫作指導
4. 參考 few_shot 中的範例風格
5. 控制段落數量在 paragraph_count_range 範圍內

生成的貼文應該：
- 自然流暢，符合社交媒體風格
- 完全滿足用戶的特殊需求
- 不要提及任何指令或模板相關的文字
- 直接輸出貼文內容，不需要額外說明

請開始生成貼文："""
        
        return prompt
    
    async def generate_content(self, template_style: str, requirements_json: Dict[str, Any], original_text: str) -> str:
        """根據完整 JSON 結構生成內容"""
        try:
            # 獲取基礎模板
            base_template = self.templates.get(template_style, self.templates["narrative"])
            
            # 合併基礎模板和用戶需求
            final_requirements = base_template.copy()
            final_requirements.update(requirements_json)
            
            # 確保風格一致
            final_requirements["style"] = template_style
            
            prompt = self.build_generation_prompt(final_requirements, original_text)
            
            messages = [
                {"role": "system", "content": "你是一位專業的社群寫手，擅長根據結構化需求創作精準的社交媒體內容。"},
                {"role": "user", "content": prompt}
            ]
            
            # 使用新的 LLM 管理器
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",  # 明確指定模型
                temperature=0.7,
                max_tokens=800,
                provider="gemini"
            )
            
            return content.strip()
                
        except Exception as e:
            print(f"內容生成失敗: {e}")
            return f"抱歉，內容生成遇到問題。原始需求：{original_text}"

# 全域 agent 實例
content_writer = ContentWriterAgent()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "content-writer-agent",
        "version": "1.0.0"
    }

@app.post("/generate", response_model=ContentResponse)
async def generate_content(request: ContentRequest):
    """生成內容"""
    try:
        final_post = await content_writer.generate_content(
            template_style=request.template_style,
            requirements_json=request.requirements_json,
            original_text=request.original_text
        )
        
        return ContentResponse(
            session_id=request.session_id,
            final_post=final_post,
            template_used=request.template_style
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"內容生成失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)