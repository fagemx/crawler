#!/usr/bin/env python3
"""
虛擬環境設置和依賴安裝腳本

自動化創建虛擬環境、安裝依賴和基本配置
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def run_command(command, description=""):
    """執行命令並處理錯誤"""
    print(f"🔄 {description}")
    print(f"   執行: {command}")
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            capture_output=True, 
            text=True
        )
        if result.stdout:
            print(f"   ✅ {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ 錯誤: {e}")
        if e.stderr:
            print(f"   詳細錯誤: {e.stderr}")
        return False


def check_python_version():
    """檢查 Python 版本"""
    print("🐍 檢查 Python 版本")
    
    version = sys.version_info
    print(f"   當前版本: Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("   ❌ 需要 Python 3.8 或更高版本")
        return False
    
    print("   ✅ Python 版本符合要求")
    return True


def create_virtual_environment():
    """創建虛擬環境"""
    venv_path = Path("venv")
    
    if venv_path.exists():
        print("📁 虛擬環境已存在，跳過創建")
        return True
    
    print("📁 創建虛擬環境")
    return run_command("python -m venv venv", "創建虛擬環境")


def get_activation_command():
    """獲取虛擬環境啟動命令"""
    system = platform.system().lower()
    
    if system == "windows":
        return "venv\\Scripts\\activate"
    else:
        return "source venv/bin/activate"


def install_dependencies():
    """安裝依賴"""
    print("📦 安裝 Python 依賴")
    
    system = platform.system().lower()
    
    if system == "windows":
        pip_command = "venv\\Scripts\\pip install -e ."
    else:
        pip_command = "venv/bin/pip install -e ."
    
    return run_command(pip_command, "安裝依賴包（可編輯模式）")


def setup_env_file():
    """設置環境變數檔案"""
    print("⚙️  設置環境配置")
    
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("   📄 .env 檔案已存在")
        return True
    
    if not env_example.exists():
        print("   ❌ .env.example 檔案不存在")
        return False
    
    # 複製範例檔案
    try:
        import shutil
        shutil.copy(env_example, env_file)
        print("   ✅ 已創建 .env 檔案")
        print("   ⚠️  請編輯 .env 檔案，設置你的 APIFY_TOKEN")
        return True
    except Exception as e:
        print(f"   ❌ 創建 .env 檔案失敗: {e}")
        return False


def verify_installation():
    """驗證安裝"""
    print("🔍 驗證安裝")
    
    system = platform.system().lower()
    
    if system == "windows":
        python_command = "venv\\Scripts\\python -c \"import fastapi, apify_client; print('依賴安裝成功')\""
    else:
        python_command = "venv/bin/python -c \"import fastapi, apify_client; print('依賴安裝成功')\""
    
    return run_command(python_command, "驗證核心依賴")


def print_next_steps():
    """打印後續步驟"""
    activation_cmd = get_activation_command()
    
    print("\n" + "="*60)
    print("🎉 環境設置完成！")
    print("="*60)
    
    print("\n📋 後續步驟：")
    print(f"1. 啟動虛擬環境：")
    print(f"   {activation_cmd}")
    
    print(f"\n2. 編輯 .env 檔案，設置你的 Apify Token：")
    print(f"   APIFY_TOKEN=your_actual_apify_token_here")
    
    print(f"\n3. 測試爬蟲功能：")
    print(f"   python test_crawler.py")
    
    print(f"\n4. 啟動開發服務：")
    print(f"   python scripts/start_dev.py")
    
    print(f"\n📚 範例用戶測試：")
    print(f"   用戶主頁：https://www.threads.com/@09johan24")
    print(f"   範例貼文：https://www.threads.com/@09johan24/post/DMaHMSqTdFs")
    
    print(f"\n🔧 如需添加更多功能：")
    print(f"   # 安裝 AI 功能: pip install -e .[ai]")
    print(f"   # 安裝 UI 功能: pip install -e .[ui]") 
    print(f"   # 安裝完整功能: pip install -e .[full]")
    print(f"   # 開發環境: pip install -e .[dev]")


def main():
    """主函數"""
    print("🚀 社交媒體內容生成系統 - 環境設置")
    print("="*60)
    
    # 檢查當前目錄
    if not Path("pyproject.toml").exists():
        print("❌ 請在專案根目錄執行此腳本")
        sys.exit(1)
    
    # 執行設置步驟
    steps = [
        ("檢查 Python 版本", check_python_version),
        ("創建虛擬環境", create_virtual_environment),
        ("安裝依賴", install_dependencies),
        ("設置環境檔案", setup_env_file),
        ("驗證安裝", verify_installation),
    ]
    
    failed_steps = []
    
    for step_name, step_func in steps:
        print(f"\n📍 步驟：{step_name}")
        if not step_func():
            failed_steps.append(step_name)
    
    if failed_steps:
        print(f"\n❌ 以下步驟失敗：")
        for step in failed_steps:
            print(f"   - {step}")
        print(f"\n請檢查錯誤訊息並手動解決")
        sys.exit(1)
    
    print_next_steps()


if __name__ == "__main__":
    main()