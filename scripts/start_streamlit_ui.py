#!/usr/bin/env python3
"""
啟動 Streamlit UI 的腳本
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    # 獲取項目根目錄
    project_root = Path(__file__).parent.parent
    ui_path = project_root / "ui" / "streamlit_app.py"
    
    if not ui_path.exists():
        print(f"❌ 找不到 UI 文件: {ui_path}")
        return
    
    print("🚀 啟動 Streamlit UI...")
    print(f"📁 項目路徑: {project_root}")
    print(f"🌐 UI 將在 http://localhost:8501 啟動")
    print("=" * 50)
    
    # 設置環境變數
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    
    try:
        # 啟動 Streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(ui_path),
            "--server.port", "8501",
            "--server.address", "0.0.0.0",
            "--theme.base", "light"
        ], env=env, cwd=project_root)
    except KeyboardInterrupt:
        print("\n👋 Streamlit UI 已停止")
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")

if __name__ == "__main__":
    main()