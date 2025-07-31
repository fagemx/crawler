#!/usr/bin/env python3
"""
簡化的 Docker 建置測試腳本
"""

import subprocess
import sys
import time
from pathlib import Path


def run_command(command: list, description: str, timeout: int = 300) -> bool:
    """執行命令並返回結果"""
    print(f"🔧 {description}...")
    print(f"   Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            return True
        else:
            print(f"❌ {description} - FAILED")
            print(f"   Error: {result.stderr}")
            if result.stdout:
                print(f"   Output: {result.stdout}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ {description} - TIMEOUT ({timeout}s)")
        return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False


def test_docker_config():
    """測試 docker-compose 配置"""
    return run_command(
        ["docker-compose", "config", "--quiet"],
        "Testing docker-compose configuration",
        30
    )


def build_service(service: str):
    """建置服務"""
    return run_command(
        ["docker-compose", "build", "--no-cache", service],
        f"Building {service}",
        600  # 10分鐘
    )


def main():
    """主函數"""
    print("🚀 Simple Docker Build Test")
    print("=" * 50)
    
    # 1. 測試配置
    print("\n1. Testing Configuration")
    print("-" * 30)
    if not test_docker_config():
        print("❌ Configuration test failed, stopping")
        return False
    
    # 2. 建置服務
    services = ["mcp-server", "vision-agent", "playwright-crawler-agent"]
    results = {}
    
    print("\n2. Building Services")
    print("-" * 30)
    
    for service in services:
        print(f"\n📦 Building {service}...")
        results[service] = build_service(service)
        
        if results[service]:
            print(f"✅ {service} build completed")
        else:
            print(f"❌ {service} build failed")
    
    # 3. 總結
    print("\n" + "=" * 50)
    print("📊 Build Results Summary")
    print("=" * 50)
    
    successful = sum(1 for success in results.values() if success)
    total = len(results)
    
    for service, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{status} {service}")
    
    print(f"\nOverall: {successful}/{total} services built successfully")
    
    if successful == total:
        print("\n🎉 All services built successfully!")
        print("\nNext steps:")
        print("1. docker-compose up -d postgres redis rustfs")
        print("2. docker-compose up -d mcp-server")
        print("3. docker-compose up -d vision-agent playwright-crawler-agent")
        print("4. python test_agents_integration.py")
    else:
        print(f"\n⚠️ {total - successful} services failed to build")
        print("Please check the error messages above and fix the issues")
    
    return successful == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)