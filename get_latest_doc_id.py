"""
動態獲取最新的 doc_id from manifest.json
"""

import re
import zstandard
import json
import httpx
import asyncio
from typing import Optional

MANIFEST_URL = "https://www.threads.com/data/manifest.json"

async def get_latest_doc_id(query_kind: str = "PostPage") -> Optional[str]:
    """
    從 manifest.json 獲取最新的 doc_id
    
    Args:
        query_kind: 查詢類型，如 "PostPage", "PostContent" 等
    
    Returns:
        最新的 doc_id 或 None
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(MANIFEST_URL)
            
            if response.status_code != 200:
                print(f"❌ 獲取 manifest 失敗: HTTP {response.status_code}")
                return None
            
            blob = response.content
            
            # 檢查是否為壓縮內容
            content_encoding = response.headers.get("content-encoding", "")
            if content_encoding == "zstd":
                try:
                    decompressor = zstandard.ZstdDecompressor()
                    blob = decompressor.decompress(blob)
                except Exception as e:
                    print(f"❌ zstd 解壓失敗: {e}")
                    # 嘗試直接解碼
                    print(f"💡 嘗試直接解碼...")
            elif content_encoding == "gzip":
                import gzip
                try:
                    blob = gzip.decompress(blob)
                except Exception as e:
                    print(f"❌ gzip 解壓失敗: {e}")
            
            # 如果是 JSON 格式，嘗試直接解析
            if blob.startswith(b'{'):
                print(f"💡 檢測到未壓縮的 JSON 格式")
            
            # 解碼為文本
            try:
                manifest_text = blob.decode('utf-8')
            except UnicodeDecodeError:
                print(f"❌ 解碼 manifest 失敗")
                return None
            
            # 尋找對應的 doc_id
            # 例如: "BarcelonaPostPageContentQuery":{"id":"25073444793714143", ...}
            pattern = rf'"[^"]*{query_kind}[^"]*Query"\s*:\s*\{{"id":"(\d+)"'
            match = re.search(pattern, manifest_text)
            
            if match:
                doc_id = match.group(1)
                print(f"✅ 找到最新 doc_id: {doc_id} (查詢類型: {query_kind})")
                return doc_id
            else:
                print(f"❌ 在 manifest 中找不到 {query_kind} 相關的 doc_id")
                
                # 列出所有可用的查詢類型
                all_queries = re.findall(r'"([^"]*Query)"\s*:\s*\{"id":"(\d+)"', manifest_text)
                if all_queries:
                    print(f"💡 可用的查詢類型:")
                    for query_name, query_doc_id in all_queries[:10]:  # 只顯示前10個
                        if "Barcelona" in query_name or "Post" in query_name:
                            print(f"   {query_name}: {query_doc_id}")
                
                return None
    
    except Exception as e:
        print(f"❌ 獲取 manifest 失敗: {e}")
        return None

async def main():
    """測試 doc_id 獲取"""
    print("🔍 獲取最新的 doc_id...")
    
    # 嘗試不同的查詢類型
    query_types = [
        "PostPage",
        "PostContent", 
        "PostPageRefetchable",
        "PostPageContent",
        "Media"
    ]
    
    for query_type in query_types:
        doc_id = await get_latest_doc_id(query_type)
        if doc_id:
            print(f"📋 {query_type}: {doc_id}")
        print()

if __name__ == "__main__":
    asyncio.run(main())