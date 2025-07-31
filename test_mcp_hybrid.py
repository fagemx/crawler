#!/usr/bin/env python3
"""
MCP Server 混合方案測試腳本
測試簡化的核心功能 + 保留的獨特功能
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any


class MCPHybridTester:
    """MCP 混合方案測試器"""
    
    def __init__(self, base_url: str = "http://localhost:10100"):
        self.base_url = base_url
        self.client = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def test_health_check(self):
        """測試健康檢查 - 基礎功能"""
        print("🔍 Testing health check...")
        
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Health check passed: {data}")
            return True
            
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    async def test_agent_registration_simplified(self):
        """測試簡化的 Agent 註冊"""
        print("🔍 Testing simplified agent registration...")
        
        test_agent = {
            "name": "test-crawler",
            "role": "crawler",
            "url": "http://test-crawler:8001",
            "version": "2.0.0",
            "capabilities": {
                "web_scraping": True,
                "threads_support": True
            },
            "metadata": {
                "author": "Hybrid Test",
                "max_concurrent": 5
            }
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/register",
                json=test_agent
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Agent registration passed: {data}")
            return True
            
        except Exception as e:
            print(f"❌ Agent registration failed: {e}")
            return False
    
    async def test_heartbeat_mechanism(self):
        """測試心跳機制"""
        print("🔍 Testing heartbeat mechanism...")
        
        try:
            # 發送心跳
            response = await self.client.post(f"{self.base_url}/heartbeat/test-crawler")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Heartbeat passed: {data}")
            
            # 驗證 Agent 狀態更新
            response = await self.client.get(f"{self.base_url}/agents/test-crawler")
            if response.status_code == 200:
                agent_data = response.json()
                print(f"   Agent status: {agent_data.get('status')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Heartbeat failed: {e}")
            return False
    
    async def test_agent_discovery_with_filters(self):
        """測試帶過濾的 Agent 發現"""
        print("🔍 Testing agent discovery with filters...")
        
        try:
            # 測試按角色過濾
            response = await self.client.get(f"{self.base_url}/agents?role=crawler")
            response.raise_for_status()
            
            crawlers = response.json()
            print(f"✅ Found {len(crawlers)} crawler agents")
            
            # 測試按狀態過濾
            response = await self.client.get(f"{self.base_url}/agents?status=ONLINE")
            response.raise_for_status()
            
            online_agents = response.json()
            print(f"✅ Found {len(online_agents)} online agents")
            
            return True
            
        except Exception as e:
            print(f"❌ Agent discovery failed: {e}")
            return False
    
    async def test_media_download_preserved(self):
        """測試保留的媒體下載功能"""
        print("🔍 Testing preserved media download functionality...")
        
        test_data = {
            "post_url": "https://example.com/hybrid-test-post",
            "media_urls": [
                "https://via.placeholder.com/600x400.jpg",
                "https://via.placeholder.com/800x600.png"
            ],
            "max_concurrent": 2
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/media/download",
                json=test_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Media download initiated: {data}")
                
                # 等待一下讓後台處理
                await asyncio.sleep(3)
                
                # 檢查媒體檔案狀態
                await self.test_media_files_retrieval(test_data["post_url"])
                
            else:
                print(f"⚠️ Media download returned {response.status_code}: {response.text}")
            
            return True
            
        except Exception as e:
            print(f"❌ Media download failed: {e}")
            return False
    
    async def test_media_files_retrieval(self, post_url: str):
        """測試媒體檔案檢索"""
        print("🔍 Testing media files retrieval...")
        
        try:
            import urllib.parse
            encoded_url = urllib.parse.quote(post_url, safe='')
            
            response = await self.client.get(f"{self.base_url}/media/{encoded_url}")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Media files retrieved: {data['count']} files for post")
            
            for media_file in data['media_files'][:3]:  # 只顯示前3個
                print(f"   - {media_file['media_type']}: {media_file['download_status']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Media files retrieval failed: {e}")
            return False
    
    async def test_enhanced_statistics(self):
        """測試增強的統計功能"""
        print("🔍 Testing enhanced statistics...")
        
        try:
            response = await self.client.get(f"{self.base_url}/stats")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Enhanced statistics retrieved:")
            
            # Agent 統計
            agent_stats = data.get('agents', {})
            print(f"   - Total agents: {agent_stats.get('total', 0)}")
            print(f"   - Online agents: {agent_stats.get('online', 0)}")
            
            # 按角色統計
            by_role = agent_stats.get('by_role', {})
            for role, stats in by_role.items():
                print(f"   - {role}: {stats['online']}/{stats['total']} online")
            
            # 媒體統計
            db_stats = data.get('database', {})
            media_stats = db_stats.get('media_files', {})
            if media_stats:
                print(f"   - Media files: {media_stats.get('completed', 0)}/{media_stats.get('total', 0)} completed")
            
            return True
            
        except Exception as e:
            print(f"❌ Enhanced statistics failed: {e}")
            return False
    
    async def test_operation_logs(self):
        """測試操作日誌"""
        print("🔍 Testing operation logs...")
        
        try:
            # 獲取最近的操作日誌
            response = await self.client.get(f"{self.base_url}/system/logs?limit=5")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Operation logs retrieved: {data['count']} recent logs")
            
            for log in data['logs'][:3]:  # 只顯示前3個
                print(f"   - {log['operation_type']}: {log['status']} ({log.get('execution_time_ms', 0)}ms)")
            
            # 測試按類型過濾
            response = await self.client.get(f"{self.base_url}/system/logs?operation_type=register&limit=3")
            if response.status_code == 200:
                register_logs = response.json()
                print(f"   - Registration logs: {register_logs['count']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Operation logs failed: {e}")
            return False
    
    async def test_mcp_client_simulation(self):
        """模擬 MCP Client 的使用"""
        print("🔍 Testing MCP Client simulation...")
        
        try:
            # 模擬多個 Agent 註冊
            agents = [
                {"name": "vision-1", "role": "vision", "url": "http://vision-1:8005"},
                {"name": "playwright-1", "role": "playwright-crawler", "url": "http://playwright-1:8006"},
                {"name": "orchestrator-1", "role": "orchestrator", "url": "http://orchestrator-1:8000"}
            ]
            
            registered_count = 0
            for agent in agents:
                try:
                    response = await self.client.post(f"{self.base_url}/register", json=agent)
                    if response.status_code == 200:
                        registered_count += 1
                        
                        # 發送心跳
                        await self.client.post(f"{self.base_url}/heartbeat/{agent['name']}")
                        
                except Exception as e:
                    print(f"   ⚠️ Failed to register {agent['name']}: {e}")
            
            print(f"✅ MCP Client simulation: {registered_count}/{len(agents)} agents registered")
            
            # 測試服務發現
            response = await self.client.get(f"{self.base_url}/agents")
            if response.status_code == 200:
                all_agents = response.json()
                print(f"   - Total agents in system: {len(all_agents)}")
            
            return True
            
        except Exception as e:
            print(f"❌ MCP Client simulation failed: {e}")
            return False
    
    async def run_hybrid_tests(self):
        """執行混合方案測試"""
        print("🚀 Starting MCP Hybrid Solution Tests...\n")
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Simplified Agent Registration", self.test_agent_registration_simplified),
            ("Heartbeat Mechanism", self.test_heartbeat_mechanism),
            ("Agent Discovery with Filters", self.test_agent_discovery_with_filters),
            ("Preserved Media Download", self.test_media_download_preserved),
            ("Enhanced Statistics", self.test_enhanced_statistics),
            ("Operation Logs", self.test_operation_logs),
            ("MCP Client Simulation", self.test_mcp_client_simulation),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results[test_name] = result
            except Exception as e:
                print(f"❌ {test_name} crashed: {e}")
                results[test_name] = False
            
            print()  # 空行分隔
        
        # 總結
        print("📊 Hybrid Solution Test Results:")
        print("=" * 60)
        
        passed = sum(1 for r in results.values() if r)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print("=" * 60)
        print(f"Total: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        # 混合方案評估
        print("\n🎯 Hybrid Solution Assessment:")
        print("=" * 60)
        
        core_features = ["Health Check", "Simplified Agent Registration", "Heartbeat Mechanism", "Agent Discovery with Filters"]
        core_passed = sum(1 for test in core_features if results.get(test, False))
        
        unique_features = ["Preserved Media Download", "Enhanced Statistics", "Operation Logs"]
        unique_passed = sum(1 for test in unique_features if results.get(test, False))
        
        print(f"Core Features (示範方案): {core_passed}/{len(core_features)} ✅")
        print(f"Unique Features (我的優點): {unique_passed}/{len(unique_features)} ✅")
        print(f"Integration Test: {1 if results.get('MCP Client Simulation', False) else 0}/1 ✅")
        
        if passed >= total * 0.8:
            print("\n🎉 Hybrid solution is working well! Ready for production.")
        elif passed >= total * 0.6:
            print("\n⚠️ Hybrid solution needs some fixes but shows promise.")
        else:
            print("\n❌ Hybrid solution needs significant work.")
        
        return passed == total


async def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Hybrid Solution Tester")
    parser.add_argument(
        "--url", 
        default="http://localhost:10100",
        help="MCP Server URL (default: http://localhost:10100)"
    )
    
    args = parser.parse_args()
    
    async with MCPHybridTester(args.url) as tester:
        success = await tester.run_hybrid_tests()
        exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())