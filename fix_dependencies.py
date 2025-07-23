#!/usr/bin/env python3
"""
依賴修復腳本

自動檢測和修復依賴問題
"""

import subprocess
import sys
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
            print(f"   ✅ 成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ 失敗: {e}")
        if e.stderr:
            print(f"   錯誤詳情: {e.stderr}")
        return False


def check_virtual_env():
    """檢查是否在虛擬環境中"""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def main():
    """主函數"""
    print("🔧 依賴修復工具")
    print("=" * 50)
    
    # 檢查是否在專案根目錄
    if not Path("pyproject.toml").exists():
        print("❌ 請在專案根目錄執行此腳本")
        sys.exit(1)
    
    # 檢查虛擬環境
    if not check_virtual_env():
        print("⚠️  建議在虛擬環境中執行")
        response = input("是否繼續？(y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    else:
        print("✅ 檢測到虛擬環境")
    
    # 升級 pip
    print(f"\n📦 升級 pip...")
    run_command("python -m pip install --upgrade pip", "升級 pip")
    
    # 安裝/升級核心依賴
    print(f"\n📦 安裝核心依賴...")
    if run_command("pip install -e .", "安裝核心依賴"):
        print("✅ 核心依賴安裝成功")
    else:
        print("❌ 核心依賴安裝失敗")
        return
    
    # 檢查特定的問題包
    print(f"\n🔍 檢查特定依賴...")
    
    # 檢查 apify-client
    try:
        import apify_client
        print(f"✅ apify-client: {apify_client.__version__}")
    except ImportError:
        print("❌ apify-client 未安裝，嘗試手動安裝...")
        run_command("pip install apify-client", "安裝 apify-client")
    
    # 檢查其他核心包
    core_packages = ['fastapi', 'uvicorn', 'pydantic', 'httpx']
    for package in core_packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'Unknown')
            print(f"✅ {package}: {version}")
        except ImportError:
            print(f"❌ {package} 未安裝")
    
    # 提供可選功能安裝選項
    print(f"\n🚀 可選功能安裝：")
    print(f"1. AI 功能 (google-generativeai, openai)")
    print(f"2. UI 功能 (streamlit)")
    print(f"3. 完整功能 (所有功能)")
    print(f"4. 開發工具 (pytest, black, mypy)")
    print(f"5. 跳過")
    
    choice = input("選擇要安裝的功能 (1-5): ").strip()
    
    if choice == "1":
        run_command("pip install -e .[ai]", "安裝 AI 功能")
    elif choice == "2":
        run_command("pip install -e .[ui]", "安裝 UI 功能")
    elif choice == "3":
        run_command("pip install -e .[full]", "安裝完整功能")
    elif choice == "4":
        run_command("pip install -e .[dev]", "安裝開發工具")
    elif choice == "5":
        print("跳過可選功能安裝")
    else:
        print("無效選擇，跳過")
    
    # 最終驗證
    print(f"\n🔍 最終驗證...")
    run_command("python check_dependencies.py", "檢查依賴狀態")
    
    print(f"\n" + "=" * 50)
    print(f"🎉 依賴修復完成！")
    print(f"\n下一步：")
    print(f"1. 設置 .env 檔案中的 APIFY_TOKEN")
    print(f"2. 執行測試：python test_crawler.py")


if __name__ == "__main__":
    main()