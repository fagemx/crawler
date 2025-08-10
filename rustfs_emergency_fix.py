#!/usr/bin/env python3
"""
RustFS 緊急修復腳本 - 簡化版本
專門用於快速解決 "Heal queue is full" 錯誤

這個腳本避免了複雜的編碼問題，專注於快速修復。
"""

import subprocess
import time
import os
import sys
import shutil
from pathlib import Path

def safe_run(cmd):
    """安全執行命令，忽略編碼錯誤"""
    try:
        print(f"[CMD] {cmd}")
        
        # 使用更簡單的方式執行命令
        result = os.system(cmd)
        return result == 0
    except Exception as e:
        print(f"[ERROR] 命令執行失敗: {e}")
        return False

def find_docker_compose():
    """尋找可用的 docker-compose 命令"""
    if shutil.which("docker-compose"):
        return "docker-compose"
    elif shutil.which("docker"):
        # 測試 docker compose
        try:
            result = os.system("docker compose version >nul 2>&1")
            if result == 0:
                return "docker compose"
        except:
            pass
    return None

def emergency_fix():
    """緊急修復函數"""
    print("[EMERGENCY] RustFS Heal Queue 緊急修復")
    print("=" * 50)
    
    # 1. 找到 docker-compose
    compose_cmd = find_docker_compose()
    if not compose_cmd:
        print("[ERROR] 找不到 docker-compose 或 docker compose")
        return False
    
    print(f"[OK] 使用: {compose_cmd}")
    
    # 2. 停止 RustFS
    print("\n[STEP 1] 停止 RustFS 服務...")
    if safe_run(f"{compose_cmd} stop rustfs"):
        print("[OK] 服務已停止")
    else:
        print("[WARN] 停止可能失敗，繼續執行...")
    
    # 3. 強制停止並移除容器
    print("\n[STEP 2] 強制清理容器...")
    safe_run(f"{compose_cmd} rm -f rustfs")
    
    # 4. 清理本地數據
    print("\n[STEP 3] 清理臨時數據...")
    try:
        # 清理 RustFS 數據目錄中的臨時文件
        data_dir = Path("./storage/rustfs")
        if data_dir.exists():
            temp_count = 0
            for pattern in ["*.tmp", "*.log", "*.lock"]:
                for file_path in data_dir.rglob(pattern):
                    try:
                        if file_path.is_file():
                            file_path.unlink()
                            temp_count += 1
                    except:
                        pass
            print(f"[OK] 清理了 {temp_count} 個臨時文件")
        
        # 清理日誌目錄
        log_dir = Path("./storage/rustfs-logs")
        if log_dir.exists():
            log_count = 0
            for log_file in log_dir.glob("*.log"):
                try:
                    log_file.unlink()
                    log_count += 1
                except:
                    pass
            print(f"[OK] 清理了 {log_count} 個日誌文件")
    except Exception as e:
        print(f"[WARN] 清理過程中出現問題: {e}")
    
    # 5. 重新創建存儲目錄
    print("\n[STEP 4] 重新創建存儲目錄...")
    try:
        storage_dirs = [
            Path("./storage/rustfs"),
            Path("./storage/rustfs-logs")
        ]
        for dir_path in storage_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
        print("[OK] 存儲目錄已準備")
    except Exception as e:
        print(f"[WARN] 目錄創建問題: {e}")
    
    # 6. 重啟 RustFS
    print("\n[STEP 5] 重啟 RustFS 服務...")
    if safe_run(f"{compose_cmd} up -d rustfs"):
        print("[OK] 服務已重啟")
    else:
        print("[ERROR] 重啟失敗")
        return False
    
    # 7. 等待啟動
    print("\n[STEP 6] 等待服務啟動...")
    for i in range(3):
        print(f"[WAIT] 等待中... ({i+1}/3)")
        time.sleep(5)
    
    # 8. 檢查狀態
    print("\n[STEP 7] 檢查服務狀態...")
    if safe_run(f"{compose_cmd} ps rustfs"):
        print("[INFO] 請檢查上面的容器狀態輸出")
    
    print("\n[COMPLETE] 緊急修復完成!")
    print("\n[NEXT STEPS]")
    print("1. 檢查 RustFS 容器是否正在運行:")
    print(f"   {compose_cmd} ps rustfs")
    print("2. 查看 RustFS 日誌:")
    print(f"   {compose_cmd} logs rustfs")
    print("3. 測試 S3 API (如果有 curl):")
    print("   curl http://localhost:9000/")
    
    return True

def main():
    """主函數"""
    try:
        # 檢查是否在正確的目錄
        if not Path("docker-compose.yml").exists():
            print("[ERROR] 請在專案根目錄執行此腳本")
            return False
        
        return emergency_fix()
        
    except KeyboardInterrupt:
        print("\n[STOP] 操作被中斷")
        return False
    except Exception as e:
        print(f"\n[ERROR] 發生錯誤: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n[HELP] 如果問題持續存在:")
        print("1. 檢查磁碟空間: dir storage")
        print("2. 手動重啟: docker-compose restart rustfs")
        print("3. 查看錯誤: docker-compose logs rustfs")
        sys.exit(1)
    else:
        print("\n[SUCCESS] 修復完成!")
        sys.exit(0)

