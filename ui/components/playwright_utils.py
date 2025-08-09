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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any


class PlaywrightUtils:
    """Playwright 爬蟲工具類"""
    
    @staticmethod
    def convert_to_taipei_time(datetime_str: str) -> datetime:
        """將各種格式的日期時間字符串轉換為台北時區的 datetime 物件（無時區信息）"""
        try:
            if not datetime_str:
                return None
            
            # 清理輸入字符串
            datetime_str = str(datetime_str).strip()
            
            # 嘗試多種時間格式解析
            dt = None
            
            # 方法1：嘗試 ISO 格式
            try:
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            except ValueError:
                pass
            
            # 方法2：嘗試標準格式（空格分隔）
            if dt is None:
                try:
                    # 處理 "YYYY-MM-DD HH:MM:SS" 格式
                    if len(datetime_str) == 19 and ' ' in datetime_str:
                        dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    # 處理 "YYYY-MM-DD HH:MM:SS.ffffff" 格式
                    elif '.' in datetime_str and ' ' in datetime_str:
                        # 截取到微秒最多6位
                        if '.' in datetime_str:
                            base_part, micro_part = datetime_str.split('.')
                            micro_part = micro_part[:6].ljust(6, '0')  # 確保6位微秒
                            datetime_str = f"{base_part}.{micro_part}"
                        dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    pass
            
            # 方法3：嘗試替換T為空格後解析
            if dt is None:
                try:
                    modified_str = datetime_str.replace('T', ' ')
                    if '.' in modified_str:
                        dt = datetime.strptime(modified_str, '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        dt = datetime.strptime(modified_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
            
            # 如果所有方法都失敗
            if dt is None:
                print(f"⚠️ 無法解析時間格式: {datetime_str}")
                return None
            
            # 如果解析的時間沒有時區信息，假設它是UTC時間
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            # 轉換為台北時區 (UTC+8)
            taipei_tz = timezone(timedelta(hours=8))
            taipei_dt = dt.astimezone(taipei_tz)
            
            # 返回無時區信息的台北時間，用於資料庫存儲
            return taipei_dt.replace(tzinfo=None)
            
        except Exception as e:
            print(f"⚠️ 時間轉換失敗 {datetime_str}: {e}")
            return None
    
    @staticmethod
    def get_current_taipei_time() -> datetime:
        """獲取當前台北時間（無時區信息）"""
        taipei_tz = timezone(timedelta(hours=8))
        return datetime.now(taipei_tz).replace(tzinfo=None)
    
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
        # 🔥 修復：支援兩種格式 - API 響應用 "posts"，Redis final_data 用 "results"
        posts = playwright_data.get("posts", []) or playwright_data.get("results", [])
        
        # 🔧 修復：從多個來源獲取正確的用戶名稱
        username = (playwright_data.get("username", "") or 
                   playwright_data.get("target_username", "") or
                   (posts[0].get("username", "") if posts else ""))
        
        # 轉換為 Playwright 專用格式
        converted_results = []
        for post in posts:
            # 檢查數據格式並轉換 - 保持所有原始數據
            result = {
                "post_id": post.get("post_id", ""),
                "url": post.get("url", ""),
                "content": post.get("content", ""),
                # 數量欄位（保持原始數值格式）
                "views_count": post.get("views_count", 0),
                "likes_count": post.get("likes_count", 0),
                "comments_count": post.get("comments_count", 0),
                "reposts_count": post.get("reposts_count", 0),
                "shares_count": post.get("shares_count", 0),
                # 向後兼容的字符串格式
                "views": str(post.get("views_count", "") or ""),
                "likes": str(post.get("likes_count", "") or ""),
                "comments": str(post.get("comments_count", "") or ""),
                "reposts": str(post.get("reposts_count", "") or ""),
                "shares": str(post.get("shares_count", "") or ""),
                # 計算分數
                "calculated_score": post.get("calculated_score", 0),
                # 時間欄位
                "created_at": post.get("created_at", ""),
                "post_published_at": post.get("post_published_at", ""),
                # 陣列欄位
                "tags": post.get("tags", []),
                "images": post.get("images", []),
                "videos": post.get("videos", []),
                # 元數據
                "source": "playwright_agent",
                "crawler_type": "playwright",
                "success": True,
                "has_views": bool(post.get("views_count")),
                "has_content": bool(post.get("content")),
                "has_likes": bool(post.get("likes_count")),
                "has_comments": bool(post.get("comments_count")),
                "has_reposts": bool(post.get("reposts_count")),
                "has_shares": bool(post.get("shares_count")),
                "content_length": len(post.get("content", "")),
                "extracted_at": PlaywrightUtils.get_current_taipei_time().isoformat(),
                "username": post.get("username", "") or username  # 🔧 修復：優先使用貼文中的username，回退到整體username
            }
            converted_results.append(result)
        
        # 生成唯一ID（時間戳 + 隨機字符）
        timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # 包裝為 Playwright 專用結構
        return {
            "crawl_id": f"{timestamp}_{unique_id}",
            "timestamp": PlaywrightUtils.get_current_taipei_time().isoformat(),
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

    # -------------------- 去重工具：顯示/存前防禦性守門 --------------------
    @staticmethod
    def _normalize_content(text: str) -> str:
        """輕度正規化 content：去頭尾空白並壓縮中間空白為單一空格"""
        if not isinstance(text, str):
            return ""
        # 去頭尾空白，並將連續空白壓縮為單一空格
        return " ".join(text.strip().split())

    @staticmethod
    def deduplicate_results_by_content_keep_max_views(results_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        防禦性守門：依據「相同 content、不同 post_id → 保留 views 較高者」過濾。
        - 只在 content 非空時才參與同組比較
        - 比較主鍵：同 (username, normalized_content)
        - views 比較：優先使用 views_count，回退解析 views 字串
        - 平手時以 likes_count 作為次序，仍平手則保留先到者

        參數:
            results_data: 具有 key "results" 的字典結構
        回傳:
            新的 results_data（淺複製），其中 "results" 已過濾
        """
        try:
            results_list = list(results_data.get("results", []) or [])
            if not results_list:
                return results_data

            target_username = results_data.get("target_username", "")

            # 以 (username, normalized_content) 分組
            groups = {}
            singles = []

            for item in results_list:
                content = item.get("content") or ""
                normalized = PlaywrightUtils._normalize_content(content)
                # 僅對非空內容進行分組去重
                if not normalized:
                    singles.append(item)
                    continue

                username = item.get("username") or target_username or ""
                key = (username, normalized)
                groups.setdefault(key, []).append(item)

            deduped = []

            # 保留每組中 views 最大者
            def views_of(x: Dict[str, Any]) -> int:
                v = x.get("views_count")
                if v is None or v == "":
                    v = x.get("views")
                parsed = PlaywrightUtils.parse_number_safe(v)
                return int(parsed or 0)

            def likes_of(x: Dict[str, Any]) -> int:
                l = x.get("likes_count")
                if l is None or l == "":
                    l = x.get("likes")
                parsed = PlaywrightUtils.parse_number_safe(l)
                return int(parsed or 0)

            dropped = []
            for _, items in groups.items():
                if len(items) == 1:
                    deduped.append(items[0])
                else:
                    # 先以 views 由大到小排序，平手再以 likes 由大到小
                    items_sorted = sorted(
                        items,
                        key=lambda x: (views_of(x), likes_of(x)),
                        reverse=True,
                    )
                    deduped.append(items_sorted[0])
                    dropped.extend(items_sorted[1:])

            # 合併單筆（無內容或未分組）+ 去重後結果
            final_results = singles + deduped

            # 回寫到新的資料結構，避免外部引用被就地修改
            new_data = dict(results_data)
            new_data["results"] = final_results
            # 記錄被丟棄的清單（作為增量跳過的標記用途）
            if dropped:
                new_data["dedup_filtered"] = [
                    {
                        "post_id": x.get("post_id", ""),
                        "url": x.get("url", ""),
                        "username": x.get("username", "") or target_username,
                        "views_count": views_of(x),
                        "likes_count": likes_of(x),
                        "content": "",  # 不保存內容
                        "source": "playwright_dedup_filtered",
                    }
                    for x in dropped
                    if x and (x.get("post_id") or x.get("url"))
                ]
            # 若有統計欄位，順便更新
            new_data["total_processed"] = len(final_results)
            new_data["api_success_count"] = len(final_results)
            return new_data
        except Exception:
            # 出錯則返回原資料，避免中斷主流程
            return results_data