#!/usr/bin/env python3
"""
即時進度測試腳本
同時監聽 SSE 進度更新和發送 API 請求
"""

import asyncio
import aiohttp
import json
import threading
import time
from typing import Optional
import uuid
from pathlib import Path
from common.config import get_auth_file_path

class ProgressMonitor:
    def __init__(self):
        self.progress_events = []
        self.task_id = str(uuid.uuid4())
        
    async def monitor_sse_progress(self):
        """監聽 SSE 進度更新"""
        sse_url = f"http://localhost:8000/stream/{self.task_id}"
        print(f"🔗 開始監聽 SSE 進度: {sse_url}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=300)  # 5分鐘超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(sse_url) as response:
                    print(f"📡 SSE 連接狀態: {response.status}")
                    
                    if response.status != 200:
                        print(f"❌ SSE 連接失敗: {response.status}")
                        error_text = await response.text()
                        print(f"   錯誤詳情: {error_text}")
                        return
                    
                    # 逐行讀取 SSE 流
                    buffer = ""
                    async for chunk in response.content.iter_chunked(1024):
                        chunk_str = chunk.decode('utf-8')
                        buffer += chunk_str
                        
                        # 處理完整的行
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            if line.startswith('data: '):
                                data_str = line[6:]  # 移除 "data: " 前綴
                                try:
                                    data = json.loads(data_str)
                                    timestamp = time.strftime('%H:%M:%S')
                                    print(f"📈 [{timestamp}] 進度更新: {data}")
                                    self.progress_events.append(data)
                                    
                                    # 如果收到完成訊息，結束監聽
                                    if data.get('stage') in ['completed', 'error']:
                                        print("✅ 收到完成訊息，結束 SSE 監聽")
                                        return
                                except json.JSONDecodeError as e:
                                    print(f"⚠️ JSON 解析錯誤: {e}, 原始數據: {data_str}")
                        
        except asyncio.TimeoutError:
            print("⏰ SSE 連接逾時")
        except Exception as e:
            print(f"❌ SSE 監聽錯誤: {e}")
    
    async def send_crawl_request(self):
        """發送爬蟲請求"""
        await asyncio.sleep(2)  # 等待 SSE 連接建立
        
        # 讀取認證文件
        auth_file_path = get_auth_file_path(from_project_root=True)
        if not auth_file_path.exists():
            print(f"❌ 錯誤：找不到認證檔案 '{auth_file_path}'")
            return
            
        try:
            with open(auth_file_path, "r", encoding="utf-8") as f:
                auth_content = json.load(f)
        except Exception as e:
            print(f"❌ 讀取認證檔案失敗: {e}")
            return
        
        crawl_url = "http://localhost:8006/v1/playwright/crawl"
        payload = {
            "username": "natgeo",
            "max_posts": 5,
            "task_id": self.task_id,  # 使用相同的 task_id
            "auth_json_content": auth_content
        }
        
        print(f"🚀 發送爬蟲請求: {crawl_url}")
        print(f"📦 Task ID: {self.task_id}")
        print(f"🔐 認證檔案: {auth_file_path}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(crawl_url, json=payload) as response:
                    print(f"📡 API 響應狀態: {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ API 調用成功，爬取了 {len(result.get('posts', []))} 則貼文")
                    else:
                        text = await response.text()
                        print(f"❌ API 調用失敗: {text}")
        except Exception as e:
            print(f"❌ API 請求錯誤: {e}")

async def main():
    """主測試函數"""
    print("🧪 開始即時進度測試")
    print("=" * 50)
    
    monitor = ProgressMonitor()
    
    # 同時運行 SSE 監聽和 API 請求
    await asyncio.gather(
        monitor.monitor_sse_progress(),
        monitor.send_crawl_request()
    )
    
    print("\n" + "=" * 50)
    print(f"📊 測試總結:")
    print(f"   - Task ID: {monitor.task_id}")
    print(f"   - 收到進度事件: {len(monitor.progress_events)} 個")
    
    if monitor.progress_events:
        print("📈 進度事件列表:")
        for i, event in enumerate(monitor.progress_events, 1):
            stage = event.get('stage', 'unknown')
            message = event.get('message', '')
            print(f"   {i}. {stage}: {message}")
    else:
        print("⚠️ 未收到任何進度事件")

if __name__ == "__main__":
    asyncio.run(main())