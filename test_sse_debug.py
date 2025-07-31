#!/usr/bin/env python3
"""
調試 SSE 連接問題 - 針對進度條不顯示的問題
"""

import requests
import json
import uuid
import time
from datetime import datetime

def test_sse_connection():
    """測試 SSE 連接"""
    task_id = str(uuid.uuid4())
    sse_url = f"http://localhost:8000/stream/{task_id}"
    
    print("🔍 SSE 連接調試")
    print("=" * 50)
    print(f"🆔 Task ID: {task_id}")
    print(f"🔗 SSE URL: {sse_url}")
    print("💡 建議: 在另一個終端運行 test_realtime_progress.py 來觸發爬蟲")
    print("=" * 50)
    
    try:
        response = requests.get(sse_url, stream=True, timeout=30)
        print(f"📡 響應狀態: {response.status_code}")
        print(f"📡 響應頭: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("✅ SSE 連接成功，開始監聽...")
            
            line_count = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8').strip()
                    line_count += 1
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    print(f"[{timestamp}] 第{line_count}行: '{line_str}'")
                    
                    # 按照修復後的邏輯解析
                    if line_str.startswith('data:'):
                        payload_txt = line_str.split(':', 1)[1].strip()
                        if payload_txt:
                            try:
                                data = json.loads(payload_txt)
                                print(f"  ✅ JSON 解析成功: {data}")
                                
                                # 檢查關鍵字段
                                stage = data.get('stage', 'unknown')
                                if stage == 'connected':
                                    print("  🔗 收到連接確認")
                                elif stage == 'post_parsed':
                                    progress = data.get('progress', 0)
                                    print(f"  📊 貼文解析進度: {progress:.1%}")
                                elif stage == 'completed':
                                    print("  🎉 爬取完成")
                                    break
                                elif stage == 'error':
                                    print("  ❌ 爬取錯誤")
                                    break
                                    
                            except json.JSONDecodeError as e:
                                print(f"  ❌ JSON 解析失敗: {e}")
                                print(f"     原始文本: '{payload_txt}'")
                    else:
                        print(f"  🔍 非數據行: '{line_str}'")
                    
                    # 防止無限等待
                    if line_count > 100:
                        print("⏹️ 達到行數限制，停止監聽")
                        break
                        
        else:
            print(f"❌ SSE 連接失敗: {response.status_code}")
            print(f"響應內容: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ SSE 連接超時")
    except Exception as e:
        print(f"❌ SSE 連接錯誤: {e}")

def test_curl_command():
    """顯示手動測試命令"""
    task_id = str(uuid.uuid4())
    print(f"\n💡 手動測試 SSE 命令:")
    print(f"curl -N http://localhost:8000/stream/{task_id}")
    print(f"\n💡 如果上面的命令顯示數據流，說明後端 SSE 正常")
    print(f"💡 Task ID: {task_id}")

if __name__ == "__main__":
    test_sse_connection()
    test_curl_command()