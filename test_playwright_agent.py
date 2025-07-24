import asyncio
import json
import httpx
from pathlib import Path

# --- 測試設定 ---
# 1. 要爬取的目標使用者名稱 (不含 @)
TARGET_USERNAME = "natgeo"  # <--- 在這裡修改您想爬取的帳號

# 2. 要爬取的最大貼文數量
MAX_POSTS_TO_FETCH = 50  # <--- 在這裡修改您想爬取的數量

# 3. Playwright Crawler Agent 的 API 端點
#    請確保您的 docker-compose 正在運行，且端口號正確
AGENT_URL = "http://localhost:8006/v1/playwright/crawl"

# 4. 認證檔案的路徑 (由 save_auth.py 產生)
from agents.playwright_crawler.config import get_auth_file_path
AUTH_FILE_PATH = get_auth_file_path(from_project_root=True)


async def main():
    """
    測試 Playwright Crawler Agent 的主函數。
    """
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 '{AUTH_FILE_PATH}'。")
        print("   請先執行 'python tests/threads_fetch/save_auth.py' 來產生此檔案。")
        return

    print(f"🔧 準備測試 Playwright Crawler Agent...")
    print(f"   - 目標帳號: @{TARGET_USERNAME}")
    print(f"   - 預計爬取: {MAX_POSTS_TO_FETCH} 則貼文")
    print(f"   - Agent 端點: {AGENT_URL}")

    # 讀取 auth.json 的內容
    try:
        with open(AUTH_FILE_PATH, "r", encoding="utf-8") as f:
            auth_content = json.load(f)
    except Exception as e:
        print(f"❌ 讀取或解析 '{AUTH_FILE_PATH}' 失敗: {e}")
        return

    # 準備 API 請求的 payload
    payload = {
        "username": TARGET_USERNAME,
        "max_posts": MAX_POSTS_TO_FETCH,
        "auth_json_content": auth_content,
    }

    print("\n🚀 發送 API 請求至 Agent...")
    
    try:
        timeout = httpx.Timeout(300.0)  # 設定一個較長的超時時間 (300秒)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", AGENT_URL, json=payload) as response:
                if response.status_code != 200:
                    print(f"❌ API 請求失敗，狀態碼: {response.status_code}")
                    async for chunk in response.aiter_text():
                        print(chunk)
                    return

                print("✅ 連線成功，開始接收串流事件...\n")
                
                final_data = None
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            event_data = json.loads(line[5:])
                            
                            # 檢查事件資料是否為字典
                            if not isinstance(event_data, dict):
                                print(f"   [警告] 收到非字典格式的事件資料: {type(event_data)} - {event_data}")
                                continue
                            
                            # 美化輸出
                            event_type = event_data.get("response_type", "unknown")
                            content = event_data.get("content", {})
                            
                            if event_type == "status":
                                # status 類型的 content 應該是字典
                                if isinstance(content, dict):
                                    state = content.get('status', 'N/A')
                                    message = content.get('message', '')
                                    progress = content.get('progress', 0)
                                    print(f"   [狀態更新] {state}: {message} ({progress:.0%})")
                                else:
                                    print(f"   [狀態更新] 格式異常: {content}")
                            elif event_type == "text":
                                # text 類型的 content 應該是字串
                                if isinstance(content, str):
                                    print(f"   [日誌訊息] {content}")
                                else:
                                    print(f"   [日誌訊息] 格式異常: {content}")
                            elif event_type == "data" and event_data.get("is_task_complete"):
                                print("\n✅ 任務完成，接收到最終資料。")
                                final_data = content
                                break
                            elif event_type == "error":
                                # error 類型的 content 應該是字典
                                if isinstance(content, dict):
                                    error_message = content.get('error', '未知錯誤')
                                    print(f"   [錯誤] {error_message}")
                                elif isinstance(content, str):
                                    print(f"   [錯誤] {content}")
                                else:
                                    print(f"   [錯誤] 格式異常: {content}")
                                break

                        except json.JSONDecodeError:
                            print(f"   [警告] 無法解析收到的事件: {line}")
                        except Exception as e:
                            print(f"   [錯誤] 處理事件時發生錯誤: {e}")
                            print(f"   [除錯] 原始事件行: {line}")
                            break

        if final_data:
            # final_data 就是 PostMetricsBatch 的內容
            posts_count = len(final_data.get("posts", []))
            print("\n--- 測試結果摘要 ---")
            print(f"批次 ID: {final_data.get('batch_id')}")
            print(f"使用者: {final_data.get('username')}")
            print(f"處理階段: {final_data.get('processing_stage')}")
            print(f"總計數量: {final_data.get('total_count')}")
            print(f"成功爬取貼文數: {posts_count}")
            print("----------------------\n")
            
            # 顯示前幾則貼文的簡要資訊
            posts = final_data.get("posts", [])
            
            # 除錯：顯示第一筆貼文的完整結構
            if posts:
                print(f"--- 除錯：第一筆貼文的完整結構 ---")
                first_post = posts[0]
                print(f"所有欄位: {list(first_post.keys())}")
                print(f"完整內容: {first_post}")
                print("=" * 50)
            
            if posts:
                print("--- 前 3 則貼文預覽 ---")
                for i, post in enumerate(posts[:3]):
                    print(f"{i+1}. ID: {post.get('post_id', 'N/A')}")
                    print(f"   作者: {post.get('username', 'N/A')}")
                    print(f"   讚數: {post.get('likes_count', 0)}")
                    print(f"   留言數: {post.get('comments_count', 0)}")
                    print(f"   分享數: {post.get('reposts_count', 0)}")
                    print(f"   網址: {post.get('url', 'N/A')}")
                    print(f"   來源: {post.get('source', 'N/A')}")
                    print(f"   處理階段: {post.get('processing_stage', 'N/A')}")
                    
                    # 顯示內容預覽
                    content = post.get('content', '')
                    if content:
                        preview = content[:100] + "..." if len(content) > 100 else content
                        print(f"   內容: {preview}")
                    
                    created_at = post.get('created_at')
                    if created_at:
                        print(f"   發布時間: {created_at}")
                    print()
        else:
            print("\n--- 測試未收到最終資料 ---")

    except httpx.ConnectError as e:
        print(f"\n❌ 連線錯誤: 無法連線至 {AGENT_URL}。")
        print(f"   請確認您的 Docker 容器是否正在運行，且端口映射正確。({e})")
    except Exception as e:
        print(f"\n❌ 執行測試時發生未預期的錯誤: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 