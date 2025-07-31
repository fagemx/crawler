#!/usr/bin/env python3
"""
整合系統啟動腳本

按正確順序啟動 MCP Server 和 Agents
"""

import asyncio
import subprocess
import time
import sys
import os
from pathlib import Path
import httpx

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class IntegratedSystemStarter:
    """整合系統啟動器"""
    
    def __init__(self):
        self.processes = {}
        self.base_urls = {
            "mcp_server": "http://localhost:10100",
            "playwright_crawler": "http://localhost:8006",
            "vision_agent": "http://localhost:8005"
        }
    
    async def check_service_health(self, name: str, url: str, max_retries: int = 30) -> bool:
        """檢查服務健康狀態"""
        print(f"🔍 Checking {name} health at {url}...")
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{url}/health")
                    if response.status_code == 200:
                        print(f"✅ {name} is healthy")
                        return True
            except Exception:
                pass
            
            if attempt < max_retries - 1:
                print(f"   Attempt {attempt + 1}/{max_retries} failed, retrying in 2s...")
                await asyncio.sleep(2)
        
        print(f"❌ {name} health check failed after {max_retries} attempts")
        return False
    
    def start_service(self, name: str, command: list, cwd: str = None) -> subprocess.Popen:
        """啟動服務"""
        print(f"🚀 Starting {name}...")
        
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd or str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[name] = process
            print(f"✅ {name} started with PID {process.pid}")
            return process
            
        except Exception as e:
            print(f"❌ Failed to start {name}: {e}")
            return None
    
    def stop_all_services(self):
        """停止所有服務"""
        print("\n🛑 Stopping all services...")
        
        for name, process in self.processes.items():
            if process and process.poll() is None:
                print(f"   Stopping {name} (PID {process.pid})...")
                process.terminate()
                
                # 等待最多5秒讓進程正常結束
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"   Force killing {name}...")
                    process.kill()
        
        self.processes.clear()
        print("✅ All services stopped")
    
    async def start_mcp_server(self) -> bool:
        """啟動 MCP Server"""
        print("=" * 50)
        print("Starting MCP Server")
        print("=" * 50)
        
        # 啟動 MCP Server
        process = self.start_service(
            "MCP Server",
            [sys.executable, "-m", "mcp_server.main"]
        )
        
        if not process:
            return False
        
        # 等待服務健康
        return await self.check_service_health("MCP Server", self.base_urls["mcp_server"])
    
    async def start_agents(self) -> dict:
        """啟動所有 Agents"""
        print("=" * 50)
        print("Starting Agents")
        print("=" * 50)
        
        results = {}
        
        # 啟動 Playwright Crawler Agent
        print("\n📱 Starting Playwright Crawler Agent...")
        playwright_process = self.start_service(
            "Playwright Crawler",
            [sys.executable, "-m", "agents.playwright_crawler.main"]
        )
        
        if playwright_process:
            results["playwright_crawler"] = await self.check_service_health(
                "Playwright Crawler", 
                self.base_urls["playwright_crawler"]
            )
        else:
            results["playwright_crawler"] = False
        
        # 啟動 Vision Agent
        print("\n👁️ Starting Vision Agent...")
        vision_process = self.start_service(
            "Vision Agent",
            [sys.executable, "-m", "agents.vision.main"]
        )
        
        if vision_process:
            results["vision_agent"] = await self.check_service_health(
                "Vision Agent", 
                self.base_urls["vision_agent"]
            )
        else:
            results["vision_agent"] = False
        
        return results
    
    async def verify_integration(self) -> bool:
        """驗證整合狀態"""
        print("=" * 50)
        print("Verifying Integration")
        print("=" * 50)
        
        try:
            # 等待一下讓 Agents 完成註冊
            print("⏳ Waiting for agent registration...")
            await asyncio.sleep(5)
            
            # 檢查 MCP Server 中的 Agent 列表
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_urls['mcp_server']}/agents")
                response.raise_for_status()
                
                agents = response.json()
                agent_names = [agent["name"] for agent in agents]
                online_agents = [agent for agent in agents if agent.get("status") == "ONLINE"]
                
                print(f"📊 Integration Status:")
                print(f"   - Total registered agents: {len(agents)}")
                print(f"   - Online agents: {len(online_agents)}")
                print(f"   - Agent names: {agent_names}")
                
                # 檢查預期的 Agents
                expected_agents = ["playwright-crawler", "vision"]
                found_agents = [name for name in expected_agents if name in agent_names]
                
                print(f"   - Expected agents: {expected_agents}")
                print(f"   - Found agents: {found_agents}")
                
                if len(found_agents) >= 1:
                    print("✅ Integration verification passed")
                    return True
                else:
                    print("❌ Integration verification failed - no expected agents found")
                    return False
                    
        except Exception as e:
            print(f"❌ Integration verification failed: {e}")
            return False
    
    async def run_integration_test(self) -> bool:
        """執行整合測試"""
        print("=" * 50)
        print("Running Integration Test")
        print("=" * 50)
        
        try:
            # 執行整合測試腳本
            test_process = subprocess.run([
                sys.executable, "test_agents_integration.py"
            ], cwd=str(project_root), capture_output=True, text=True, timeout=120)
            
            print("Integration Test Output:")
            print("-" * 30)
            print(test_process.stdout)
            
            if test_process.stderr:
                print("Integration Test Errors:")
                print("-" * 30)
                print(test_process.stderr)
            
            success = test_process.returncode == 0
            
            if success:
                print("✅ Integration test passed")
            else:
                print("❌ Integration test failed")
            
            return success
            
        except subprocess.TimeoutExpired:
            print("❌ Integration test timed out")
            return False
        except Exception as e:
            print(f"❌ Integration test failed: {e}")
            return False
    
    async def start_system(self, run_tests: bool = True) -> bool:
        """啟動完整系統"""
        print("🚀 Starting Integrated Social Media Content Generator System")
        print("=" * 70)
        
        try:
            # 1. 啟動 MCP Server
            mcp_success = await self.start_mcp_server()
            if not mcp_success:
                print("❌ Failed to start MCP Server")
                return False
            
            # 2. 啟動 Agents
            agent_results = await self.start_agents()
            successful_agents = sum(1 for success in agent_results.values() if success)
            
            print(f"\n📊 Agent Startup Summary:")
            for agent, success in agent_results.items():
                status = "✅" if success else "❌"
                print(f"   {status} {agent}")
            
            if successful_agents == 0:
                print("❌ No agents started successfully")
                return False
            
            # 3. 驗證整合
            integration_success = await self.verify_integration()
            if not integration_success:
                print("❌ Integration verification failed")
                return False
            
            # 4. 執行整合測試（可選）
            if run_tests:
                test_success = await self.run_integration_test()
                if not test_success:
                    print("⚠️ Integration tests failed, but system is running")
            
            # 5. 顯示系統狀態
            print("\n" + "=" * 70)
            print("🎉 System Started Successfully!")
            print("=" * 70)
            print(f"MCP Server:          {self.base_urls['mcp_server']}")
            print(f"Playwright Crawler:  {self.base_urls['playwright_crawler']}")
            print(f"Vision Agent:        {self.base_urls['vision_agent']}")
            print()
            print("API Documentation:")
            print(f"- MCP Server:        {self.base_urls['mcp_server']}/docs")
            print(f"- Playwright:        {self.base_urls['playwright_crawler']}/docs")
            print(f"- Vision:            {self.base_urls['vision_agent']}/docs")
            print()
            print("Monitoring:")
            print(f"- System Stats:      {self.base_urls['mcp_server']}/stats")
            print(f"- Agent List:        {self.base_urls['mcp_server']}/agents")
            print(f"- Operation Logs:    {self.base_urls['mcp_server']}/system/logs")
            print("=" * 70)
            
            return True
            
        except KeyboardInterrupt:
            print("\n🛑 Startup interrupted by user")
            return False
        except Exception as e:
            print(f"❌ System startup failed: {e}")
            return False
    
    async def run_interactive_mode(self):
        """執行互動模式"""
        print("\n🎮 Interactive Mode")
        print("Commands: status, test, logs, stop, help")
        
        while True:
            try:
                command = input("\n> ").strip().lower()
                
                if command == "status":
                    await self.show_system_status()
                elif command == "test":
                    await self.run_integration_test()
                elif command == "logs":
                    await self.show_recent_logs()
                elif command == "stop":
                    break
                elif command == "help":
                    print("Available commands:")
                    print("  status - Show system status")
                    print("  test   - Run integration tests")
                    print("  logs   - Show recent operation logs")
                    print("  stop   - Stop the system")
                    print("  help   - Show this help")
                else:
                    print(f"Unknown command: {command}")
                    
            except KeyboardInterrupt:
                break
            except EOFError:
                break
    
    async def show_system_status(self):
        """顯示系統狀態"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_urls['mcp_server']}/stats")
                response.raise_for_status()
                
                data = response.json()
                agent_stats = data.get("agents", {})
                
                print("📊 System Status:")
                print(f"   Total agents: {agent_stats.get('total', 0)}")
                print(f"   Online agents: {agent_stats.get('online', 0)}")
                
                by_role = agent_stats.get("by_role", {})
                for role, stats in by_role.items():
                    print(f"   {role}: {stats.get('online', 0)}/{stats.get('total', 0)}")
                    
        except Exception as e:
            print(f"❌ Failed to get system status: {e}")
    
    async def show_recent_logs(self):
        """顯示最近的日誌"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_urls['mcp_server']}/system/logs?limit=10")
                response.raise_for_status()
                
                data = response.json()
                logs = data.get("logs", [])
                
                print("📝 Recent Operation Logs:")
                for log in logs:
                    timestamp = log.get("timestamp", "")[:19]  # 只顯示日期時間部分
                    operation = log.get("operation_type", "")
                    status = log.get("status", "")
                    agent = log.get("agent", "system")
                    
                    status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
                    print(f"   {status_icon} {timestamp} [{agent}] {operation} - {status}")
                    
        except Exception as e:
            print(f"❌ Failed to get recent logs: {e}")


async def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Integrated System Starter")
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip integration tests"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode after startup"
    )
    
    args = parser.parse_args()
    
    starter = IntegratedSystemStarter()
    
    try:
        # 啟動系統
        success = await starter.start_system(run_tests=not args.no_tests)
        
        if not success:
            print("❌ System startup failed")
            exit(1)
        
        # 互動模式或等待中斷
        if args.interactive:
            await starter.run_interactive_mode()
        else:
            print("\n⏳ System running... Press Ctrl+C to stop")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
    
    finally:
        starter.stop_all_services()


if __name__ == "__main__":
    asyncio.run(main())