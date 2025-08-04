"""
Playwright 爬蟲工具函式
包含數據轉換、JSON保存、日誌處理等輔助功能
"""

import json
import time
import tempfile
import shutil
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


class PlaywrightUtils:
    """Playwright 爬蟲工具類"""
    
    @staticmethod
    def write_progress(path: str, data: Dict[str, Any]):
        """線程安全寫入進度文件"""
        old: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                pass

        # 合併邏輯
        stage_priority = {
            "initialization": 0, "fetch_start": 1, "post_parsed": 2,
            "batch_parsed": 3, "fill_views_start": 4, "fill_views_completed": 5,
            "api_completed": 6, "completed": 7, "error": 8
        }
        old_stage = old.get("stage", "")
        new_stage = data.get("stage", old_stage)
        if stage_priority.get(new_stage, 0) < stage_priority.get(old_stage, 0):
            data.pop("stage", None)

        if "progress" not in data and "progress" in old:
            data["progress"] = old["progress"]
        if "current_work" not in data and "current_work" in old:
            data["current_work"] = old["current_work"]

        merged = {**old, **data, "timestamp": time.time()}

        # 先寫到 tmp，再 atomic rename
        dir_ = os.path.dirname(path)
        os.makedirs(dir_, exist_ok=True)
        
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, dir=dir_, suffix=".tmp", encoding='utf-8') as tmp:
                json.dump(merged, tmp, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name
            
            shutil.move(tmp_path, path)
        except Exception as e:
            print(f"❌ 寫入進度文件失敗: {e}")

    @staticmethod
    def read_progress(path: str) -> Dict[str, Any]:
        """讀取進度文件"""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    
    @staticmethod
    def convert_playwright_results(playwright_data: Dict[str, Any]) -> Dict[str, Any]:
        """轉換 Playwright API 結果為專用格式"""
        posts = playwright_data.get("posts", [])
        username = playwright_data.get("username", "")
        
        # 轉換為 Playwright 專用格式
        converted_results = []
        for post in posts:
            # 檢查數據格式並轉換
            result = {
                "post_id": post.get("post_id", ""),
                "url": post.get("url", ""),
                "content": post.get("content", ""),
                "views": str(post.get("views_count", "") or ""),
                "likes": str(post.get("likes_count", "") or ""),
                "comments": str(post.get("comments_count", "") or ""),
                "reposts": str(post.get("reposts_count", "") or ""),
                "shares": str(post.get("shares_count", "") or ""),
                "source": "playwright_agent",
                "crawler_type": "playwright",  # 標記爬蟲類型
                "success": True,
                "has_views": bool(post.get("views_count")),
                "has_content": bool(post.get("content")),
                "has_likes": bool(post.get("likes_count")),
                "has_comments": bool(post.get("comments_count")),
                "has_reposts": bool(post.get("reposts_count")),
                "has_shares": bool(post.get("shares_count")),
                "content_length": len(post.get("content", "")),
                "extracted_at": datetime.now().isoformat(),
                "created_at": post.get("created_at", ""),
                "username": username
            }
            converted_results.append(result)
        
        # 生成唯一ID（時間戳 + 隨機字符）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # 包裝為 Playwright 專用結構
        return {
            "crawl_id": f"{timestamp}_{unique_id}",
            "timestamp": datetime.now().isoformat(),
            "target_username": username,
            "crawler_type": "playwright",
            "max_posts": len(posts),
            "total_processed": len(posts),
            "api_success_count": len(posts),
            "api_failure_count": 0,
            "overall_success_rate": 100.0 if posts else 0.0,
            "timing": {
                "total_time": 0,  # Playwright API 不提供詳細計時
                "url_collection_time": 0,
                "content_extraction_time": 0
            },
            "results": converted_results,
            "source": "playwright_agent",
            "database_saved": False,  # 將在保存後更新
            "database_saved_count": 0
        }
    
    @staticmethod
    def save_json_results(results_data: Dict[str, Any]) -> Path:
        """保存結果為JSON文件，使用指定格式"""
        try:
            # 創建 playwright_results 目錄
            results_dir = Path("playwright_results")
            results_dir.mkdir(exist_ok=True)
            
            # 生成文件名：crawl_data_20250803_121452_934d52b1.json
            crawl_id = results_data.get("crawl_id", "unknown")
            filename = f"crawl_data_{crawl_id}.json"
            json_file_path = results_dir / filename
            
            # 保存JSON文件
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(results_data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 結果已保存: {json_file_path}")
            return json_file_path
            
        except Exception as e:
            print(f"⚠️ 保存JSON文件失敗: {e}")
            return None
    
    @staticmethod
    def parse_number_safe(value):
        """安全解析數字字符串"""
        try:
            if not value or value == 'N/A':
                return None
            # 移除非數字字符（除了小數點）
            clean_value = str(value).replace(',', '').replace(' ', '')
            if 'K' in clean_value:
                return int(float(clean_value.replace('K', '')) * 1000)
            elif 'M' in clean_value:
                return int(float(clean_value.replace('M', '')) * 1000000)
            elif 'B' in clean_value:
                return int(float(clean_value.replace('B', '')) * 1000000000)
            else:
                return int(float(clean_value))
        except:
            return None