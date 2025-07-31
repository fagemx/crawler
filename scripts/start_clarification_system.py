#!/usr/bin/env python3
"""
啟動澄清系統的腳本
"""

import subprocess
import time
import sys
import os

def run_command(command, description):
    """執行命令並顯示結果"""
    print(f"🚀 {description}")
    print(f"執行命令: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} 成功")
        if result.stdout:
            print(f"輸出: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失敗")
        print(f"錯誤: {e.stderr}")
        return False

def main():
    print("🎯 啟動社交媒體內容生成器 - 澄清系統")
    print("=" * 60)
    
    # 檢查 Docker 是否運行
    if not run_command("docker --version", "檢查 Docker"):
        print("請確保 Docker 已安裝並運行")
        sys.exit(1)
    
    # 檢查 Docker Compose 是否可用
    if not run_command("docker-compose --version", "檢查 Docker Compose"):
        print("請確保 Docker Compose 已安裝")
        sys.exit(1)
    
    print("\n📋 啟動核心服務...")
    
    # 啟動基礎設施服務
    services_to_start = [
        "postgres",
        "redis", 
        "rustfs",
        "mcp-server",
        "orchestrator-agent",
        "clarification-agent", 
        "content-writer-agent",
        "form-api",
        "streamlit-ui"
    ]
    
    for service in services_to_start:
        print(f"\n🔧 啟動 {service}...")
        if not run_command(f"docker-compose up -d {service}", f"啟動 {service}"):
            print(f"⚠️ {service} 啟動失敗，但繼續啟動其他服務")
        time.sleep(2)  # 等待服務啟動
    
    print("\n⏳ 等待服務完全啟動...")
    time.sleep(10)
    
    # 檢查服務狀態
    print("\n📊 檢查服務狀態...")
    run_command("docker-compose ps", "查看服務狀態")
    
    print("\n🎉 系統啟動完成！")
    print("\n📍 服務端點:")
    print("- Streamlit UI: http://localhost:8501")
    print("- Orchestrator: http://localhost:8000")
    print("- Form API: http://localhost:8010")
    print("- Clarification Agent: http://localhost:8004")
    print("- Content Writer: http://localhost:8003")
    print("- MCP Server: http://localhost:10100")
    
    print("\n🧪 測試建議:")
    print("1. 打開瀏覽器訪問 http://localhost:8501")
    print("2. 或運行測試腳本: python test_clarification_system.py")
    
    print("\n📝 日誌查看:")
    print("- 查看所有日誌: docker-compose logs -f")
    print("- 查看特定服務: docker-compose logs -f [service-name]")

if __name__ == "__main__":
    main()