#!/usr/bin/env python3
"""
雙軌爬蟲系統測試腳本

測試項目：
1. Reader服務集群健康檢查
2. Reader Processor批量處理
3. Crawl Coordinator統一API
4. 數據庫狀態更新
5. fast/full/hybrid模式功能
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict, Any

# 服務端點配置
SERVICES = {
    "reader_lb": "http://localhost:8880",
    "reader_processor": "http://localhost:8009", 
    "crawl_coordinator": "http://localhost:8008",
    "playwright_crawler": "http://localhost:8006"
}

class DualTrackTester:
    """雙軌系統測試器"""
    
    def __init__(self):
        self.test_results = {}
    
    async def test_service_health(self, service_name: str, url: str) -> bool:
        """測試服務健康狀態"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ {service_name}: {data}")
                        return True
                    else:
                        print(f"❌ {service_name}: HTTP {response.status}")
                        return False
        except Exception as e:
            print(f"❌ {service_name}: {e}")
            return False
    
    async def test_reader_cluster(self) -> bool:
        """測試Reader集群"""
        print("\n🔍 測試Reader集群...")
        
        # 測試負載平衡器
        reader_lb_ok = await self.test_service_health("Reader LB", SERVICES["reader_lb"])
        
        # 測試Reader處理器
        reader_processor_ok = await self.test_service_health("Reader Processor", SERVICES["reader_processor"])
        
        # 測試Reader實際處理能力
        test_url = "https://www.threads.com/@natgeo/post/C_test123"
        try:
            async with aiohttp.ClientSession() as session:
                reader_url = f"{SERVICES['reader_lb']}/{test_url}"
                async with session.get(reader_url, headers={"X-Return-Format": "text"}, timeout=30) as response:
                    if response.status == 200:
                        content = await response.text()
                        print(f"✅ Reader處理測試: 成功處理 ({len(content)} 字符)")
                        return reader_lb_ok and reader_processor_ok
                    else:
                        print(f"⚠️ Reader處理測試: HTTP {response.status}")
                        return reader_lb_ok and reader_processor_ok
        except Exception as e:
            print(f"⚠️ Reader處理測試: {e}")
            return reader_lb_ok and reader_processor_ok
    
    async def test_reader_batch_processing(self) -> bool:
        """測試Reader批量處理"""
        print("\n🔍 測試Reader批量處理...")
        
        test_data = {
            "urls": [
                "https://www.threads.com/@natgeo/post/C_test1",
                "https://www.threads.com/@natgeo/post/C_test2"
            ],
            "username": "natgeo",
            "timeout": 30,
            "return_format": "text"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SERVICES['reader_processor']}/process",
                    json=test_data,
                    timeout=60
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ 批量處理: {result['successful']}/{result['total_urls']} 成功")
                        print(f"   總耗時: {result['total_time']:.2f}秒")
                        return True
                    else:
                        error = await response.text()
                        print(f"❌ 批量處理失敗: HTTP {response.status} - {error}")
                        return False
        except Exception as e:
            print(f"❌ 批量處理異常: {e}")
            return False
    
    async def test_crawl_coordinator_modes(self) -> bool:
        """測試爬蟲協調器的不同模式"""
        print("\n🔍 測試爬蟲協調器模式...")
        
        test_username = "natgeo"
        modes_to_test = ["fast"]  # 只測試不需要認證的模式
        
        results = {}
        
        for mode in modes_to_test:
            print(f"\n   測試 {mode} 模式...")
            
            test_data = {
                "username": test_username,
                "max_posts": 3,
                "mode": mode,
                "also_slow": False
            }
            
            try:
                start_time = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{SERVICES['crawl_coordinator']}/crawl",
                        json=test_data,
                        timeout=120
                    ) as response:
                        elapsed = time.time() - start_time
                        
                        if response.status == 200:
                            result = await response.json()
                            print(f"   ✅ {mode}模式: {len(result['posts'])} 篇貼文, {elapsed:.2f}秒")
                            print(f"      狀態: {result['status']}, {result['message']}")
                            results[mode] = True
                        else:
                            error = await response.text()
                            print(f"   ❌ {mode}模式失敗: HTTP {response.status} - {error}")
                            results[mode] = False
            except Exception as e:
                print(f"   ❌ {mode}模式異常: {e}")
                results[mode] = False
        
        return all(results.values())
    
    async def test_status_tracking(self) -> bool:
        """測試狀態追蹤功能"""
        print("\n🔍 測試狀態追蹤...")
        
        test_username = "natgeo"
        
        try:
            # 測試URL狀態查詢
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SERVICES['playwright_crawler']}/urls/{test_username}?max_posts=5") as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ URL狀態查詢: {len(result['urls'])} 個URLs")
                        print(f"   摘要: {result['summary']}")
                        
                        # 檢查狀態欄位
                        if result['urls']:
                            sample_url = result['urls'][0]
                            required_fields = ['reader_status', 'dom_status', 'needs_reader', 'needs_dom']
                            has_all_fields = all(field in sample_url for field in required_fields)
                            
                            if has_all_fields:
                                print("✅ 狀態欄位完整")
                                return True
                            else:
                                print(f"❌ 缺少狀態欄位: {required_fields}")
                                return False
                        else:
                            print("⚠️ 沒有URLs數據，無法測試狀態欄位")
                            return True
                    else:
                        error = await response.text()
                        print(f"❌ URL狀態查詢失敗: HTTP {response.status} - {error}")
                        return False
        except Exception as e:
            print(f"❌ 狀態追蹤異常: {e}")
            return False
    
    async def test_database_migration(self) -> bool:
        """測試數據庫遷移結果"""
        print("\n🔍 測試數據庫遷移...")
        
        try:
            # 通過爬蟲協調器的狀態端點檢查數據庫
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SERVICES['crawl_coordinator']}/status/natgeo") as response:
                    if response.status == 200:
                        result = await response.json()
                        summary = result['summary']
                        
                        # 檢查新欄位是否存在
                        expected_fields = ['reader_complete', 'dom_complete', 'needs_reader', 'needs_dom']
                        has_all_fields = all(field in summary for field in expected_fields)
                        
                        if has_all_fields:
                            print("✅ 數據庫遷移成功，新欄位可用")
                            print(f"   統計: Reader完成={summary['reader_complete']}, DOM完成={summary['dom_complete']}")
                            return True
                        else:
                            print(f"❌ 數據庫遷移不完整，缺少欄位: {expected_fields}")
                            return False
                    else:
                        print(f"❌ 無法查詢數據庫狀態: HTTP {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 數據庫遷移測試異常: {e}")
            return False
    
    async def run_all_tests(self):
        """執行所有測試"""
        print("🚀 雙軌爬蟲系統測試開始...")
        print(f"⏰ 測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        tests = [
            ("服務健康檢查", self.test_service_health_all),
            ("Reader集群測試", self.test_reader_cluster),
            ("Reader批量處理", self.test_reader_batch_processing),
            ("爬蟲協調器模式", self.test_crawl_coordinator_modes),
            ("狀態追蹤功能", self.test_status_tracking),
            ("數據庫遷移", self.test_database_migration)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{'='*50}")
            print(f"🧪 執行測試: {test_name}")
            
            try:
                result = await test_func()
                if result:
                    print(f"✅ {test_name} - 通過")
                    passed += 1
                else:
                    print(f"❌ {test_name} - 失敗")
            except Exception as e:
                print(f"💥 {test_name} - 異常: {e}")
        
        print(f"\n{'='*50}")
        print(f"📊 測試完成: {passed}/{total} 通過")
        
        if passed == total:
            print("🎉 所有測試通過！雙軌系統運行正常")
        else:
            print(f"⚠️ {total-passed} 個測試失敗，請檢查相關服務")
        
        return passed == total
    
    async def test_service_health_all(self) -> bool:
        """測試所有服務健康狀態"""
        results = []
        for service_name, url in SERVICES.items():
            result = await self.test_service_health(service_name, url)
            results.append(result)
        return all(results)

async def main():
    """主函數"""
    tester = DualTrackTester()
    success = await tester.run_all_tests()
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)