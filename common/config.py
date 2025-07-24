#!/usr/bin/env python3
"""
共用設定模組
"""

from pathlib import Path

def get_project_root() -> Path:
    """返回專案的根目錄"""
    return Path(__file__).parent.parent

def get_auth_file_path(from_project_root: bool = False) -> Path:
    """
    獲取 auth.json 的標準路徑。
    
    Args:
        from_project_root: 如果為 True，返回相對於專案根目錄的路徑物件。
                           如果為 False，返回相對於 `agents/playwright_crawler/` 的路徑。
                           實際上兩者指向同一個檔案。
    
    Returns:
        Path: auth.json 的路徑物件。
    """
    root = get_project_root()
    return root / "agents" / "playwright_crawler" / "auth.json" 