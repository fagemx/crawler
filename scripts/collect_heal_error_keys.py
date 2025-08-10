#!/usr/bin/env python3
"""
從 RustFS 容器日誌收集觸發 heal queue 的物件 key，輸出到檔案以便後續批次刪除。

使用方式：
  python scripts/collect_heal_error_keys.py --tail 5000 --out heal_keys.txt

注意：
  - 需在專案根目錄執行，且可使用 docker compose 取得容器日誌。
  - 依據日誌型態解析：
    例：Failed to submit heal task for social-media-content/image/xx/yy/abc.jpg: Heal configuration error: Heal queue is full
    解析出 bucket=social-media-content, key=image/xx/yy/abc.jpg
"""

import argparse
import os
import re
import sys
from pathlib import Path
import subprocess


def run_compose_logs(tail: int) -> str:
    """取得 rustfs 的 docker compose 日誌內容。"""
    cmd = ["docker", "compose", "logs", f"--tail={tail}", "rustfs"]
    # Windows 編碼相容
    encoding = 'utf-8' if sys.platform != 'win32' else 'cp950'
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding=encoding, errors='replace', check=False
        )
        return (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    except Exception as e:
        print(f"[ERROR] 無法取得 docker compose 日誌: {e}")
        return ""


def parse_keys_from_logs(log_text: str, default_bucket: str) -> list[str]:
    keys = []
    # 直接從訊息中找 for <bucket>/<key>: Heal configuration error
    # 例：... Failed to submit heal task for social-media-content/image/1c/67/xxx.jpg: Heal configuration error: ...
    pattern = re.compile(r"for\s+([^\s:]+):\s+Heal configuration error")
    for line in log_text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        full = m.group(1).strip()  # social-media-content/image/...
        # 嘗試拆 bucket 與 key
        if '/' in full:
            first_slash = full.find('/')
            bucket = full[:first_slash]
            key = full[first_slash+1:]
        else:
            bucket = default_bucket
            key = full
        if bucket:  # 僅收集 key，bucket 用於檢查
            keys.append(key)
    return keys


def main():
    parser = argparse.ArgumentParser(description="Collect heal error object keys from rustfs logs")
    parser.add_argument("--tail", type=int, default=2000, help="讀取最後 N 行日誌")
    parser.add_argument("--out", default="heal_keys.txt", help="輸出檔案")
    parser.add_argument("--bucket", default=os.getenv("RUSTFS_BUCKET", "social-media-content"))
    args = parser.parse_args()

    text = run_compose_logs(args.tail)
    keys = parse_keys_from_logs(text, args.bucket)
    unique_keys = sorted(set(keys))
    Path(args.out).write_text("\n".join(unique_keys), encoding='utf-8')
    print(f"[SUMMARY] 解析出 {len(unique_keys)} 個問題 key，已輸出至 {args.out}")


if __name__ == "__main__":
    main()



