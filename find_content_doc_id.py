"""
尋找正確的內容查詢 doc_id
從頁面的 JS 文件中提取
"""

import asyncio
import re
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# 導入認證
import sys
sys.path.append(str(Path(__file__).parent))
from common.config import get_auth_file_path
import json

async def find_content_doc_id():
    """從多個來源尋找內容查詢的 doc_id"""
    
    # 讀取認證
    auth_file_path = get_auth_file_path()
    auth_data = json.loads(auth_file_path.read_text())
    cookies = {c["name"]: c["value"] for c in auth_data["cookies"]}
    
    headers = {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "accept": "*/*",
    }
    
    async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=30.0) as client:
        print("🔍 尋找內容查詢 doc_id...")
        
        # 策略1: 分析頁面中的 JS 文件
        print("\n📄 策略1: 分析主頁面中的 JS 文件...")
        try:
            response = await client.get("https://www.threads.com/")
            if response.status_code == 200:
                html = response.text
                
                # 尋找 JS 文件引用
                js_files = re.findall(r'src="([^"]*\.js[^"]*)"', html)
                print(f"   找到 {len(js_files)} 個 JS 文件")
                
                for i, js_url in enumerate(js_files[:5]):  # 只檢查前5個
                    if js_url.startswith('/'):
                        js_url = "https://www.threads.com" + js_url
                    
                    print(f"   🔍 檢查 JS 文件 {i+1}: {js_url}")
                    try:
                        js_response = await client.get(js_url)
                        if js_response.status_code == 200:
                            js_content = js_response.text
                            
                            # 搜尋 doc_id 模式
                            patterns = [
                                r'"([A-Za-z0-9]*PostPage[^"]*)":\s*\{\s*id:\s*"(\d{15,19})"',
                                r'"([A-Za-z0-9]*Thread[^"]*)":\s*\{\s*id:\s*"(\d{15,19})"',
                                r'"([A-Za-z0-9]*Media[^"]*)":\s*\{\s*id:\s*"(\d{15,19})"',
                                r'(\w+):\s*\{\s*id:\s*"(\d{15,19})"[^}]*media[^}]*\}',
                            ]
                            
                            for pattern in patterns:
                                matches = re.findall(pattern, js_content)
                                if matches:
                                    print(f"      ✅ 找到查詢: {matches[:3]}")  # 只顯示前3個
                    except:
                        continue
                        
        except Exception as e:
            print(f"   ❌ 策略1失敗: {e}")
        
        # 策略2: 嘗試已知的備用 doc_id 列表
        print("\n🎯 策略2: 測試已知的備用 doc_id...")
        
        # 擴展的 doc_id 列表（從網路上收集的）
        known_doc_ids = [
            "7428920450586442",  # SingleThreadQuery
            "7248604598467997",  # BarcelonaPostPageContentQuery  
            "7439738349112860",  # ProfileThreadsTabQuery
            "6981243555252543",  # BarcelonaPostPageFeedMediaQuery
            "7127871700615871",  # BarcelonaPostPageDirectQuery
            "7268729639845570",  # ThreadQuery
            "7395825420492230",  # MediaQuery
            "7396485793756116",  # BarcelonaPostPageRefetchableDirectQuery
            "25924527474041776", # 較新的查詢ID
            "8523948474355533",  # 另一個可能的ID
        ]
        
        test_pk = "3689219480905289907"  # 我們已知的有效 PK
        
        for doc_id in known_doc_ids:
            print(f"   🧪 測試 doc_id: {doc_id}")
            try:
                # 測試新格式
                variables = json.dumps({
                    "postID_pk": test_pk,
                    "withShallowTree": False,
                    "includePromotedPosts": False
                })
                
                # 我們需要一個假的 LSD token 來測試
                fake_lsd = "test123"
                data = f"lsd={fake_lsd}&doc_id={doc_id}&variables={variables}"
                
                test_response = await client.post(
                    "https://www.threads.com/graphql/query",
                    data=data,
                    headers={"x-fb-lsd": fake_lsd}
                )
                
                print(f"      HTTP {test_response.status_code}")
                
                # 分析響應
                if test_response.status_code == 200:
                    try:
                        result = test_response.json()
                        if "data" in result and result["data"]:
                            if "media" in result["data"]:
                                print(f"      ✅ 找到有效的內容查詢: {doc_id}")
                                print(f"         響應包含 media 數據")
                                return doc_id
                            else:
                                print(f"      ⚠️ 有響應但無 media: {list(result.get('data', {}).keys())}")
                        else:
                            print(f"      ❌ 空響應或錯誤")
                    except:
                        print(f"      ❌ 無法解析 JSON 響應")
                elif test_response.status_code == 400:
                    print(f"      ❌ 400 錯誤 (可能是錯誤的 variables 格式)")
                elif test_response.status_code == 401:
                    print(f"      ❌ 401 錯誤 (認證問題)")
                else:
                    print(f"      ❌ 其他錯誤")
                    
            except Exception as e:
                print(f"      ❌ 測試失敗: {e}")
        
        # 策略3: 嘗試舊格式變數
        print("\n🔄 策略3: 嘗試舊格式變數...")
        
        for doc_id in known_doc_ids[:3]:  # 只測試前3個
            print(f"   🧪 測試舊格式 doc_id: {doc_id}")
            try:
                # 測試舊格式
                variables = json.dumps({
                    "postID": test_pk,
                    "includePromotedPosts": False
                })
                
                fake_lsd = "test123"
                data = f"lsd={fake_lsd}&doc_id={doc_id}&variables={variables}"
                
                test_response = await client.post(
                    "https://www.threads.com/graphql/query",
                    data=data,
                    headers={"x-fb-lsd": fake_lsd}
                )
                
                print(f"      HTTP {test_response.status_code}")
                
                if test_response.status_code == 200:
                    try:
                        result = test_response.json()
                        if "data" in result and result["data"] and "media" in result["data"]:
                            print(f"      ✅ 舊格式有效的內容查詢: {doc_id}")
                            return doc_id
                    except:
                        pass
                        
            except Exception as e:
                print(f"      ❌ 測試失敗: {e}")
        
        print("\n❌ 未找到有效的內容查詢 doc_id")
        return None

async def main():
    """主函數"""
    doc_id = await find_content_doc_id()
    if doc_id:
        print(f"\n🎉 找到有效的內容查詢 doc_id: {doc_id}")
    else:
        print(f"\n😞 未找到有效的內容查詢 doc_id")

if __name__ == "__main__":
    asyncio.run(main())