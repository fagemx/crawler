"""
位置查找器 - 找出發文時間和主題tag的位置
目標貼文: https://www.threads.com/@chnyu._12/post/DM4gtYYybr-
期望數據:
- 發文時間: 2025年8月3日下午 2:36
- 主題tag: 雲林
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 目標貼文
TARGET_POST_URL = "https://www.threads.com/@chnyu._12/post/DM4gtYYybr-"
TARGET_USERNAME = "chnyu._12"
TARGET_CODE = "DM4gtYYybr-"

# 期望的數據
EXPECTED_TIME = "2025年8月3日下午 2:36"
EXPECTED_TAG = "雲林"

class TimeAndTagLocationFinder:
    """發文時間和主題tag位置查找器"""
    
    def __init__(self):
        self.captured_responses = []
        self.potential_matches = []
    
    async def intercept_all_responses(self):
        """攔截所有的 GraphQL 回應（模仿 analyze_all_graphql.py 的成功模式）"""
        print(f"🎯 攔截目標貼文的所有回應...")
        print(f"   📍 URL: {TARGET_POST_URL}")
        print(f"   ⏰ 期望時間: {EXPECTED_TIME}")
        print(f"   🏷️ 期望標籤: {EXPECTED_TAG}")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812},
                locale="zh-TW"
            )
            
            page = await context.new_page()
            
            async def response_handler(response):
                url = response.url.lower()
                if "/graphql" in url and response.status == 200:
                    friendly_name = response.request.headers.get("x-fb-friendly-name", "Unknown")
                    root_field = response.request.headers.get("x-root-field-name", "")
                    
                    print(f"   📡 {friendly_name}")
                    if root_field:
                        print(f"      🔍 Root field: {root_field}")
                    
                    try:
                        data = await response.json()
                        
                        # 分析響應結構
                        content_indicators = []
                        target_post_found = False
                        contains_yunlin = False
                        contains_time_info = False
                        
                        if "data" in data and data["data"]:
                            # 檢查是否包含目標用戶名或代碼
                            data_str = json.dumps(data, ensure_ascii=False)
                            if TARGET_USERNAME in data_str or TARGET_CODE in data_str:
                                target_post_found = True
                                content_indicators.append("HAS_TARGET_POST")
                            
                            # 檢查是否包含雲林
                            if "雲林" in data_str:
                                contains_yunlin = True
                                content_indicators.append("HAS_YUNLIN")
                            
                            # 檢查時間相關信息
                            time_keywords = ["2025", "8月", "3日", "taken_at", "timestamp", "created_time"]
                            for keyword in time_keywords:
                                if keyword in data_str:
                                    contains_time_info = True
                                    content_indicators.append(f"HAS_TIME({keyword})")
                                    break
                            
                            # 檢查其他內容指標
                            if "caption" in data_str:
                                content_indicators.append("has_caption")
                            if "like_count" in data_str:
                                content_indicators.append("has_likes")
                            if "text_post_app_info" in data_str:
                                content_indicators.append("has_text_info")
                            if len(data_str) > 10000:
                                content_indicators.append("large_response")
                        
                        indicators_text = ", ".join(content_indicators) if content_indicators else "no_content"
                        print(f"      📊 指標: {indicators_text}")
                        
                        # 記錄查詢信息
                        query_info = {
                            "friendly_name": friendly_name,
                            "root_field": root_field,
                            "url": response.url,
                            "has_target_post": target_post_found,
                            "contains_yunlin": contains_yunlin,
                            "contains_time_info": contains_time_info,
                            "content_indicators": content_indicators,
                            "request_headers": dict(response.request.headers),
                            "request_data": response.request.post_data,
                            "response_size": len(json.dumps(data)) if data else 0,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        self.captured_responses.append(query_info)
                        
                        # 如果找到目標貼文或包含雲林，詳細分析並保存
                        if target_post_found or contains_yunlin or contains_time_info:
                            print(f"      🎯 找到重要回應！")
                            
                            # 保存完整響應
                            detail_file = Path(f"time_tag_found_{friendly_name}_{datetime.now().strftime('%H%M%S')}.json")
                            with open(detail_file, 'w', encoding='utf-8') as f:
                                json.dump({
                                    "query_info": query_info,
                                    "full_response": data
                                }, f, indent=2, ensure_ascii=False)
                            print(f"      📁 詳細數據已保存: {detail_file}")
                            
                            # 立即分析時間和標籤
                            await self.analyze_time_and_tag(query_info, data)
                    
                    except Exception as e:
                        print(f"      ❌ 解析失敗: {e}")
            
            page.on("response", response_handler)
            
            # 導航到頁面
            print(f"   🌐 導航到目標頁面...")
            await page.goto(TARGET_POST_URL, wait_until="networkidle", timeout=60000)
            
            # 等待初始載入
            await asyncio.sleep(5)
            
            # 嘗試一些操作來觸發更多查詢
            print(f"   🖱️ 嘗試用戶操作...")
            
            # 滾動頁面
            await page.evaluate("window.scrollTo(0, 300)")
            await asyncio.sleep(2)
            
            # 嘗試點擊貼文區域
            try:
                await page.click('article', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            # 嘗試刷新頁面
            print(f"   🔄 刷新頁面...")
            await page.reload(wait_until="networkidle")
            await asyncio.sleep(5)
            
            # 再次滾動
            await page.evaluate("window.scrollTo(0, 600)")
            await asyncio.sleep(2)
            
            await browser.close()
        
        print(f"\n📊 攔截完成，共 {len(self.captured_responses)} 個回應")
        return len(self.captured_responses) > 0
    
    async def analyze_time_and_tag(self, query_info: Dict[str, Any], data: Dict[str, Any]):
        """分析單個回應中的時間和標籤信息"""
        friendly_name = query_info["friendly_name"]
        
        # 轉換為字符串便於搜索
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        
        # 查找時間相關的欄位
        time_patterns = [
            r'"taken_at[^"]*":\s*(\d+)',           # taken_at 時間戳
            r'"device_timestamp[^"]*":\s*(\d+)',   # device_timestamp
            r'"created_time[^"]*":\s*(\d+)',       # created_time
            r'"upload_time[^"]*":\s*(\d+)',        # upload_time
            r'"timestamp[^"]*":\s*(\d+)',          # 一般 timestamp
            r'"time[^"]*":\s*"([^"]+)"',           # 文字格式時間
            r'"date[^"]*":\s*"([^"]+)"',           # 日期格式
            r'"published_time[^"]*":\s*(\d+)',     # 發布時間
        ]
        
        # 查找標籤相關的欄位
        tag_patterns = [
            r'"hashtags?"[^:]*:\s*\[([^\]]+)\]',                    # hashtags 數組
            r'"tags?"[^:]*:\s*\[([^\]]+)\]',                        # tags 數組
            r'"location[^"]*":\s*"([^"]*雲林[^"]*)"',               # 地點包含雲林
            r'"place[^"]*":\s*"([^"]*雲林[^"]*)"',                  # place 包含雲林
            r'"location_name[^"]*":\s*"([^"]*雲林[^"]*)"',          # location_name
            r'"venue[^"]*":\s*\{[^}]*"name":\s*"([^"]*雲林[^"]*)"', # venue name
            r'"city[^"]*":\s*"([^"]*雲林[^"]*)"',                   # city
            r'"region[^"]*":\s*"([^"]*雲林[^"]*)"',                 # region
            r'"categories?"[^:]*:\s*\[([^\]]*雲林[^\]]*)\]',        # categories
        ]
        
        print(f"\n🔍 分析回應: {friendly_name}")
        
        # 查找時間
        found_times = []
        for pattern in time_patterns:
            matches = re.findall(pattern, data_str, re.IGNORECASE)
            for match in matches:
                if match.isdigit():
                    # 時間戳轉換
                    try:
                        timestamp = int(match)
                        if timestamp > 1000000000:  # 有效的時間戳
                            from datetime import datetime
                            dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%Y年%m月%d日")
                            found_times.append({
                                "pattern": pattern,
                                "raw_value": match,
                                "timestamp": timestamp,
                                "formatted": time_str,
                                "match_expected": "2025年8月3日" in time_str
                            })
                    except:
                        pass
                else:
                    # 文字格式時間
                    found_times.append({
                        "pattern": pattern,
                        "raw_value": match,
                        "timestamp": None,
                        "formatted": match,
                        "match_expected": "2025" in match or "8月" in match or "雲林" in match
                    })
        
        # 查找標籤
        found_tags = []
        for pattern in tag_patterns:
            matches = re.findall(pattern, data_str, re.IGNORECASE)
            for match in matches:
                found_tags.append({
                    "pattern": pattern,
                    "raw_value": match,
                    "match_expected": "雲林" in match
                })
        
        # 直接搜索 "雲林" 和時間相關字符串
        if "雲林" in data_str:
            print(f"   🏷️ 發現 '雲林' 字符串！")
            
            # 提取包含雲林的完整字段
            yunlin_contexts = []
            lines = data_str.split('\n')
            for i, line in enumerate(lines):
                if "雲林" in line:
                    # 獲取上下文
                    start = max(0, i-2)
                    end = min(len(lines), i+3)
                    context = '\n'.join(lines[start:end])
                    yunlin_contexts.append({
                        "line_number": i,
                        "line": line.strip(),
                        "context": context
                    })
            
            for ctx in yunlin_contexts:
                print(f"      📍 第 {ctx['line_number']} 行: {ctx['line']}")
        
        # 搜索時間相關
        time_keywords = ["2025", "8月", "3日", "下午", "2:36"]
        for keyword in time_keywords:
            if keyword in data_str:
                print(f"   ⏰ 發現時間關鍵字 '{keyword}'")
        
        # 保存有價值的發現
        if found_times or found_tags or "雲林" in data_str:
            match_info = {
                "friendly_name": friendly_name,
                "found_times": found_times,
                "found_tags": found_tags,
                "contains_yunlin": "雲林" in data_str,
                "contains_time_keywords": any(kw in data_str for kw in time_keywords),
                "payload": query_info["request_data"],
                "headers": query_info["request_headers"]
            }
            self.potential_matches.append(match_info)
    
    def save_detailed_analysis(self):
        """保存詳細分析結果"""
        if not self.captured_responses:
            print("❌ 沒有攔截到任何回應")
            return
        
        # 分析結果
        print(f"\n📊 分析結果:")
        print(f"   總查詢數: {len(self.captured_responses)}")
        
        # 找到包含目標貼文的查詢
        target_queries = [q for q in self.captured_responses if q["has_target_post"]]
        yunlin_queries = [q for q in self.captured_responses if q["contains_yunlin"]]
        time_queries = [q for q in self.captured_responses if q["contains_time_info"]]
        
        print(f"   包含目標貼文的查詢: {len(target_queries)}")
        print(f"   包含雲林的查詢: {len(yunlin_queries)}")
        print(f"   包含時間信息的查詢: {len(time_queries)}")
        
        # 顯示重要查詢
        important_queries = [q for q in self.captured_responses 
                           if q["has_target_post"] or q["contains_yunlin"] or q["contains_time_info"]]
        
        if important_queries:
            print(f"\n🎯 重要查詢:")
            for i, query in enumerate(important_queries):
                print(f"   {i+1}. {query['friendly_name']}")
                print(f"      Root field: {query['root_field']}")
                print(f"      指標: {', '.join(query['content_indicators'])}")
                print(f"      響應大小: {query['response_size']:,} 字符")
        
        # 按查詢名稱分組統計
        query_stats = {}
        for query in self.captured_responses:
            name = query["friendly_name"]
            if name not in query_stats:
                query_stats[name] = {"count": 0, "has_target": 0, "has_yunlin": 0, "has_time": 0, "avg_size": 0}
            query_stats[name]["count"] += 1
            if query["has_target_post"]:
                query_stats[name]["has_target"] += 1
            if query["contains_yunlin"]:
                query_stats[name]["has_yunlin"] += 1
            if query["contains_time_info"]:
                query_stats[name]["has_time"] += 1
            query_stats[name]["avg_size"] += query["response_size"]
        
        for name, stats in query_stats.items():
            stats["avg_size"] = stats["avg_size"] // stats["count"] if stats["count"] > 0 else 0
        
        print(f"\n📋 查詢統計:")
        for name, stats in sorted(query_stats.items(), 
                                key=lambda x: (x[1]["has_target"], x[1]["has_yunlin"], x[1]["has_time"]), 
                                reverse=True):
            print(f"   {name}:")
            print(f"      次數: {stats['count']}, 目標: {stats['has_target']}, 雲林: {stats['has_yunlin']}, 時間: {stats['has_time']}, 平均大小: {stats['avg_size']:,}")
        
        # 保存完整分析結果
        analysis_file = Path(f"time_tag_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump({
                "target_url": TARGET_POST_URL,
                "target_username": TARGET_USERNAME,
                "target_code": TARGET_CODE,
                "expected_time": EXPECTED_TIME,
                "expected_tag": EXPECTED_TAG,
                "all_queries": self.captured_responses,
                "summary": {
                    "total_queries": len(self.captured_responses),
                    "target_queries_count": len(target_queries),
                    "yunlin_queries_count": len(yunlin_queries),
                    "time_queries_count": len(time_queries),
                    "query_stats": query_stats
                }
            }, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📁 完整分析已保存: {analysis_file}")
        
        # 推薦最佳查詢
        if important_queries:
            # 選擇包含最多重要指標的查詢
            best_query = max(important_queries, key=lambda q: (
                q["has_target_post"],
                q["contains_yunlin"],
                q["contains_time_info"],
                len(q["content_indicators"])
            ))
            print(f"\n💡 推薦查詢: {best_query['friendly_name']}")
            print(f"   Root field: {best_query['root_field']}")
            print(f"   內容指標: {', '.join(best_query['content_indicators'])}")
            print(f"   響應大小: {best_query['response_size']:,} 字符")
            
            return analysis_file, best_query
        else:
            print(f"\n😞 未找到包含重要信息的查詢")
            print(f"💡 可能需要:")
            print(f"   1. 檢查貼文 URL 是否正確")
            print(f"   2. 嘗試不同的用戶操作")
            print(f"   3. 檢查認證狀態")
            
            return analysis_file, None

async def main():
    """主函數"""
    print("🎯 發文時間和主題tag位置查找器")
    print("===============================")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    finder = TimeAndTagLocationFinder()
    
    # 攔截回應
    success = await finder.intercept_all_responses()
    
    if success:
        print(f"\n📊 分析完成！")
        result = finder.save_detailed_analysis()
        
        if result:
            analysis_file, best_query = result
            if best_query:
                print(f"\n🎉 找到最佳查詢！")
                print(f"💡 請檢查保存的 JSON 檔案來找到具體的字段路徑")
            else:
                print(f"\n😞 未找到包含重要信息的查詢")
        
        print(f"\n💡 下一步:")
        print(f"   1. 檢查保存的 JSON 檔案")
        print(f"   2. 在 JSON 中搜索包含 '雲林' 和時間數據的字段")
        print(f"   3. 確定字段的完整路徑")
        print(f"   4. 整合到主爬蟲中")
    else:
        print(f"\n😞 未能攔截到相關回應")

if __name__ == "__main__":
    asyncio.run(main())