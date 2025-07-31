#!/usr/bin/env python3
"""
只啟動澄清系統相關的核心服務
"""

import subprocess
import time
import sys

def run_command(command, description):
    """執行命令並顯示結果"""
    print(f"🚀 {description}")
    print(f"執行命令: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} 成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失敗")
        print(f"錯誤: {e.stderr}")
        return False

def main():
    print("🎯 啟動澄清系統核心服務")
    print("=" * 50)
    
    # 核心服務列表
    core_services = [
        "postgres",
        "redis", 
        "mcp-server",
        "orchestrator-agent",
        "clarification-agent", 
        "content-writer-agent",
        "form-api",
        "streamlit-ui"
    ]
    
    print("📋 將啟動以下服務:")
    for service in core_services:
        print(f"  - {service}")
    
    print("\n🔧 開始啟動服務...")
    
    # 先啟動基礎設施
    infrastructure = ["postgres", "redis"]
    for service in infrastructure:
        print(f"\n🏗️ 啟動基礎設施: {service}")
        if not run_command(f"docker-compose up -d {service}", f"啟動 {service}"):
            print(f"⚠️ {service} 啟動失敗")
        time.sleep(3)
    
    # 等待基礎設施就緒
    print("\n⏳ 等待基礎設施就緒...")
    time.sleep(10)
    
    # 啟動 MCP Server
    print(f"\n🎯 啟動 MCP Server")
    if not run_command("docker-compose up -d mcp-server", "啟動 MCP Server"):
        print("⚠️ MCP Server 啟動失敗")
    time.sleep(5)
    
    # 啟動應用服務
    app_services = ["orchestrator-agent", "clarification-agent", "content-writer-agent", "form-api"]
    for service in app_services:
        print(f"\n🤖 啟動應用服務: {service}")
        if not run_command(f"docker-compose up -d {service}", f"啟動 {service}"):
            print(f"⚠️ {service} 啟動失敗，但繼續啟動其他服務")
        time.sleep(3)
    
    # 最後啟動 UI
    print(f"\n🖥️ 啟動 Streamlit UI")
    if not run_command("docker-compose up -d streamlit-ui", "啟動 Streamlit UI"):
        print("⚠️ Streamlit UI 啟動失敗")
    
    print("\n⏳ 等待所有服務完全啟動...")
    time.sleep(15)
    
    # 檢查服務狀態
    print("\n📊 檢查服務狀態...")
    run_command("docker-compose ps", "查看服務狀態")
    
    print("\n🎉 澄清系統啟動完成！")
    print("\n📍 服務端點:")
    print("- 🖥️  Streamlit UI: http://localhost:8501")
    print("- 🎯 Orchestrator: http://localhost:8000/health")
    print("- ❓ Clarification Agent: http://localhost:8004/health")
    print("- ✍️  Content Writer: http://localhost:8003/health")
    print("- 📋 Form API: http://localhost:8010/health")
    
    print("\n🧪 測試建議:")
    print("1. 打開瀏覽器訪問: http://localhost:8501")
    print("2. 輸入測試需求: '請幫我創建貼文，簡單一點，然後化妝新品月底前打8折'")
    print("3. 或運行測試腳本: python test_clarification_system.py")
    
    print("\n📝 查看日誌:")
    print("- 查看所有日誌: docker-compose logs -f")
    print("- 查看特定服務: docker-compose logs -f orchestrator-agent")

if __name__ == "__main__":
    main()