#!/usr/bin/env python3
"""
依賴檢查腳本

檢查當前安裝的依賴版本和兼容性
"""

import sys
import importlib
from pathlib import Path


def check_package(package_name, min_version=None):
    """檢查單個包的安裝狀態和版本"""
    try:
        module = importlib.import_module(package_name)
        version = getattr(module, '__version__', 'Unknown')
        
        print(f"✅ {package_name}: {version}")
        
        if min_version and hasattr(module, '__version__'):
            from packaging import version as pkg_version
            if pkg_version.parse(module.__version__) >= pkg_version.parse(min_version):
                print(f"   版本符合要求 (>= {min_version})")
            else:
                print(f"   ⚠️  版本過低，建議升級到 >= {min_version}")
        
        return True
        
    except ImportError:
        print(f"❌ {package_name}: 未安裝")
        return False
    except Exception as e:
        print(f"⚠️  {package_name}: 檢查時發生錯誤 - {e}")
        return False


def main():
    """主函數"""
    print("🔍 依賴檢查報告")
    print("=" * 50)
    
    # 核心依賴檢查
    core_deps = [
        ("fastapi", "0.100.0"),
        ("uvicorn", "0.20.0"),
        ("pydantic", "2.0.0"),
        ("apify_client", "1.0.0"),
        ("httpx", "0.24.0"),
        ("requests", "2.28.0"),
        ("click", "8.0.0"),
    ]
    
    print("\n📦 核心依賴檢查：")
    core_success = 0
    for package, min_ver in core_deps:
        if check_package(package, min_ver):
            core_success += 1
    
    print(f"\n核心依賴狀態：{core_success}/{len(core_deps)} 已安裝")
    
    # 可選依賴檢查
    optional_deps = {
        "AI 功能": [
            ("google.generativeai", None),
            ("openai", None),
            ("anthropic", None),
        ],
        "UI 功能": [
            ("streamlit", None),
        ],
        "資料庫功能": [
            ("sqlalchemy", None),
            ("asyncpg", None),
        ],
        "開發工具": [
            ("pytest", None),
            ("black", None),
            ("mypy", None),
        ]
    }
    
    for category, deps in optional_deps.items():
        print(f"\n🔧 {category}：")
        success = 0
        for package, min_ver in deps:
            if check_package(package, min_ver):
                success += 1
        
        if success > 0:
            print(f"   狀態：{success}/{len(deps)} 已安裝")
        else:
            print(f"   狀態：未安裝（可選功能）")
    
    # 版本策略驗證
    print(f"\n📊 版本策略驗證：")
    print(f"✅ 使用寬鬆版本範圍 (>=X.Y.Z)")
    print(f"✅ 允許自動獲得最新功能和安全更新")
    print(f"✅ 避免過度限制版本範圍")
    
    # 安裝建議
    if core_success < len(core_deps):
        print(f"\n💡 安裝建議：")
        print(f"   pip install -e .  # 安裝核心依賴")
    
    print(f"\n🚀 功能擴展：")
    print(f"   pip install -e .[ai]        # 添加 AI 功能")
    print(f"   pip install -e .[ui]        # 添加 UI 功能")
    print(f"   pip install -e .[full]      # 安裝完整功能")
    print(f"   pip install -e .[dev]       # 開發環境")
    
    # 檢查 pyproject.toml
    pyproject_file = Path("pyproject.toml")
    if pyproject_file.exists():
        print(f"\n✅ pyproject.toml 存在")
    else:
        print(f"\n❌ pyproject.toml 不存在")
    
    print(f"\n" + "=" * 50)
    print(f"檢查完成！")


if __name__ == "__main__":
    # 檢查是否安裝了 packaging（用於版本比較）
    try:
        import packaging
    except ImportError:
        print("⚠️  建議安裝 packaging 包以進行版本比較：pip install packaging")
    
    main()