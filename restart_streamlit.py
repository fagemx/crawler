#!/usr/bin/env python3
"""
重新啟動 Streamlit 的快速腳本
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    project_root = Path(__file__).parent
    ui_path = project_root / "ui" / "streamlit_app.py"
    
    print("🔄 重新啟動 Streamlit UI...")
    print("🌐 訪問: http://localhost:8501")
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
        print("\n👋 Streamlit UI 已停止")

if __name__ == "__main__":
    main()