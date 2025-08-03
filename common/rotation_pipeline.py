#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正式版本的輪迴策略讀取器
從 test_reader_rotation.py 遷移而來，包含修正後的內容提取邏輯
"""

import requests
import re
import time
import random
import json
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

class RotationPipelineReader:
    """
    輪迴策略讀取器 - 10個API → 20個本地 → 輪迴
    包含修正後的智能內容提取邏輯
    """
    
    def __init__(self):
        self.api_batch_size = 10
        self.local_batch_size = 20
        self.local_reader_url = "http://localhost:8880"
        
        # 最佳化的本地Headers
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'x-return-format': 'markdown',
            'x-wait-for-selector': 'body',
            'x-timeout': '60',
        }
        
        # 統計記錄
        self.batch_stats = {}
    
    def normalize_content(self, content: str) -> str:
        """正規化內容 - 處理NBSP等特殊字符"""
        if not content:
            return content
        
        # 處理NBSP (Non-breaking space) - 這是關鍵修正
        content = content.replace('\u00a0', ' ')  # U+00A0 → 普通空格
        content = content.replace('\xa0', ' ')    # \xa0 → 普通空格
        
        # 標準化行結束符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除多餘空白但保留結構
        lines = content.split('\n')
        normalized_lines = [line.rstrip() for line in lines]
        
        return '\n'.join(normalized_lines)
    
    def extract_views_count(self, content: str, post_id: str) -> Optional[str]:
        """提取觀看數 - 使用加強的正則表達式模式"""
        normalized_content = self.normalize_content(content)
        
        # 增強的觀看數模式 - 針對NBSP問題
        view_patterns = [
            r'(\d+(?:\.\d+)?[KMB]?)\s*views',  # 標準格式
            r'(\d+(?:\.\d+)?[KMB]?)\s*觀看',   # 中文
            r'Thread\s*=+\s*(\d+(?:\.\d+)?[KMB]?)\s*views',  # Thread標題格式
            r'views\s*(\d+(?:\.\d+)?[KMB]?)',  # 倒序
        ]
        
        for i, pattern in enumerate(view_patterns):
            matches = re.findall(pattern, normalized_content, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
    
    def extract_post_content(self, content: str) -> Optional[str]:
        """智能提取主貼文內容 - 區分主貼文和回覆 (修正版本)"""
        lines = content.split('\n')
        
        # 策略1: 查找主貼文（第一個出現的實質內容）
        main_post_content = self._extract_main_post_from_structure(lines)
        if main_post_content:
            return main_post_content
        
        # 策略2: 回到原始方法作為備選
        return self._extract_content_fallback(lines)
    
    def _extract_main_post_from_structure(self, lines: List[str]) -> Optional[str]:
        """從結構化內容中提取主貼文 - 優先提取當前頁面的主要內容"""
        main_content_candidates = []
        
        # 策略1: 如果第一行就是回覆內容，優先使用它
        if lines and lines[0].strip().startswith('>>>'):
            reply_content = lines[0].strip()
            if len(reply_content) > 10:  # 確保有實質內容
                return reply_content
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 跳過明顯的回覆標識（但如果是第一行已經處理過了）
            if i > 0 and (stripped.startswith('>>>') or stripped.startswith('回覆') or stripped.startswith('·Author')):
                continue
            
            # 尋找主貼文內容的模式
            if (stripped and 
                not stripped.startswith('[') and  # 跳過連結
                not stripped.startswith('![') and  # 跳過圖片
                not stripped.startswith('http') and  # 跳過URL
                not stripped.startswith('Log in') and  # 跳過登入提示
                not stripped.startswith('Thread') and  # 跳過Thread標題
                not stripped.startswith('gvmonthly') and  # 跳過用戶名
                not stripped.isdigit() and  # 跳過純數字
                not re.match(r'^\d+[dhm]$', stripped) and  # 跳過時間格式
                not stripped in ['Translate', 'views'] and  # 跳過特殊詞
                len(stripped) > 8):  # 內容要有一定長度
                
                # 檢查這是否可能是主貼文內容
                if self._is_likely_main_post_content(stripped, lines, i):
                    main_content_candidates.append(stripped)
        
        # 返回第一個合理的主貼文候選
        if main_content_candidates:
            return main_content_candidates[0]
        
        return None
    
    def _is_likely_main_post_content(self, content: str, lines: List[str], index: int) -> bool:
        """判斷內容是否可能是主貼文"""
        # 檢查後續是否有 "Translate" 標識（主貼文的典型結構）
        has_translate = False
        for j in range(index + 1, min(index + 3, len(lines))):
            if 'Translate' in lines[j]:
                has_translate = True
                break
        
        # 檢查是否包含常見的主貼文特徵
        has_content_features = (
            len(content) > 15 and  # 有一定長度
            not content.startswith('>>>') and  # 不是回覆
            not content.startswith('·') and  # 不是元數據
            not content.startswith('[') and  # 不是連結
            ('!' in content or '?' in content or '。' in content or '，' in content or
             '😆' in content or '😅' in content or '護照' in content or '台灣' in content)  # 包含標點符號或表情
        )
        
        # 必須有 Translate 標識 AND 有內容特徵
        return has_translate and has_content_features
    
    def _extract_content_fallback(self, lines: List[str]) -> Optional[str]:
        """備選內容提取方法"""
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        if content_start == -1:
            return None
        
        content_lines = []
        for i in range(content_start, min(content_start + 15, len(lines))):
            line = lines[i].strip()
            if (line and 
                not line.startswith('[![Image') and 
                not line.startswith('[Image') and
                not line.startswith('>>>')):  # 排除回覆
                content_lines.append(line)
                
                # 如果找到了合理的內容就停止
                if len(content_lines) >= 2 and len(line) > 10:
                    break
        
        return '\n'.join(content_lines) if content_lines else None
    
    def extract_engagement_numbers(self, markdown_content: str) -> List[str]:
        """提取所有統計數字序列（按讚、留言、轉發、分享）"""
        lines = markdown_content.split('\n')
        
        # 策略1: 查找貼文內容後的第一個圖片，然後提取後續數字
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到貼文圖片（通常在Translate之後）
            if stripped.startswith('![Image') and not 'profile picture' in stripped:
                numbers = []
                # 在這個圖片後查找連續的數字
                for j in range(i + 1, min(i + 20, len(lines))):
                    candidate = lines[j].strip()
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and not re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate) and candidate != "Pinned":
                        # 遇到非數字行（但跳過Pinned），停止收集
                        break
                
                # 如果找到了數字序列，返回
                if len(numbers) >= 3:
                    return numbers
        
        # 策略2: 查找任何上下文中的連續數字
        all_numbers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^\d+(?:\.\d+)?[KMB]?$', stripped):
                # 檢查上下文是否合理（附近有圖片或Translate等標識）
                context_valid = False
                for k in range(max(0, i-10), i):
                    if "![Image" in lines[k] or "Translate" in lines[k]:
                        context_valid = True
                        break
                
                if context_valid:
                    all_numbers.append(stripped)
        
        # 返回找到的數字（通常前4個是按讚、留言、轉發、分享）
        if len(all_numbers) >= 4:
            return all_numbers[:4]
        elif len(all_numbers) >= 3:
            return all_numbers[:3]
        
        return all_numbers
    
    def extract_likes_count(self, markdown_content: str) -> Optional[str]:
        """提取按讚數"""
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 1:
            return numbers[0]
        
        # 備選方法：尋找舊格式
        lines = markdown_content.split('\n')
        for line in lines:
            if '👍' in line or 'like' in line.lower():
                match = re.search(r'(\d+(?:,\d+)*)', line)
                if match:
                    return match.group(1)
        return None
    
    def extract_comments_count(self, markdown_content: str) -> Optional[str]:
        """提取留言數"""
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 2:
            return numbers[1]
        
        # 備選方法：尋找舊格式
        lines = markdown_content.split('\n')
        for line in lines:
            if '💬' in line or 'comment' in line.lower():
                match = re.search(r'(\d+(?:,\d+)*)', line)
                if match:
                    return match.group(1)
        return None
    
    def extract_reposts_count(self, markdown_content: str) -> Optional[str]:
        """提取轉發數"""
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 3:
            return numbers[2]
        
        # 備選方法：尋找舊格式
        lines = markdown_content.split('\n')
        for line in lines:
            if '🔄' in line or 'repost' in line.lower():
                match = re.search(r'(\d+(?:,\d+)*)', line)
                if match:
                    return match.group(1)
        return None
    
    def extract_shares_count(self, markdown_content: str) -> Optional[str]:
        """提取分享數"""
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 4:
            return numbers[3]
        
        # 備選方法：尋找舊格式
        lines = markdown_content.split('\n')
        for line in lines:
            if '📤' in line or 'share' in line.lower():
                match = re.search(r'(\d+(?:,\d+)*)', line)
                if match:
                    return match.group(1)
        return None
    
    def fetch_content_jina_api(self, url: str) -> tuple:
        """使用Jina AI官方API獲取內容"""
        try:
            api_url = f"https://r.jina.ai/{url}"
            headers = {'X-Return-Format': 'markdown'}
            response = requests.get(api_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def fetch_content_local(self, url: str, use_cache: bool = True) -> tuple:
        """使用本地Reader獲取內容"""
        headers = self.local_headers.copy()
        if not use_cache:
            headers['x-no-cache'] = 'true'
        
        try:
            response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=30)
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
    
    def parse_post(self, url: str, content: str, source: str) -> Dict:
        """解析貼文 - 完整版本包含互動數據"""
        post_id = url.split('/')[-1] if '/' in url else url
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content(content)
        
        # 提取互動數據
        likes = self.extract_likes_count(content)
        comments = self.extract_comments_count(content)
        reposts = self.extract_reposts_count(content)
        shares = self.extract_shares_count(content)
        
        return {
            'post_id': post_id,
            'url': url,
            'views': views,
            'content': main_content,
            'source': source,
            'likes': likes,
            'comments': comments,
            'reposts': reposts,
            'shares': shares,
            'success': views is not None and main_content is not None,
            'has_views': views is not None,
            'has_content': main_content is not None,
            'has_likes': likes is not None,
            'has_comments': comments is not None,
            'has_reposts': reposts is not None,
            'has_shares': shares is not None,
            'content_length': len(content)
        }
    
    def process_api_batch(self, urls: List[str], batch_num: int) -> List[Dict]:
        """處理API批次"""
        print(f"🌐 API批次 #{batch_num}: 並行處理 {len(urls)} 個URL...")
        
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_url = {
                executor.submit(self.fetch_content_jina_api, url): url 
                for url in urls
            }
            
            for completed, future in enumerate(as_completed(future_to_url), 1):
                url = future_to_url[future]
                
                try:
                    success, content = future.result()
                    if success:
                        result = self.parse_post(url, content, 'API-批次')
                        if result['has_views']:
                            status = f"✅ ({result['views']})"
                        else:
                            status = "❌ 無觀看數"
                        print(f"   🌐 {completed}/{len(urls)}: {status} {result['post_id']}")
                        results.append(result)
                    else:
                        print(f"   🌐 {completed}/{len(urls)}: ❌ API失敗 {url.split('/')[-1]} ({content})")
                        print(f"      🔄 API失敗立即回退本地Reader...")
                        
                        # API失敗時立即回退到本地Reader
                        local_success, local_content = self.fetch_content_local(url, use_cache=False)
                        if local_success:
                            local_result = self.parse_post(url, local_content, 'API-失敗回退')
                            if local_result['has_views']:
                                print(f"      ✅ 本地救援成功 ({local_result['views']}) {local_result['post_id']}")
                                results.append(local_result)
                            else:
                                print(f"      ❌ 本地救援無觀看數 {local_result['post_id']}")
                                results.append(local_result)
                        else:
                            print(f"      ❌ 本地救援也失敗: {local_content}")
                            results.append({
                                'post_id': url.split('/')[-1],
                                'url': url,
                                'views': None,
                                'content': None,
                                'likes': None,
                                'comments': None,
                                'reposts': None,
                                'shares': None,
                                'success': False,
                                'source': 'API-批次',
                                'has_views': False,
                                'has_content': False,
                                'has_likes': False,
                                'has_comments': False,
                                'has_reposts': False,
                                'has_shares': False,
                                'content_length': 0,
                                'api_error': content,
                                'local_error': local_content
                            })
                
                except Exception as e:
                    print(f"   🌐 {completed}/{len(urls)}: ❌ API異常 {url.split('/')[-1]} ({e})")
                    print(f"      🔄 API異常立即回退本地Reader...")
                    
                    # API異常時立即回退到本地Reader
                    try:
                        local_success, local_content = self.fetch_content_local(url, use_cache=False)
                        if local_success:
                            local_result = self.parse_post(url, local_content, 'API-異常回退')
                            if local_result['has_views']:
                                print(f"      ✅ 本地救援成功 ({local_result['views']}) {local_result['post_id']}")
                                results.append(local_result)
                            else:
                                print(f"      ❌ 本地救援無觀看數 {local_result['post_id']}")
                                results.append(local_result)
                        else:
                            print(f"      ❌ 本地救援也失敗: {local_content}")
                            results.append({
                                'post_id': url.split('/')[-1],
                                'url': url,
                                'views': None,
                                'content': None,
                                'likes': None,
                                'comments': None,
                                'reposts': None,
                                'shares': None,
                                'success': False,
                                'source': 'API-批次',
                                'has_views': False,
                                'has_content': False,
                                'has_likes': False,
                                'has_comments': False,
                                'has_reposts': False,
                                'has_shares': False,
                                'content_length': 0,
                                'api_error': str(e),
                                'local_error': local_content
                            })
                    except Exception as local_e:
                        print(f"      ❌ 本地救援也異常: {local_e}")
                        results.append({
                            'post_id': url.split('/')[-1],
                            'url': url,
                            'views': None,
                            'content': None,
                            'likes': None,
                            'comments': None,
                            'reposts': None,
                            'shares': None,
                            'success': False,
                            'source': 'API-批次',
                            'has_views': False,
                            'has_content': False,
                            'has_likes': False,
                            'has_comments': False,
                            'has_reposts': False,
                            'has_shares': False,
                            'content_length': 0,
                            'api_error': str(e),
                            'local_error': str(local_e)
                        })
        
        return results
    
    def process_local_batch(self, urls: List[str], batch_num: int) -> List[Dict]:
        """處理本地批次（包含API回退）"""
        print(f"⚡ 本地批次 #{batch_num}: 並行處理 {len(urls)} 個URL...")
        
        results = []
        failed_urls_for_api = []
        
        # 第一階段：本地並行處理
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_url = {
                executor.submit(self.fetch_content_local, url, False): url 
                for url in urls
            }
            
            for completed, future in enumerate(as_completed(future_to_url), 1):
                url = future_to_url[future]
                
                try:
                    success, content = future.result()
                    if success:
                        result = self.parse_post(url, content, '本地-批次')
                        if result['has_views']:
                            print(f"   ⚡ {completed}/{len(urls)}: ✅ ({result['views']}) {result['post_id']}")
                            results.append(result)
                        else:
                            print(f"   ⚡ {completed}/{len(urls)}: ❌ 本地失敗 {url.split('/')[-1]} → 轉送API")
                            failed_urls_for_api.append(url)
                    else:
                        print(f"   ⚡ {completed}/{len(urls)}: ❌ 本地失敗 {url.split('/')[-1]} → 轉送API")
                        failed_urls_for_api.append(url)
                
                except Exception as e:
                    print(f"   ⚡ {completed}/{len(urls)}: ❌ 本地異常 {url.split('/')[-1]} → 轉送API")
                    failed_urls_for_api.append(url)
        
        # 第二階段：失敗項目的API回退
        if failed_urls_for_api:
            print(f"   🌐 本地失敗項目立即轉API: {len(failed_urls_for_api)} 個...")
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_url = {
                    executor.submit(self.fetch_content_jina_api, url): url 
                    for url in failed_urls_for_api
                }
                
                for api_completed, future in enumerate(as_completed(future_to_url), 1):
                    url = future_to_url[future]
                    
                    try:
                        success, content = future.result()
                        if success:
                            result = self.parse_post(url, content, 'API-回退')
                            if result['has_views']:
                                print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ✅ API救援成功 ({result['views']}) {result['post_id']}")
                            else:
                                print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ❌ API無觀看數 {result['post_id']}")
                            results.append(result)
                        else:
                            print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ❌ API也失敗 {url.split('/')[-1]}")
                            results.append({
                                'post_id': url.split('/')[-1],
                                'url': url,
                                'success': False,
                                'source': 'API-回退',
                                'error': content
                            })
                    
                    except Exception as e:
                        print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ❌ API回退異常 {url.split('/')[-1]}")
                        results.append({
                            'post_id': url.split('/')[-1],
                            'url': url,
                            'success': False,
                            'source': 'API-回退',
                            'error': str(e)
                        })
        
        return results
    
    def rotation_pipeline(self, urls: List[str]) -> List[Dict]:
        """輪迴策略管線"""
        print(f"🔄 輪迴策略管線啟動")
        print(f"📊 處理 {len(urls)} 個URL")
        print(f"🌐 API批次大小: {self.api_batch_size} | ⚡ 本地批次大小: {self.local_batch_size}")
        print("✅ 已整合最佳化: Headers配置 + NBSP正規化 + 智能內容提取")
        print("=" * 60)
        
        all_results = []
        batch_counter = 1
        processed_count = 0
        total_start_time = time.time()
        
        remaining_urls = urls.copy()
        
        while remaining_urls:
            if len(remaining_urls) <= self.api_batch_size:
                # 最後一批，直接用API處理完
                batch_results = self.process_api_batch(remaining_urls, batch_counter)
                all_results.extend(batch_results)
                processed_count += len(remaining_urls)
                remaining_urls = []
            
            elif processed_count == 0 or (batch_counter - 1) % 2 == 0:
                # API批次（第1,3,5...批次）
                api_urls = remaining_urls[:self.api_batch_size]
                remaining_urls = remaining_urls[self.api_batch_size:]
                
                batch_results = self.process_api_batch(api_urls, batch_counter)
                all_results.extend(batch_results)
                processed_count += len(api_urls)
            
            else:
                # 本地批次（第2,4,6...批次）
                local_urls = remaining_urls[:self.local_batch_size]
                remaining_urls = remaining_urls[self.local_batch_size:]
                
                batch_results = self.process_local_batch(local_urls, batch_counter)
                all_results.extend(batch_results)
                processed_count += len(local_urls)
            
            # 更新批次統計
            batch_key = f"{batch_counter}"
            batch_results_success = [r for r in batch_results if r.get('success', False)]
            self.batch_stats[batch_key] = {
                'total': len(batch_results),
                'success': len(batch_results_success),
                'source': batch_results[0]['source'] if batch_results else 'unknown'
            }
            
            print(f"\n📊 已處理: {processed_count}/{len(urls)} ({processed_count/len(urls)*100:.1f}%)")
            print(f"🎯 剩餘: {len(remaining_urls)} 個URL")
            
            batch_counter += 1
            
            # 批次間短暫停頓
            if remaining_urls:
                time.sleep(1)
        
        # 最終統計
        total_end_time = time.time()
        success_results = [r for r in all_results if r.get('success', False)]
        success_count = len(success_results)
        
        api_success_count = len([r for r in success_results if 'API' in r.get('source', '')])
        local_success_count = len([r for r in success_results if '本地' in r.get('source', '')])
        
        print(f"\n{'='*80}")
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"🌐 API成功: {api_success_count} | ⚡ 本地成功: {local_success_count}")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 平均速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        
        # 各批次成功率
        print(f"\n📈 各批次成功率:")
        for batch_key, stats in self.batch_stats.items():
            rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
            source = stats['source']
            if 'API' in source:
                print(f"   🌐 API批次{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
            elif '本地' in source:
                print(f"   ⚡ 本地批次{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
            elif 'API-回退' in source:
                print(f"   🚀 API救援{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
        
        return all_results