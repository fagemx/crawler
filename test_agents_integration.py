#!/usr/bin/env python3
"""
Agents MCP 整合測試腳本

測試 playwright_crawler 和 vision agents 與 MCP Server 的整合
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any


class AgentsIntegrationTester:
    """Agents MCP 整合測試器"""
    
    def __init__(
        self,
        mcp_url: str = "http://localhost:10100",
        playwright_url: str = "http://localhost:8006",
        vision_url: str = "http://localhost:8005"
    ):
        self.mcp_url = mcp_url
        self.playwright_url = playwright_url
        self.vision_url = vision_url
        self.client = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def test_mcp_server_health(self):
        """測試 MCP Server 健康狀態"""
        print("🔍 Testing MCP Server health...")
        
        try:
            response = await self.client.get(f"{self.mcp_url}/health")
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ MCP Server health: {data}")
            return True
            
        except Exception as e:
            print(f"❌ MCP Server health check failed: {e}")
            return False
    
    async def test_agents_health(self):
        """測試 Agents 健康狀態"""
        print("🔍 Testing Agents health...")
        
        results = {}
        
        # 測試 Playwright Crawler
        try:
            response = await self.client.get(f"{self.playwright_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Playwright Crawler health: {data}")
                results["playwright"] = True
            else:
                print(f"⚠️ Playwright Crawler returned {response.status_code}")
                results["playwright"] = False
        except Exception as e:
            print(f"❌ Playwright Crawler health failed: {e}")
            results["playwright"] = False
        
        # 測試 Vision Agent
        try:
            response = await self.client.get(f"{self.vision_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Vision Agent health: {data}")
                results["vision"] = True
            else:
                print(f"⚠️ Vision Agent returned {response.status_code}")
                results["vision"] = False
        except Exception as e:
            print(f"❌ Vision Agent health failed: {e}")
            results["vision"] = False
        
        return all(results.values())
    
    async def test_agent_registration(self):
        """測試 Agent 自動註冊"""
        print("🔍 Testing Agent auto-registration...")
        
        try:
            # 等待一下讓 Agent 完成註冊
            await asyncio.sleep(2)
            
            # 檢查 MCP Server 中的 Agent 列表
            response = await self.client.get(f"{self.mcp_url}/agents")
            response.raise_for_status()
            
            agents = response.json()
            agent_names = [agent["name"] for agent in agents]
            
            print(f"✅ Registered agents: {agent_names}")
            
            # 檢查是否包含我們的 Agent
            expected_agents = ["playwright-crawler", "vision"]
            found_agents = [name for name in expected_agents if name in agent_names]
            
            print(f"   Expected: {expected_agents}")
            print(f"   Found: {found_agents}")
            
            return len(found_agents) >= 1  # 至少找到一個
            
        except Exception as e:
            print(f"❌ Agent registration test failed: {e}")
            return False
    
    async def test_agent_discovery(self):
        """測試 Agent 間的服務發現"""
        print("🔍 Testing Agent service discovery...")
        
        results = {}
        
        # 測試 Playwright Crawler 的服務發現
        try:
            response = await self.client.get(f"{self.playwright_url}/mcp/discover")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Playwright discovered: {data.get('total_discovered', 0)} agents")
                results["playwright_discovery"] = True
            else:
                print(f"⚠️ Playwright discovery returned {response.status_code}")
                results["playwright_discovery"] = False
        except Exception as e:
            print(f"❌ Playwright discovery failed: {e}")
            results["playwright_discovery"] = False
        
        # 測試 Vision Agent 的服務發現
        try:
            response = await self.client.get(f"{self.vision_url}/mcp/discover")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Vision discovered: {data.get('total_discovered', 0)} agents")
                results["vision_discovery"] = True
            else:
                print(f"⚠️ Vision discovery returned {response.status_code}")
                results["vision_discovery"] = False
        except Exception as e:
            print(f"❌ Vision discovery failed: {e}")
            results["vision_discovery"] = False
        
        return any(results.values())  # 至少一個成功
    
    async def test_agent_capabilities(self):
        """測試 Agent 能力查詢"""
        print("🔍 Testing Agent capabilities...")
        
        results = {}
        
        # 測試 Playwright Crawler 能力
        try:
            response = await self.client.get(f"{self.playwright_url}/mcp/capabilities")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Playwright capabilities: {list(data.keys())}")
                results["playwright_capabilities"] = True
            else:
                results["playwright_capabilities"] = False
        except Exception as e:
            print(f"❌ Playwright capabilities failed: {e}")
            results["playwright_capabilities"] = False
        
        # 測試 Vision Agent 能力
        try:
            response = await self.client.get(f"{self.vision_url}/mcp/capabilities")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Vision capabilities: {list(data.keys())}")
                results["vision_capabilities"] = True
            else:
                results["vision_capabilities"] = False
        except Exception as e:
            print(f"❌ Vision capabilities failed: {e}")
            results["vision_capabilities"] = False
        
        return any(results.values())
    
    async def test_media_download_integration(self):
        """測試媒體下載整合"""
        print("🔍 Testing media download integration...")
        
        try:
            # 測試 Playwright Crawler 請求媒體下載
            test_data = {
                "post_url": "https://example.com/integration-test-post",
                "media_urls": [
                    "https://via.placeholder.com/400x300.jpg",
                    "https://via.placeholder.com/600x400.png"
                ]
            }
            
            response = await self.client.post(
                f"{self.playwright_url}/mcp/request-media-download",
                params=test_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Media download integration: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"⚠️ Media download returned {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Media download integration failed: {e}")
            return False
    
    async def test_vision_media_analysis(self):
        """測試 Vision Agent 媒體分析整合"""
        print("🔍 Testing Vision Agent media analysis integration...")
        
        try:
            # 測試 Vision Agent 請求媒體分析
            test_data = {
                "post_url": "https://example.com/integration-test-post",
                "analysis_type": "metrics_extraction"
            }
            
            response = await self.client.post(
                f"{self.vision_url}/mcp/request-media-analysis",
                params=test_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Vision media analysis: {data.get('status', 'unknown')}")
                
                if data.get("status") == "no_media":
                    print("   (No media found - expected for test)")
                    return True
                elif data.get("status") == "analysis_ready":
                    print(f"   Found {data.get('analyzable_files', 0)} analyzable files")
                    return True
                
                return True
            else:
                print(f"⚠️ Vision analysis returned {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Vision media analysis failed: {e}")
            return False
    
    async def test_heartbeat_mechanism(self):
        """測試心跳機制"""
        print("🔍 Testing heartbeat mechanism...")
        
        try:
            # 等待一下讓心跳發送
            await asyncio.sleep(5)
            
            # 檢查 Agent 狀態
            response = await self.client.get(f"{self.mcp_url}/agents")
            response.raise_for_status()
            
            agents = response.json()
            online_agents = [agent for agent in agents if agent.get("status") == "ONLINE"]
            
            print(f"✅ Heartbeat mechanism: {len(online_agents)} agents online")
            
            for agent in online_agents:
                if agent["name"] in ["playwright-crawler", "vision"]:
                    print(f"   - {agent['name']}: {agent['status']} (last: {agent.get('last_heartbeat', 'unknown')})")
            
            return len(online_agents) > 0
            
        except Exception as e:
            print(f"❌ Heartbeat mechanism test failed: {e}")
            return False
    
    async def test_mcp_statistics(self):
        """測試 MCP 統計資訊"""
        print("🔍 Testing MCP statistics...")
        
        try:
            response = await self.client.get(f"{self.mcp_url}/stats")
            response.raise_for_status()
            
            data = response.json()
            agent_stats = data.get("agents", {})
            
            print(f"✅ MCP Statistics:")
            print(f"   - Total agents: {agent_stats.get('total', 0)}")
            print(f"   - Online agents: {agent_stats.get('online', 0)}")
            
            # 按角色統計
            by_role = agent_stats.get("by_role", {})
            for role, stats in by_role.items():
                if role in ["playwright-crawler", "vision"]:
                    print(f"   - {role}: {stats.get('online', 0)}/{stats.get('total', 0)} online")
            
            return True
            
        except Exception as e:
            print(f"❌ MCP statistics test failed: {e}")
            return False
    
    async def run_integration_tests(self):
        """執行完整的整合測試"""
        print("🚀 Starting Agents MCP Integration Tests...\n")
        
        tests = [
            ("MCP Server Health", self.test_mcp_server_health),
            ("Agents Health", self.test_agents_health),
            ("Agent Registration", self.test_agent_registration),
            ("Agent Discovery", self.test_agent_discovery),
            ("Agent Capabilities", self.test_agent_capabilities),
            ("Media Download Integration", self.test_media_download_integration),
            ("Vision Media Analysis", self.test_vision_media_analysis),
            ("Heartbeat Mechanism", self.test_heartbeat_mechanism),
            ("MCP Statistics", self.test_mcp_statistics),
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
        print("📊 Integration Test Results:")
        print("=" * 70)
        
        passed = sum(1 for r in results.values() if r)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print("=" * 70)
        print(f"Total: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        # 整合評估
        print("\n🎯 Integration Assessment:")
        print("=" * 70)
        
        core_tests = ["MCP Server Health", "Agents Health", "Agent Registration"]
        core_passed = sum(1 for test in core_tests if results.get(test, False))
        
        integration_tests = ["Agent Discovery", "Media Download Integration", "Vision Media Analysis"]
        integration_passed = sum(1 for test in integration_tests if results.get(test, False))
        
        monitoring_tests = ["Heartbeat Mechanism", "MCP Statistics"]
        monitoring_passed = sum(1 for test in monitoring_tests if results.get(test, False))
        
        print(f"Core Functionality: {core_passed}/{len(core_tests)} ✅")
        print(f"Integration Features: {integration_passed}/{len(integration_tests)} ✅")
        print(f"Monitoring & Stats: {monitoring_passed}/{len(monitoring_tests)} ✅")
        
        if passed >= total * 0.8:
            print("\n🎉 Agents are successfully integrated with MCP Server!")
            print("Ready for production workflow.")
        elif passed >= total * 0.6:
            print("\n⚠️ Integration mostly working but needs some fixes.")
        else:
            print("\n❌ Integration needs significant work.")
        
        return passed == total


async def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agents MCP Integration Tester")
    parser.add_argument(
        "--mcp-url", 
        default="http://localhost:10100",
        help="MCP Server URL"
    )
    parser.add_argument(
        "--playwright-url", 
        default="http://localhost:8006",
        help="Playwright Crawler Agent URL"
    )
    parser.add_argument(
        "--vision-url", 
        default="http://localhost:8005",
        help="Vision Agent URL"
    )
    
    args = parser.parse_args()
    
    async with AgentsIntegrationTester(args.mcp_url, args.playwright_url, args.vision_url) as tester:
        success = await tester.run_integration_tests()
        exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())