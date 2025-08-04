#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
貼文處理器
處理API請求和貼文解析
"""

import requests
import concurrent.futures
from typing import Dict, Optional, Tuple
from datetime import datetime

from ..extractors import ContentExtractor, MetricsExtractor
from ..utils.helpers import safe_print

class PostProcessor:
    """貼文處理器"""
    
    def __init__(self, target_username: str = None):
        self.target_username = target_username
        
        # API設定
        self.official_reader_url = "https://r.jina.ai"
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        # 本地Reader配置
        self.local_reader_url = "http://localhost:8880"
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
        # 提取器
        self.content_extractor = ContentExtractor(target_username)
        self.metrics_extractor = MetricsExtractor()
    
    def fetch_content_jina_api(self, url: str) -> Tuple[bool, str]:
        """從Jina API獲取內容"""
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=60)
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def fetch_content_local(self, url: str, use_cache: bool = True, max_retries: int = 2) -> Tuple[bool, str]:
        """使用本地Reader獲取內容 - 快速重試機制"""
        headers = self.local_headers.copy()
        if not use_cache: 
            headers['x-no-cache'] = 'true'
        
        for attempt in range(max_retries + 1):
            try:
                # 降低timeout，快速失敗
                timeout = 15 if attempt == 0 else 10  # 第一次15s，重試10s
                response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=timeout)
                if response.status_code == 200:
                    return True, response.text
                else:
                    if attempt < max_retries:
                        continue  # 重試
                    return False, f"HTTP {response.status_code}"
            except Exception as e:
                if attempt < max_retries:
                    # 短暫等待後重試
                    import time
                    time.sleep(0.5)
                    continue
                return False, f"最終失敗: {str(e)}"
        
        return False, "重試耗盡"
    
    def fetch_content_local_fast(self, url: str) -> Tuple[bool, str]:
        """快速本地Reader - 專門為回退設計"""
        def try_single_request(instance_id):
            """嘗試單個Reader實例"""
            headers = self.local_headers.copy()
            headers['x-no-cache'] = 'true'  # 強制無快取
            try:
                # 超短timeout，快速失敗
                response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=8)
                return (True, response.text, instance_id) if response.status_code == 200 else (False, f"HTTP {response.status_code}", instance_id)
            except Exception as e:
                return (False, str(e), instance_id)
        
        # 平行嘗試多個實例（模擬負載均衡）
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # 提交2個平行請求（模擬重試）
            futures = [executor.submit(try_single_request, i) for i in range(2)]
            
            # 等待第一個成功的結果
            for future in concurrent.futures.as_completed(futures, timeout=12):
                try:
                    success, content, instance_id = future.result()
                    if success:
                        # 取消其他正在進行的請求
                        for f in futures:
                            f.cancel()
                        return True, content
                except Exception as e:
                    continue
        
        return False, "所有快速請求都失敗了"
    
    def parse_post(self, url: str, content: str) -> Dict:
        """解析貼文內容"""
        try:
            post_id = url.split('/')[-1] if '/' in url else url
            
            # 提取各種指標
            views = self.metrics_extractor.extract_views_count(content, post_id)
            main_content = self.content_extractor.extract_post_content(content)
            likes = self.metrics_extractor.extract_likes_count(content)
            comments = self.metrics_extractor.extract_comments_count(content)
            reposts = self.metrics_extractor.extract_reposts_count(content)
            shares = self.metrics_extractor.extract_shares_count(content)
            
            # 構建結果
            result = {
                'post_id': post_id,
                'url': url,
                'views': views,
                'content': main_content,
                'source': 'unknown',  # 會在調用方設置
                'likes': likes,
                'comments': comments,
                'reposts': reposts,
                'shares': shares,
                'success': bool(views or main_content),
                'has_views': bool(views),
                'has_content': bool(main_content),
                'has_likes': bool(likes),
                'has_comments': bool(comments),
                'has_reposts': bool(reposts),
                'has_shares': bool(shares),
                'content_length': len(content),
                'extracted_at': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            safe_print(f"❌ 解析貼文失敗 {url}: {e}")
            return {
                'post_id': url.split('/')[-1] if '/' in url else url,
                'url': url,
                'views': None,
                'content': None,
                'source': 'parse_error',
                'likes': None,
                'comments': None,
                'reposts': None,
                'shares': None,
                'success': False,
                'has_views': False,
                'has_content': False,
                'has_likes': False,
                'has_comments': False,
                'has_reposts': False,
                'has_shares': False,
                'content_length': 0,
                'extracted_at': datetime.now().isoformat(),
                'error': str(e)
            }
    
    async def process_url_realtime(self, url: str, index: int, total: int) -> Optional[Dict]:
        """實時處理單個URL"""
        post_id = url.split('/')[-1] if '/' in url else url
        safe_print(f"🔄 [{index+1}/{total}] 處理: {post_id}")
        
        # 先嘗試Jina API（官方，通常更穩定）
        try:
            safe_print(f"   📡 [{index+1}] 嘗試 Jina API...")
            success, content = self.fetch_content_jina_api(url)
            
            if success:
                safe_print(f"   ✅ [{index+1}] Jina API 成功 ({len(content)} 字符)")
                result = self.parse_post(url, content)
                result['source'] = 'jina_api'
                return result
            else:
                safe_print(f"   ❌ [{index+1}] Jina API 失敗: {content}")
        
        except Exception as e:
            safe_print(f"   ❌ [{index+1}] Jina API 異常: {e}")
        
        # API失敗，嘗試本地Reader
        try:
            safe_print(f"   🔄 [{index+1}] 回退到本地Reader...")
            success, content = self.fetch_content_local_fast(url)
            
            if success:
                safe_print(f"   ✅ [{index+1}] 本地Reader 成功 ({len(content)} 字符)")
                result = self.parse_post(url, content)
                result['source'] = 'local_reader'
                return result
            else:
                safe_print(f"   ❌ [{index+1}] 本地Reader 失敗: {content}")
        
        except Exception as e:
            safe_print(f"   ❌ [{index+1}] 本地Reader 異常: {e}")
        
        # 都失敗了
        safe_print(f"   💀 [{index+1}] 所有方法都失敗了")
        result = self.parse_post(url, "")
        result['source'] = 'all_failed'
        return result