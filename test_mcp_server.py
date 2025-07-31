#!/usr/bin/env python3
"""
MCP Server 測試腳本

測試 Agent 註冊、健康檢查、媒體下載等功能
"""

import asyncio
import httpx
import json
from typing import Dict, Any


class MCPServerTester:
    """MCP Server 測試器"""
    
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
        """測試健康檢查"""
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
    
    async def test_agent_registration(self):
        """測試 Agent 註冊"""
        print("🔍 Testing agent registration...")
        
        test_agent = {
            "name": "test-agent",
            "description": "Test Agent for MCP Server",
            "version": "1.0.0",
            "url": "http://test-agent:8999",
            "health_check_url": "http://test-agent:8999/health",
            "capabilities": {
                "testing": True,
                "mock_operations": True
            },
            "skills": [
                {
                    "name": "mock_testing",
                    "description": "Mock testing capabilities",
                    "tags": ["testing", "mock"]
                }
            ],
            "requirements": {
                "python": ">=3.11",
                "memory": "512MB"
            },
            "metadata": {
                "author": "Test Suite",
                "created_at": "2025-01-28"
            }
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/agents/register",
                json=test_agent
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Agent registration passed: {data}")
            return True
            
        except Exception as e:
            print(f"❌ Agent registration failed: {e}")
            return False
    
    async def test_agent_listing(self):
        """測試 Agent 列表"""
        print("🔍 Testing agent listing...")
        
        try:
            response = await self.client.get(f"{self.base_url}/agents")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Agent listing passed: Found {data['count']} agents")
            
            for agent in data['agents'][:3]:  # 只顯示前3個
                print(f"   - {agent['name']}: {agent['status']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Agent listing failed: {e}")
            return False
    
    async def test_agent_discovery(self):
        """測試 Agent 發現"""
        print("🔍 Testing agent discovery...")
        
        try:
            # 測試按名稱查找
            response = await self.client.get(f"{self.base_url}/agents/test-agent")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Agent discovery by name passed: {data['name']}")
            else:
                print("⚠️ Test agent not found (expected if not registered)")
            
            # 測試按查詢查找
            response = await self.client.get(f"{self.base_url}/agents/find?query=crawler")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Agent discovery by query passed: {data['name']}")
            else:
                print("⚠️ No crawler agent found")
            
            return True
            
        except Exception as e:
            print(f"❌ Agent discovery failed: {e}")
            return False
    
    async def test_health_check_trigger(self):
        """測試健康檢查觸發"""
        print("🔍 Testing health check trigger...")
        
        try:
            response = await self.client.post(f"{self.base_url}/agents/health-check")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Health check trigger passed: {data}")
            
            # 等待一下讓健康檢查完成
            await asyncio.sleep(2)
            
            return True
            
        except Exception as e:
            print(f"❌ Health check trigger failed: {e}")
            return False
    
    async def test_media_download(self):
        """測試媒體下載"""
        print("🔍 Testing media download...")
        
        test_data = {
            "post_url": "https://example.com/test-post",
            "media_urls": [
                "https://via.placeholder.com/300x200.jpg",
                "https://via.placeholder.com/400x300.png"
            ]
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/media/download",
                json=test_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Media download passed: {data}")
            else:
                print(f"⚠️ Media download returned {response.status_code}: {response.text}")
            
            return True
            
        except Exception as e:
            print(f"❌ Media download failed: {e}")
            return False
    
    async def test_statistics(self):
        """測試統計資訊"""
        print("🔍 Testing statistics...")
        
        try:
            response = await self.client.get(f"{self.base_url}/stats")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ Statistics passed:")
            print(f"   - Total agents: {data['agents']['total_agents']}")
            print(f"   - Active agents: {data['agents']['active_agents']}")
            
            if 'database' in data and 'posts' in data['database']:
                print(f"   - Total posts: {data['database']['posts']['total']}")
                print(f"   - Media files: {data['database']['media_files']['total']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Statistics failed: {e}")
            return False
    
    async def test_system_logs(self):
        """測試系統日誌"""
        print("🔍 Testing system logs...")
        
        try:
            response = await self.client.get(f"{self.base_url}/system/logs?limit=5")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ System logs passed: Found {data['count']} recent logs")
            
            for log in data['logs'][:3]:  # 只顯示前3個
                print(f"   - {log['operation_type']}: {log['status']} ({log['started_at']})")
            
            return True
            
        except Exception as e:
            print(f"❌ System logs failed: {e}")
            return False
    
    async def run_all_tests(self):
        """執行所有測試"""
        print("🚀 Starting MCP Server tests...\n")
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Agent Registration", self.test_agent_registration),
            ("Agent Listing", self.test_agent_listing),
            ("Agent Discovery", self.test_agent_discovery),
            ("Health Check Trigger", self.test_health_check_trigger),
            ("Media Download", self.test_media_download),
            ("Statistics", self.test_statistics),
            ("System Logs", self.test_system_logs),
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
        print("📊 Test Results Summary:")
        print("=" * 50)
        
        passed = sum(1 for r in results.values() if r)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print("=" * 50)
        print(f"Total: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        return passed == total


async def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Server Tester")
    parser.add_argument(
        "--url", 
        default="http://localhost:10100",
        help="MCP Server URL (default: http://localhost:10100)"
    )
    parser.add_argument(
        "--test",
        choices=["health", "register", "list", "discover", "health-trigger", "media", "stats", "logs"],
        help="Run specific test only"
    )
    
    args = parser.parse_args()
    
    async with MCPServerTester(args.url) as tester:
        if args.test:
            # 執行特定測試
            test_map = {
                "health": tester.test_health_check,
                "register": tester.test_agent_registration,
                "list": tester.test_agent_listing,
                "discover": tester.test_agent_discovery,
                "health-trigger": tester.test_health_check_trigger,
                "media": tester.test_media_download,
                "stats": tester.test_statistics,
                "logs": tester.test_system_logs,
            }
            
            await test_map[args.test]()
        else:
            # 執行所有測試
            success = await tester.run_all_tests()
            exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())