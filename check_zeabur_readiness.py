#!/usr/bin/env python3
"""
Zeabur 部署準備檢查腳本
檢查項目是否準備好部署到 Zeabur
"""

import os
import sys
from pathlib import Path

def check_file_exists(file_path: str, required: bool = True) -> bool:
    """檢查文件是否存在"""
    exists = Path(file_path).exists()
    status = "✅" if exists else ("❌" if required else "⚠️")
    req_text = " (必需)" if required else " (可選)"
    print(f"{status} {file_path}{req_text}")
    return exists

def check_dockerfile_ports():
    """檢查 Dockerfile 中的端口配置"""
    print("\n📋 檢查 Dockerfile 端口配置:")
    
    dockerfiles = [
        ("ui/Dockerfile", "8501"),
        ("agents/orchestrator/Dockerfile", "8000"), 
        ("agents/playwright_crawler/Dockerfile", "8006"),
        ("Dockerfile.minimal", "8501"),
        ("Dockerfile.zeabur", "8501"),
    ]
    
    for dockerfile, expected_port in dockerfiles:
        if Path(dockerfile).exists():
            with open(dockerfile, 'r') as f:
                content = f.read()
                has_expose = f"EXPOSE {expected_port}" in content
                has_cmd_port = f"--port {expected_port}" in content or f"--port={expected_port}" in content
                
                if has_expose or has_cmd_port:
                    print(f"✅ {dockerfile}: 端口 {expected_port} 配置正確")
                else:
                    print(f"⚠️ {dockerfile}: 可能缺少端口 {expected_port} 配置")

def check_dependencies():
    """檢查依賴配置"""
    print("\n📦 檢查依賴配置:")
    
    if Path("pyproject.toml").exists():
        with open("pyproject.toml", 'r') as f:
            content = f.read()
            
            # 檢查必要的依賴組
            required_groups = ["ui", "messaging", "database"]
            for group in required_groups:
                if f"{group} = [" in content:
                    print(f"✅ 依賴組 '{group}' 已定義")
                else:
                    print(f"❌ 缺少依賴組 '{group}'")

def main():
    """主檢查函數"""
    print("🚀 Zeabur 部署準備檢查")
    print("=" * 50)
    
    print("\n📁 檢查核心文件:")
    
    # 檢查核心文件
    core_files = [
        ("pyproject.toml", True),
        ("README.md", True), 
        ("LICENSE", True),
        ("docker-compose.yml", False),
    ]
    
    all_core_exists = True
    for file_path, required in core_files:
        exists = check_file_exists(file_path, required)
        if required and not exists:
            all_core_exists = False
    
    print("\n🐳 檢查 Dockerfile:")
    
    # 檢查各種 Dockerfile 選項
    dockerfile_options = [
        ("Dockerfile.minimal", "最小化部署 (僅 UI)"),
        ("Dockerfile.zeabur", "核心功能部署 (UI + 主要服務)"),
        ("ui/Dockerfile", "UI 服務單獨部署"),
        ("agents/orchestrator/Dockerfile", "Orchestrator 服務"),
        ("agents/playwright_crawler/Dockerfile", "爬蟲服務"),
    ]
    
    available_options = []
    for dockerfile, description in dockerfile_options:
        if check_file_exists(dockerfile, False):
            available_options.append((dockerfile, description))
    
    print("\n🎯 可用的部署選項:")
    if available_options:
        for dockerfile, description in available_options:
            print(f"  📄 {dockerfile} - {description}")
    else:
        print("❌ 沒有找到可用的 Dockerfile")
    
    # 檢查端口配置
    check_dockerfile_ports()
    
    # 檢查依賴
    check_dependencies()
    
    print("\n📝 檢查服務目錄:")
    service_dirs = [
        "ui/", "agents/orchestrator/", "agents/playwright_crawler/",
        "agents/vision/", "agents/content_writer/", "common/"
    ]
    
    for service_dir in service_dirs:
        check_file_exists(service_dir, False)
    
    print("\n" + "=" * 50)
    print("📊 總結:")
    
    if all_core_exists:
        print("✅ 核心文件準備完成")
    else:
        print("❌ 缺少必要的核心文件")
    
    if available_options:
        print("✅ 有可用的 Dockerfile 選項")
        print("\n🎯 建議的部署步驟:")
        print("1. 選擇一個 Dockerfile (推薦 Dockerfile.minimal 開始)")
        print("2. 在 Zeabur 創建 PostgreSQL 和 Redis 服務")
        print("3. 設定環境變數")
        print("4. 部署主應用")
        print("\n📖 詳細步驟請參考: ZEABUR_DEPLOYMENT.md")
    else:
        print("❌ 需要創建 Dockerfile")
    
    return 0 if all_core_exists and available_options else 1

if __name__ == "__main__":
    sys.exit(main())