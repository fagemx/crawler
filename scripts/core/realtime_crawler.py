#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
實時爬蟲核心
主要協調邏輯和流程控制
"""

import asyncio
import json
import time
import threading
import concurrent.futures
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path

from playwright.async_api import async_playwright

from common.config import get_auth_file_path
from common.incremental_crawl_manager import IncrementalCrawlManager
from ..processors import PostProcessor
from ..crawlers import UrlCollector
from ..utils.helpers import safe_print

class RealtimeCrawler:
    """實時爬蟲核心類"""
    
    def __init__(self, target_username: str, max_posts: int = 20, incremental: bool = True):
        self.target_username = target_username
        self.max_posts = max_posts
        self.incremental = incremental
        
        # 增量爬取管理器
        self.crawl_manager = IncrementalCrawlManager() if incremental else None
        
        # 爬蟲Agent設定
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.auth_file_path = get_auth_file_path(from_project_root=True)
        
        # 處理器
        self.post_processor = PostProcessor(target_username)
        self.url_collector = UrlCollector(target_username, max_posts, self.auth_file_path)
        
        # 結果統計
        self.results = []
        self.start_time = None
        self.api_success_count = 0
        self.api_failure_count = 0
        self.local_success_count = 0
        self.local_failure_count = 0
    
    async def collect_urls_only(self) -> List[str]:
        """收集URLs"""
        # 增量模式：獲取已存在的post_ids
        existing_post_ids = set()
        if self.incremental and self.crawl_manager:
            safe_print("🔍 正在檢查資料庫連接...")
            try:
                existing_post_ids = await self.crawl_manager.get_existing_post_ids(self.target_username)
                checkpoint = await self.crawl_manager.get_crawl_checkpoint(self.target_username)
                safe_print(f"✅ 資料庫連接成功")
                safe_print(f"🔍 增量模式: 已爬取 {len(existing_post_ids)} 個貼文")
                if len(existing_post_ids) > 0:
                    safe_print(f"📋 已存在貼文ID範例: {list(existing_post_ids)[:3]}...")
                if checkpoint:
                    safe_print(f"📊 上次檢查點: {checkpoint.latest_post_id} (總計: {checkpoint.total_crawled})")
                else:
                    safe_print("📊 未找到檢查點記錄 (首次爬取)")
            except Exception as e:
                safe_print(f"❌ 資料庫連接失敗: {e}")
                safe_print("🔄 回退到全量模式")
                self.incremental = False
                self.crawl_manager = None
        else:
            safe_print("📋 全量模式: 爬取所有找到的貼文")
        
        # 使用URL收集器
        return await self.url_collector.collect_urls(existing_post_ids, self.incremental)
    
    async def run_realtime_extraction(self):
        """主要執行流程"""
        self.start_time = time.time()
        safe_print(f"🚀 開始實時爬取: @{self.target_username}")
        safe_print(f"📊 模式: {'增量' if self.incremental else '全量'}, 目標: {self.max_posts} 個貼文")
        
        # URL收集階段
        safe_print("=" * 60)
        safe_print("📍 階段1: 智能滾動收集URLs")
        url_start_time = time.time()
        
        urls = await self.collect_urls_only()
        
        url_end_time = time.time()
        url_collection_time = url_end_time - url_start_time
        
        if not urls:
            safe_print("❌ 未收集到任何URL")
            return
        
        safe_print(f"✅ URL收集完成: {len(urls)} 個URL, 耗時 {url_collection_time:.2f}s")
        safe_print(f"⚡ URL收集速度: {len(urls)/url_collection_time:.2f} URLs/秒")
        
        # 內容提取階段
        safe_print("=" * 60)
        safe_print("📍 階段2: 實時內容提取")
        extraction_start_time = time.time()
        
        for i, url in enumerate(urls):
            result = await self.post_processor.process_url_realtime(url, i, len(urls))
            if result:
                self.results.append(result)
                # 統計API使用情況
                if result.get('source') == 'jina_api':
                    self.api_success_count += 1
                elif result.get('source') == 'local_reader':
                    self.local_success_count += 1
                else:
                    self.api_failure_count += 1
        
        extraction_end_time = time.time()
        extraction_time = extraction_end_time - extraction_start_time
        
        # 顯示最終統計
        safe_print("=" * 60)
        safe_print("📊 最終統計")
        self.show_final_statistics()
        
        # 保存結果
        safe_print("=" * 60)
        safe_print("💾 保存結果")
        results_file = self.save_results()
        
        safe_print("=" * 60)
        safe_print("🎉 爬取完成！")
        safe_print(f"📁 結果文件: {results_file}")
        
        return results_file
    
    def show_final_statistics(self):
        """顯示最終統計"""
        total_time = time.time() - self.start_time if self.start_time else 0
        total_processed = len(self.results)
        
        # 基本統計
        safe_print(f"📊 總處理數: {total_processed}")
        safe_print(f"⏱️  總耗時: {total_time:.2f}秒")
        if total_processed > 0:
            safe_print(f"⚡ 平均速度: {total_processed/total_time:.2f} 貼文/秒")
        
        # API使用統計
        safe_print(f"📡 Jina API 成功: {self.api_success_count}")
        safe_print(f"🏠 本地Reader 成功: {self.local_success_count}")
        safe_print(f"❌ 失敗: {self.api_failure_count}")
        
        total_attempts = self.api_success_count + self.local_success_count + self.api_failure_count
        if total_attempts > 0:
            safe_print(f"✅ 整體成功率: {((self.api_success_count + self.local_success_count) / total_attempts * 100):.1f}%")
        
        # 提取成功率統計
        if self.results:
            views_count = len([r for r in self.results if r.get('has_views')])
            content_count = len([r for r in self.results if r.get('has_content')])
            likes_count = len([r for r in self.results if r.get('has_likes')])
            comments_count = len([r for r in self.results if r.get('has_comments')])
            reposts_count = len([r for r in self.results if r.get('has_reposts')])
            shares_count = len([r for r in self.results if r.get('has_shares')])
            
            safe_print(f"👁️  觀看數提取: {views_count}/{total_processed} ({views_count/total_processed*100:.1f}%)")
            safe_print(f"📝 內容提取: {content_count}/{total_processed} ({content_count/total_processed*100:.1f}%)")
            safe_print(f"👍 按讚數提取: {likes_count}/{total_processed} ({likes_count/total_processed*100:.1f}%)")
            safe_print(f"💬 留言數提取: {comments_count}/{total_processed} ({comments_count/total_processed*100:.1f}%)")
            safe_print(f"🔄 轉發數提取: {reposts_count}/{total_processed} ({reposts_count/total_processed*100:.1f}%)")
            safe_print(f"📤 分享數提取: {shares_count}/{total_processed} ({shares_count/total_processed*100:.1f}%)")
    
    def save_results(self):
        """保存結果到文件和資料庫"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 確保目錄存在
        results_dir = Path('extraction_results')
        results_dir.mkdir(exist_ok=True)
        
        filename = f"realtime_extraction_results_{timestamp}.json"
        filepath = results_dir / filename
        
        # 計算統計信息
        total_time = time.time() - self.start_time if self.start_time else 0
        total_processed = len(self.results)
        
        # 構建完整結果
        full_result = {
            'timestamp': datetime.now().isoformat(),
            'target_username': self.target_username,
            'max_posts': self.max_posts,
            'total_processed': total_processed,
            'api_success_count': self.api_success_count,
            'api_failure_count': self.api_failure_count,
            'local_success_count': self.local_success_count,
            'local_failure_count': self.local_failure_count,
            'overall_success_rate': ((self.api_success_count + self.local_success_count) / max(total_processed, 1)) * 100,
            'timing': {
                'total_time': total_time,
                'overall_speed': total_processed / max(total_time, 1)
            },
            'results': self.results
        }
        
        # 添加提取統計
        if self.results:
            views_count = len([r for r in self.results if r.get('has_views')])
            content_count = len([r for r in self.results if r.get('has_content')])
            likes_count = len([r for r in self.results if r.get('has_likes')])
            comments_count = len([r for r in self.results if r.get('has_comments')])
            reposts_count = len([r for r in self.results if r.get('has_reposts')])
            shares_count = len([r for r in self.results if r.get('has_shares')])
            
            full_result.update({
                'views_extraction_count': views_count,
                'content_extraction_count': content_count,
                'likes_extraction_count': likes_count,
                'comments_extraction_count': comments_count,
                'reposts_extraction_count': reposts_count,
                'shares_extraction_count': shares_count,
                'views_extraction_rate': (views_count / total_processed * 100) if total_processed > 0 else 0,
                'content_extraction_rate': (content_count / total_processed * 100) if total_processed > 0 else 0,
                'likes_extraction_rate': (likes_count / total_processed * 100) if total_processed > 0 else 0,
                'comments_extraction_rate': (comments_count / total_processed * 100) if total_processed > 0 else 0,
                'reposts_extraction_rate': (reposts_count / total_processed * 100) if total_processed > 0 else 0,
                'shares_extraction_rate': (shares_count / total_processed * 100) if total_processed > 0 else 0,
            })
        
        # 保存到JSON文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(full_result, f, ensure_ascii=False, indent=2)
            safe_print(f"✅ 結果已保存到: {filepath}")
        except Exception as e:
            safe_print(f"❌ 保存JSON文件失敗: {e}")
            return None
        
        # 保存到資料庫（增量模式）
        if self.incremental and self.crawl_manager and self.results:
            safe_print(f"💾 正在保存 {len(self.results)} 個結果到資料庫...")
            try:
                import asyncio
                try:
                    current_loop = asyncio.get_running_loop()
                    safe_print("🔍 檢測到運行中的事件循環，使用同步模式...")
                    self._save_to_database_sync()
                except RuntimeError:
                    safe_print("📤 正在寫入資料庫...")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    saved_count = loop.run_until_complete(
                        self.crawl_manager.save_quick_crawl_results(self.results, self.target_username)
                    )
                    safe_print(f"✅ 成功保存 {saved_count} 個貼文到資料庫")
                    
                    # 更新檢查點
                    if self.results and saved_count > 0:
                        latest_post_id = self.results[0].get('post_id')
                        if latest_post_id:
                            safe_print(f"📊 更新檢查點: {latest_post_id}")
                            loop.run_until_complete(
                                self.crawl_manager.update_crawl_checkpoint(
                                    self.target_username, 
                                    latest_post_id, 
                                    saved_count
                                )
                            )
                            safe_print(f"✅ 檢查點更新成功")
                    
                    loop.close()
                    safe_print(f"💾 資料庫操作完成: 保存 {saved_count} 個新貼文")
            except Exception as e:
                safe_print(f"❌ 資料庫保存失敗: {e}")
                safe_print(f"🔍 錯誤詳情: {type(e).__name__}: {str(e)}")
                safe_print("📝 將只保存到JSON文件")
        
        return str(filepath)
    
    def _save_to_database_sync(self):
        """同步版本的資料庫保存"""
        def async_save_worker():
            import asyncio
            from common.incremental_crawl_manager import IncrementalCrawlManager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            new_crawl_manager = IncrementalCrawlManager()
            try:
                safe_print("📤 正在寫入資料庫...")
                saved_count = loop.run_until_complete(
                    new_crawl_manager.save_quick_crawl_results(self.results, self.target_username)
                )
                safe_print(f"✅ 成功保存 {saved_count} 個貼文到資料庫")
                if self.results and saved_count > 0:
                    latest_post_id = self.results[0].get('post_id')
                    if latest_post_id:
                        safe_print(f"📊 更新檢查點: {latest_post_id}")
                        loop.run_until_complete(
                            new_crawl_manager.update_crawl_checkpoint(
                                self.target_username, 
                                latest_post_id, 
                                saved_count
                            )
                        )
                        safe_print(f"✅ 檢查點更新成功")
                safe_print(f"💾 資料庫操作完成: 保存 {saved_count} 個新貼文")
                return saved_count
            finally:
                try:
                    loop.run_until_complete(new_crawl_manager.db.close_pool())
                except:
                    pass
                loop.close()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(async_save_worker)
            try:
                result = future.result(timeout=60)
                safe_print(f"🎯 線程執行完成，結果: {result}")
                return result
            except concurrent.futures.TimeoutError:
                safe_print("❌ 資料庫保存超時")
                raise
            except Exception as e:
                safe_print(f"❌ 資料庫保存線程執行失敗: {e}")
                safe_print(f"🔍 錯誤類型: {type(e).__name__}")
                raise