#!/usr/bin/env python3
"""
RustFS Heal Queue 修復腳本
用於立即解決 "Heal queue is full" 錯誤

這是一個簡化版本的修復腳本，專門用於快速解決當前的問題。
"""

import subprocess
import time
import os
import sys
from pathlib import Path

# Windows 控制台編碼問題的解決方案
if sys.platform == "win32":
    import io
    
    # 設置控制台輸出編碼
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def run_command(cmd, timeout=30):
    """執行命令並返回結果"""
    try:
        # Windows 編碼修復
        encoding = 'utf-8' if sys.platform != "win32" else 'cp950'
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding=encoding,
            errors='replace',  # 忽略編碼錯誤
            timeout=timeout
        )
        
        # 安全處理 None 值
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        
        return result.returncode == 0, stdout, stderr
    except subprocess.TimeoutExpired:
        return False, "", "命令超時"
    except Exception as e:
        return False, "", str(e)

def check_docker_compose():
    """檢查 docker-compose 可用性"""
    success, _, _ = run_command("docker-compose --version")
    if success:
        return "docker-compose"
    
    success, _, _ = run_command("docker compose version")
    if success:
        return "docker compose"
    
    return None

def main():
    print("[FIX] RustFS Heal Queue 修復腳本")
    print("=" * 40)
    
    # 檢查 docker-compose
    compose_cmd = check_docker_compose()
    if not compose_cmd:
        print("[ERROR] 找不到 docker-compose 或 docker compose 命令")
        print("[INFO] 請先安裝 Docker Compose")
        return False
    
    print(f"[OK] 使用 {compose_cmd}")
    
    # 1. 停止 RustFS 容器
    print("\n[STOP] 停止 RustFS 容器...")
    success, stdout, stderr = run_command(f"{compose_cmd} stop rustfs")
    if success:
        print("[OK] RustFS 容器已停止")
    else:
        print(f"[ERROR] 停止失敗: {stderr}")
    
    # 2. 清理 RustFS 數據（謹慎操作）
    print("\n[CLEAN] 清理 RustFS 臨時數據...")
    rustfs_data_dir = Path("./storage/rustfs")
    if rustfs_data_dir.exists():
        # 只清理臨時和日誌文件，保留實際數據
        temp_patterns = ["*.tmp", "*.log", "*.lock", ".heal*"]
        cleaned_count = 0
        
        for pattern in temp_patterns:
            for file_path in rustfs_data_dir.rglob(pattern):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                        cleaned_count += 1
                except Exception as e:
                    print(f"[WARN] 無法刪除 {file_path}: {e}")
        
        print(f"[OK] 清理了 {cleaned_count} 個臨時文件")
    else:
        print("[INFO] RustFS 數據目錄不存在")
    
    # 3. 清理日誌目錄
    print("\n[LOG] 清理日誌目錄...")
    logs_dir = Path("./storage/rustfs-logs")
    if logs_dir.exists():
        log_count = 0
        for log_file in logs_dir.glob("*.log"):
            try:
                log_file.unlink()
                log_count += 1
            except Exception as e:
                print(f"[WARN] 無法刪除日誌 {log_file}: {e}")
        print(f"[OK] 清理了 {log_count} 個日誌文件")
    else:
        print("[INFO] 日誌目錄不存在")
    
    # 4. 重啟 RustFS 容器
    print("\n[RESTART] 重啟 RustFS 容器...")
    success, stdout, stderr = run_command(f"{compose_cmd} up -d rustfs", timeout=60)
    if success:
        print("[OK] RustFS 容器已重啟")
    else:
        print(f"[ERROR] 重啟失敗: {stderr}")
        return False
    
    # 5. 等待服務啟動
    print("\n[WAIT] 等待服務啟動...")
    time.sleep(15)
    
    # 6. 檢查服務狀態
    print("\n[CHECK] 檢查服務狀態...")
    success, stdout, stderr = run_command(f"{compose_cmd} ps rustfs")
    stdout_content = stdout or ""
    if success and "Up" in stdout_content:
        print("[OK] RustFS 服務正常運行")
    else:
        print("[WARN] RustFS 狀態異常，請檢查日誌")
        print("[INFO] 使用以下命令檢查日誌:")
        print(f"   {compose_cmd} logs rustfs")
        if stdout_content:
            print(f"[DEBUG] 容器狀態: {stdout_content.strip()}")
    
    # 7. 檢查 S3 API
    print("\n[TEST] 測試 S3 API...")
    try:
        import requests
        response = requests.get("http://localhost:9000/", timeout=10)
        if response.status_code in [200, 403, 404]:
            print("[OK] S3 API 可以訪問")
        else:
            print(f"[WARN] S3 API 狀態異常: {response.status_code}")
    except ImportError:
        print("[INFO] 無法測試 S3 API (缺少 requests 模組)")
    except Exception as e:
        print(f"[WARN] S3 API 測試失敗: {e}")
    
    print("\n[DONE] 修復完成！")
    print("\n[INFO] 如果問題仍然存在，請:")
    print("   1. 檢查磁碟空間是否充足")
    print("   2. 使用完整的管理工具:")
    print("      python rustfs_auto_manager.py --action auto")
    print("   3. 查看詳細日誌:")
    print(f"      {compose_cmd} logs rustfs")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOP] 操作已中斷")
    except Exception as e:
        print(f"\n[ERROR] 修復過程中發生錯誤: {e}")
        sys.exit(1)
