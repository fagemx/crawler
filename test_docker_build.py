#!/usr/bin/env python3
"""
Docker 建置測試腳本

測試 MCP Server 和 Agents 的 Docker 建置
"""

import subprocess
import sys
import time
from pathlib import Path


class DockerBuildTester:
    """Docker 建置測試器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.services = [
            "mcp-server",
            "vision-agent", 
            "playwright-crawler-agent"
        ]
    
    def run_command(self, command: list, description: str) -> bool:
        """執行命令並返回結果"""
        print(f"🔧 {description}...")
        print(f"   Command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10分鐘超時
            )
            
            if result.returncode == 0:
                print(f"✅ {description} - SUCCESS")
                return True
            else:
                print(f"❌ {description} - FAILED")
                print(f"   Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ {description} - TIMEOUT (10 minutes)")
            return False
        except Exception as e:
            print(f"❌ {description} - ERROR: {e}")
            return False
    
    def test_docker_compose_config(self) -> bool:
        """測試 docker-compose 配置"""
        return self.run_command(
            ["docker-compose", "config"],
            "Testing docker-compose configuration"
        )
    
    def build_service(self, service: str, no_cache: bool = True) -> bool:
        """建置特定服務"""
        command = ["docker-compose", "build"]
        if no_cache:
            command.append("--no-cache")
        command.append(service)
        
        return self.run_command(
            command,
            f"Building {service}"
        )
    
    def test_service_health(self, service: str, port: int) -> bool:
        """測試服務健康狀態"""
        print(f"🔍 Testing {service} health on port {port}...")
        
        # 啟動服務
        start_result = self.run_command(
            ["docker-compose", "up", "-d", service],
            f"Starting {service}"
        )
        
        if not start_result:
            return False
        
        # 等待服務啟動
        print(f"   Waiting for {service} to start...")
        time.sleep(10)
        
        # 檢查健康狀態
        health_result = self.run_command(
            ["curl", "-f", f"http://localhost:{port}/health"],
            f"Checking {service} health"
        )
        
        # 停止服務
        self.run_command(
            ["docker-compose", "down", service],
            f"Stopping {service}"
        )
        
        return health_result
    
    def run_build_tests(self) -> dict:
        """執行建置測試"""
        print("🚀 Starting Docker Build Tests")
        print("=" * 60)
        
        results = {}
        
        # 1. 測試 docker-compose 配置
        print("\n1. Testing Docker Compose Configuration")
        print("-" * 40)
        results["config"] = self.test_docker_compose_config()
        
        # 2. 建置各個服務
        print("\n2. Building Services")
        print("-" * 40)
        
        for service in self.services:
            print(f"\n📦 Building {service}...")
            results[f"build_{service}"] = self.build_service(service)
        
        # 3. 測試服務健康狀態（可選）
        print("\n3. Testing Service Health (Optional)")
        print("-" * 40)
        
        service_ports = {
            "mcp-server": 10100,
            "vision-agent": 8005,
            "playwright-crawler-agent": 8006
        }
        
        for service, port in service_ports.items():
            if results.get(f"build_{service}", False):
                print(f"\n🏥 Testing {service} health...")
                results[f"health_{service}"] = self.test_service_health(service, port)
            else:
                print(f"⏭️ Skipping {service} health test (build failed)")
                results[f"health_{service}"] = False
        
        return results
    
    def print_summary(self, results: dict):
        """打印測試總結"""
        print("\n" + "=" * 60)
        print("📊 Docker Build Test Summary")
        print("=" * 60)
        
        # 分類結果
        config_tests = {k: v for k, v in results.items() if k == "config"}
        build_tests = {k: v for k, v in results.items() if k.startswith("build_")}
        health_tests = {k: v for k, v in results.items() if k.startswith("health_")}
        
        # 配置測試
        print("\n🔧 Configuration Tests:")
        for test, result in config_tests.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} {test}")
        
        # 建置測試
        print("\n📦 Build Tests:")
        for test, result in build_tests.items():
            service = test.replace("build_", "")
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} {service}")
        
        # 健康檢查測試
        print("\n🏥 Health Tests:")
        for test, result in health_tests.items():
            service = test.replace("health_", "")
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} {service}")
        
        # 總體統計
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        
        print(f"\n📈 Overall Results:")
        print(f"   Total tests: {total_tests}")
        print(f"   Passed: {passed_tests}")
        print(f"   Failed: {total_tests - passed_tests}")
        print(f"   Success rate: {passed_tests/total_tests*100:.1f}%")
        
        # 建議
        print(f"\n💡 Recommendations:")
        if passed_tests == total_tests:
            print("   🎉 All tests passed! Ready for deployment.")
        elif passed_tests >= total_tests * 0.8:
            print("   ⚠️ Most tests passed. Check failed tests and fix issues.")
        else:
            print("   ❌ Many tests failed. Review Docker configuration and dependencies.")
        
        print("=" * 60)
        
        return passed_tests == total_tests


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Docker Build Tester")
    parser.add_argument(
        "--service",
        choices=["mcp-server", "vision-agent", "playwright-crawler-agent"],
        help="Test specific service only"
    )
    parser.add_argument(
        "--no-health",
        action="store_true",
        help="Skip health tests"
    )
    
    args = parser.parse_args()
    
    tester = DockerBuildTester()
    
    if args.service:
        # 測試特定服務
        print(f"🎯 Testing specific service: {args.service}")
        
        results = {}
        results["config"] = tester.test_docker_compose_config()
        results[f"build_{args.service}"] = tester.build_service(args.service)
        
        if not args.no_health and results[f"build_{args.service}"]:
            service_ports = {
                "mcp-server": 10100,
                "vision-agent": 8005,
                "playwright-crawler-agent": 8006
            }
            port = service_ports[args.service]
            results[f"health_{args.service}"] = tester.test_service_health(args.service, port)
        
        success = tester.print_summary(results)
    else:
        # 測試所有服務
        results = tester.run_build_tests()
        success = tester.print_summary(results)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()