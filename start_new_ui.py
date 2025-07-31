#!/usr/bin/env python3
"""
啟動新版 Streamlit UI
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    project_root = Path(__file__).parent
    ui_path = project_root / "ui" / "streamlit_app_new.py"
    
    print("🚀 啟動新版 Streamlit UI...")
    print("📁 項目路徑:", project_root)
    print("🌐 UI 將在 http://localhost:8501 啟動")
    print("=" * 50)
    print("✨ 新版功能:")
    print("  🕷️ Threads 爬蟲 (基於 test_playwright_agent.py)")
    print("  📝 智能內容生成 (支持通用主題)")
    print("  📊 系統監控 (基於 test_mcp_complete.py)")
    print("  💾 JSON 下載功能")
    print("=" * 50)
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(ui_path),
            "--server.port", "8501",
            "--server.address", "0.0.0.0"
        ], env=env, cwd=project_root)
    except KeyboardInterrupt:
        print("\n👋 新版 Streamlit UI 已停止")

if __name__ == "__main__":
    main()