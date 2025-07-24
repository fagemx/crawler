#!/usr/bin/env python3
"""
Playwright Crawler Agent - 統一設定檔
管理所有路徑和常數設定
"""

from pathlib import Path

# 基礎路徑設定
AGENT_DIR = Path(__file__).parent  # agents/playwright_crawler/
PROJECT_ROOT = AGENT_DIR.parent.parent  # project root

# 認證檔案路徑設定
AUTH_FILE = AGENT_DIR / "auth.json"
AUTH_FILE_RELATIVE = "agents/playwright_crawler/auth.json"  # 從專案根目錄的相對路徑

# 除錯檔案路徑
SAMPLE_THREAD_ITEM_FILE = AGENT_DIR / "sample_thread_item.json"
DEBUG_FAILED_ITEM_FILE = AGENT_DIR / "debug_failed_item.json"

# 容器相容的 User-Agent（與 playwright_logic.py 保持一致）
DOCKER_COMPATIBLE_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# API 設定
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8006

# 爬蟲預設設定
DEFAULT_SCROLL_DELAY_MIN = 2.0
DEFAULT_SCROLL_DELAY_MAX = 3.5
DEFAULT_MAX_SCROLL_ATTEMPTS = 20
DEFAULT_NAVIGATION_TIMEOUT = 30000

def get_auth_file_path(from_project_root: bool = False) -> Path:
    """
    取得 auth.json 的路徑
    
    Args:
        from_project_root: 是否從專案根目錄開始的路徑
        
    Returns:
        Path: auth.json 的路徑
    """
    if from_project_root:
        return PROJECT_ROOT / AUTH_FILE_RELATIVE
    else:
        return AUTH_FILE

def ensure_auth_file_exists() -> bool:
    """
    檢查 auth.json 是否存在
    
    Returns:
        bool: 檔案是否存在
    """
    return AUTH_FILE.exists() 