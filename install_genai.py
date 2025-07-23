#!/usr/bin/env python3
"""
安裝 Google GenAI 套件

安裝新版的 google-genai 套件以支援 Jina + Vision 整合功能
"""

import subprocess
import sys


def install_package(package_name):
    """安裝 Python 套件"""
    try:
        print(f"正在安裝 {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ {package_name} 安裝成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {package_name} 安裝失敗:")
        print(f"錯誤輸出: {e.stderr}")
        return False


def main():
    """主函數"""
    print("開始安裝 Google GenAI 相關套件")
    print("=" * 50)
    
    # 需要安裝的套件
    packages = [
        "google-genai",
        "requests",  # 確保 requests 已安裝
    ]
    
    success_count = 0
    for package in packages:
        if install_package(package):
            success_count += 1
    
    print(f"\n安裝完成: {success_count}/{len(packages)} 個套件成功安裝")
    
    if success_count == len(packages):
        print("🎉 所有套件都安裝成功！")
        print("\n現在可以執行測試:")
        print("python test_jina_vision_integration.py")
        return 0
    else:
        print("⚠️ 部分套件安裝失敗，請檢查錯誤訊息")
        return 1


if __name__ == "__main__":
    sys.exit(main())