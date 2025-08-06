"""
Playwright SSE 處理器
負責SSE連接、事件監聽和進度處理
"""

import json
import threading
import time
import requests
import asyncio
import httpx
from typing import Dict, Any, Callable
from .playwright_utils import PlaywrightUtils


class PlaywrightSSEHandler:
    """Playwright SSE 事件處理器"""
    
    def __init__(self, sse_url: str, agent_url: str):
        self.sse_url = sse_url
        self.agent_url = agent_url
        self.log_callback = None
        self.progress_callback = None
    
    def set_log_callback(self, callback: Callable[[str], None]):
        """設置日誌回調函數"""
        self.log_callback = callback
    
    def set_progress_callback(self, callback: Callable[[float, str, str], None]):
        """設置進度回調函數 (progress, stage, log_message)"""
        self.progress_callback = callback
    
    def _log(self, message: str):
        """記錄日誌（線程安全）"""
        print(message)  # 先 print 確保能在終端看到
        # 不直接調用回調，而是將日誌信息寫入進度文件
        # 這樣主線程可以讀取並顯示日誌
    
    def sse_listener(self, task_id: str, progfile: str):
        """SSE 事件監聽線程（完全照搬原版邏輯）"""
        url = f"{self.sse_url}/{task_id}"
        self._log(f"🔥 SSE監聽啟動: {url}")
        
        try:
            with requests.get(url, stream=True, timeout=1800) as response:  # 30分鐘超時，支援大型任務
                print(f"🔥 SSE連接成功，狀態碼: {response.status_code}")
                
                current_cnt = 0
                total_cnt = None      # 第一次拿到再放進來
                for line in response.iter_lines():
                    if line and line.startswith(b"data:"):
                        try:
                            data = json.loads(line[5:].decode().strip())
                            stage = data.get('stage', 'unknown')
                            print(f"🔥 收到SSE事件: {stage}")
                            self._log(f"🔥 收到SSE事件: {stage}")
                            
                            # --- 通用事件處理 ---
                            # 對於所有事件，都準備一個基礎的 payload
                            payload = {'stage': stage}

                            # 提取工作描述
                            work_description = None
                            if "current_work" in data:
                                work_description = data["current_work"]
                            elif "message" in data:
                                work_description = data["message"]
                            
                            if work_description:
                                payload['current_work'] = work_description

                            # --- 針對性計算進度 (V2 - 分段權重) ---
                            PARSE_WEIGHT = 0.60   # 解析階段佔 60%
                            POST_PROCESS_W = 0.40   # 後處理佔 40%

                            if stage == "post_parsed":
                                current_cnt += 1
                                total_cnt = total_cnt or data.get("total") # 只要拿一次就好
                                
                                if total_cnt:
                                    unit_progress = min(1.0, current_cnt / total_cnt)
                                    payload['progress'] = unit_progress * PARSE_WEIGHT # 映射到 0% -> 60%
                                else:
                                    # 沒 total 時，給一個遞增但接近60%的假進度
                                    progress = min(PARSE_WEIGHT * 0.99, current_cnt * (PARSE_WEIGHT * 0.02))
                                    payload['progress'] = progress
                                payload['current_work'] = f"已解析 {current_cnt}/{total_cnt or '?'} 篇"
                                log_msg = f"📝 已解析 {current_cnt}/{total_cnt or '?'} 篇貼文"
                                self._log(log_msg)
                                # 將日誌添加到進度文件中
                                payload['log_message'] = log_msg
                                
                                # 使用進度回調更新UI
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(payload['progress'], stage, log_msg)
                                    except:
                                        pass
                            
                            elif stage == "fill_views_start":
                                payload["progress"] = PARSE_WEIGHT # 到達 60%
                                payload["current_work"] = "正在補齊瀏覽數..."
                                log_msg = "👁️ 開始補齊瀏覽數..."
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(payload["progress"], stage, log_msg)
                                    except:
                                        pass

                            elif stage == "fill_views_completed":
                                payload["progress"] = PARSE_WEIGHT + POST_PROCESS_W * 0.75 # 60% + 30% = 90%
                                payload["current_work"] = "瀏覽數已補齊，準備收尾..."
                                log_msg = "✅ 瀏覽數補齊完成，準備收尾..."
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(payload["progress"], stage, log_msg)
                                    except:
                                        pass

                            elif stage in ("completed", "api_completed"):
                                payload["progress"] = 1.0
                                if not payload.get('current_work'):
                                    payload['current_work'] = "全部完成！"
                                log_msg = "🎉 爬蟲任務全部完成！"
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(payload["progress"], stage, log_msg)
                                    except:
                                        pass

                            elif stage == "fetch_progress" and "progress" in data:
                                payload['progress'] = max(0.0, min(1.0, float(data["progress"])))
                                progress_percent = int(payload['progress'] * 100)
                                log_msg = f"📊 進度更新: {progress_percent}%"
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                            
                            elif stage == "views_fetched":
                                log_msg = "👁️ 正在獲取觀看數..."
                                if "message" in data:
                                    log_msg = f"📝 {data['message']}"
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                            
                            elif stage in ("post_start", "post_processing"):
                                if "message" in data:
                                    log_msg = f"🔄 {data['message']}"
                                    self._log(log_msg)
                                    payload['log_message'] = log_msg
                            
                            elif stage == "batch_start":
                                log_msg = "📦 開始批次處理..."
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                            
                            elif stage == "error":
                                error_msg = data.get("error", "未知錯誤")
                                log_msg = f"❌ 錯誤: {error_msg}"
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                            
                            # 捕獲其他未處理的事件
                            elif stage not in ["post_parsed", "fill_views_start", "fill_views_completed", "completed", "api_completed"]:
                                log_msg = f"🔄 {stage}: {data.get('message', '處理中...')}"
                                self._log(log_msg)
                                payload['log_message'] = log_msg
                            
                            # 無論哪種事件，都用一個 write 完成
                            PlaywrightUtils.write_progress(progfile, payload)
                            
                            # 檢查是否完成
                            if stage in ("completed", "error"):
                                print(f"🔥 SSE監聽結束: {stage}")
                                break
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON解析失敗: {e}")
                            continue
                            
        except Exception as e:
            self._log(f"❌ SSE連接失敗: {e}")
            PlaywrightUtils.write_progress(progfile, {
                "stage": "error",
                "error": f"SSE連接失敗: {str(e)}",
                "status": "error"
            })
    
    async def execute_async_api_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """異步發送API請求（不等待完成）"""
        try:
            timeout = httpx.Timeout(1800.0)  # 30分鐘超時，支援大型任務
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                self._log("🚀 已發送異步API請求，等待SSE回應...")
                
                # 發送請求但在背景執行
                response = await client.post(self.agent_url, json=payload)
                
                if response.status_code != 200:
                    self._log(f"❌ API 請求失敗，狀態碼: {response.status_code}")
                    self._log(f"錯誤內容: {response.text}")
                    return None
                
                # 解析響應
                try:
                    final_data = response.json()
                    self._log("✅ API請求成功完成！")
                    return final_data
                except json.JSONDecodeError as e:
                    self._log(f"❌ 無法解析響應 JSON: {e}")
                    return None
                    
        except httpx.TimeoutException:
            self._log("❌ API請求超時（10分鐘）")
            return None
        except Exception as e:
            self._log(f"❌ API請求錯誤: {e}")
            return None
    
    def start_sse_listener(self, task_id: str, progfile: str):
        """啟動SSE監聽線程"""
        sse_thread = threading.Thread(
            target=self.sse_listener,
            args=(task_id, progfile),
            daemon=True
        )
        sse_thread.start()
        return sse_thread