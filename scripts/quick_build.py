#!/usr/bin/env python3
"""
快速建置腳本 - 使用 pip 而非 poetry
"""

import subprocess
import sys
import os
from pathlib import Path


def main():
    """主函數"""
    print("🚀 Quick Docker Build Script")
    print("=" * 40)
    
    # 確保在正確的目錄
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    print(f"📁 Working directory: {project_root}")
    
    # 建置命令
    commands = [
        {
            "name": "Test Configuration",
            "cmd": ["docker-compose", "config", "--quiet"],
            "timeout": 30
        },
        {
            "name": "Build MCP Server",
            "cmd": ["docker-compose", "build", "--no-cache", "mcp-server"],
            "timeout": 600
        },
        {
            "name": "Build Vision Agent",
            "cmd": ["docker-compose", "build", "--no-cache", "vision-agent"],
            "timeout": 600
        },
        {
            "name": "Build Playwright Crawler",
            "cmd": ["docker-compose", "build", "--no-cache", "playwright-crawler-agent"],
            "timeout": 600
        }
    ]
    
    results = []
    
    for i, command in enumerate(commands, 1):
        print(f"\n{i}. {command['name']}")
        print("-" * 30)
        print(f"Command: {' '.join(command['cmd'])}")
        
        try:
            result = subprocess.run(
                command['cmd'],
                timeout=command['timeout'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ {command['name']} - SUCCESS")
                results.append(True)
            else:
                print(f"❌ {command['name']} - FAILED")
                print("Error output:")
                print(result.stderr)
                results.append(False)
                
        except subprocess.TimeoutExpired:
            print(f"❌ {command['name']} - TIMEOUT")
            results.append(False)
        except Exception as e:
            print(f"❌ {command['name']} - ERROR: {e}")
            results.append(False)
    
    # 總結
    print("\n" + "=" * 40)
    print("📊 Build Summary")
    print("=" * 40)
    
    successful = sum(results)
    total = len(results)
    
    for i, (command, success) in enumerate(zip(commands, results)):
        status = "✅" if success else "❌"
        print(f"{status} {command['name']}")
    
    print(f"\nResult: {successful}/{total} successful")
    
    if successful == total:
        print("\n🎉 All builds completed successfully!")
        print("\n📋 Next Steps:")
        print("1. Start infrastructure: docker-compose up -d postgres redis rustfs")
        print("2. Start MCP Server: docker-compose up -d mcp-server")
        print("3. Start Agents: docker-compose up -d vision-agent playwright-crawler-agent")
        print("4. Test integration: python test_agents_integration.py")
    else:
        print(f"\n⚠️ {total - successful} builds failed")
        print("Please check the error messages above")
    
    return successful == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)