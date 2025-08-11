#!/usr/bin/env python3
"""
RustFS 自動管理腳本
用於自動清理和管理 RustFS 存儲，解決 "Heal queue is full" 問題

功能：
1. 監控 RustFS 健康狀態
2. 自動清理過期媒體檔案
3. 清理失敗的下載記錄
4. 重啟 RustFS 服務（如果需要）
5. 定期維護和監控

使用方法：
python rustfs_auto_manager.py --action cleanup        # 執行清理
python rustfs_auto_manager.py --action monitor        # 監控狀態
python rustfs_auto_manager.py --action restart        # 重啟服務
python rustfs_auto_manager.py --action auto           # 自動模式（推薦）
"""

import asyncio
import os
import sys
import argparse
import subprocess
import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日誌 - Windows 兼容性
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rustfs_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Windows 控制台編碼問題的解決方案
if sys.platform == "win32":
    import io
    import codecs
    
    # 設置控制台輸出編碼
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        
    # 重新配置 logging 以避免 emoji 問題
    class SafeFormatter(logging.Formatter):
        def format(self, record):
            # 移除 emoji 字符，替換為安全的文字
            msg = super().format(record)
            emoji_map = {
                '🤖': '[AUTO]',
                '📊': '[INFO]',
                '✅': '[OK]',
                '❌': '[ERROR]',
                '⚠️': '[WARN]',
                '🧹': '[CLEAN]',
                '🔄': '[RESTART]',
                '📡': '[MONITOR]',
                '🕐': '[TIME]',
                '😴': '[SLEEP]',
                '⏹️': '[STOP]'
            }
            for emoji, text in emoji_map.items():
                msg = msg.replace(emoji, text)
            return msg
    
    # 更新所有 handlers 的 formatter
    safe_formatter = SafeFormatter('%(asctime)s - %(levelname)s - %(message)s')
    for handler in logging.root.handlers:
        handler.setFormatter(safe_formatter)
logger = logging.getLogger(__name__)

class RustFSAutoManager:
    """RustFS 自動管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.rustfs_data_dir = Path("./storage/rustfs")
        self.rustfs_logs_dir = Path("./storage/rustfs-logs")
        self.docker_compose_cmd = self._get_docker_compose_cmd()
        
        # 清理配置
        self.max_file_age_days = int(os.getenv("RUSTFS_MAX_FILE_AGE_DAYS", "7"))
        self.max_log_age_days = int(os.getenv("RUSTFS_MAX_LOG_AGE_DAYS", "3"))
        self.max_storage_size_gb = int(os.getenv("RUSTFS_MAX_STORAGE_SIZE_GB", "10"))
        
        # 確保目錄存在
        self.rustfs_data_dir.mkdir(parents=True, exist_ok=True)
        self.rustfs_logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_docker_compose_cmd(self) -> str:
        """獲取 docker-compose 命令"""
        if shutil.which("docker-compose"):
            return "docker-compose"
        elif shutil.which("docker") and self._test_docker_compose():
            return "docker compose"
        else:
            raise RuntimeError("找不到 docker-compose 或 docker compose 命令")
    
    def _test_docker_compose(self) -> bool:
        """測試 docker compose 是否可用"""
        try:
            subprocess.run(["docker", "compose", "version"], 
                         capture_output=True, check=True)
            return True
        except:
            return False
    
    def _run_command(self, cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """執行命令"""
        try:
            logger.info(f"執行命令: {' '.join(cmd)}")
            
            # Windows 編碼修復
            encoding = 'utf-8' if sys.platform != "win32" else 'cp950'
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                encoding=encoding,
                errors='replace',  # 忽略編碼錯誤
                timeout=timeout,
                check=False
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"命令超時: {' '.join(cmd)}")
            raise
        except Exception as e:
            logger.error(f"命令執行失敗: {e}")
            raise
    
    def check_rustfs_health(self) -> Dict[str, Any]:
        """檢查 RustFS 健康狀態"""
        health_status = {
            "container_running": False,
            "s3_api_accessible": False,
            "storage_usage": {},
            "heal_queue_status": "unknown",
            "errors": []
        }
        
        try:
            # 檢查容器狀態
            result = self._run_command([
                self.docker_compose_cmd.split()[0], 
                *self.docker_compose_cmd.split()[1:], 
                "ps", "rustfs"
            ])
            
            stdout_content = result.stdout or ""
            if "Up" in stdout_content:
                health_status["container_running"] = True
                logger.info("[OK] RustFS 容器正在運行")
            else:
                health_status["errors"].append("RustFS 容器未運行")
                logger.warning("[ERROR] RustFS 容器未運行")
            
            # 檢查 S3 API
            try:
                import requests
                response = requests.get("http://localhost:9000/", timeout=5)
                if response.status_code in [200, 403, 404]:  # 這些都表示服務在運行
                    health_status["s3_api_accessible"] = True
                    logger.info("[OK] RustFS S3 API 可訪問")
                else:
                    health_status["errors"].append(f"S3 API 返回狀態碼: {response.status_code}")
            except Exception as e:
                health_status["errors"].append(f"S3 API 不可訪問: {str(e)}")
                logger.warning(f"[ERROR] S3 API 不可訪問: {e}")
            
            # 檢查存儲使用情況
            if self.rustfs_data_dir.exists():
                storage_size = self._get_directory_size(self.rustfs_data_dir)
                health_status["storage_usage"] = {
                    "size_gb": round(storage_size / (1024**3), 2),
                    "max_size_gb": self.max_storage_size_gb,
                    "usage_percent": round((storage_size / (1024**3)) / self.max_storage_size_gb * 100, 1)
                }
            
            # 檢查日誌中的 heal queue 錯誤
            heal_errors = self._check_heal_queue_errors()
            if heal_errors > 0:
                health_status["heal_queue_status"] = "full"
                health_status["errors"].append(f"發現 {heal_errors} 個 heal queue 錯誤")
                logger.warning(f"[ERROR] 發現 {heal_errors} 個 heal queue 錯誤")
            else:
                health_status["heal_queue_status"] = "ok"
            
        except Exception as e:
            health_status["errors"].append(f"健康檢查失敗: {str(e)}")
            logger.error(f"健康檢查失敗: {e}")
        
        return health_status
    
    def _get_directory_size(self, path: Path) -> int:
        """獲取目錄大小（字節）"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = Path(dirpath) / filename
                    try:
                        total_size += filepath.stat().st_size
                    except:
                        continue
        except:
            pass
        return total_size
    
    def _check_heal_queue_errors(self) -> int:
        """檢查日誌中的 heal queue 錯誤"""
        error_count = 0
        try:
            # 檢查 Docker 日誌
            result = self._run_command([
                self.docker_compose_cmd.split()[0], 
                *self.docker_compose_cmd.split()[1:], 
                "logs", "--tail", "100", "rustfs"
            ])
            
            stdout_content = result.stdout or ""
            stderr_content = result.stderr or ""
            if "Heal queue is full" in stdout_content or "Heal queue is full" in stderr_content:
                error_count += stdout_content.count("Heal queue is full")
                error_count += stderr_content.count("Heal queue is full")
            
            # 檢查日誌文件
            if self.rustfs_logs_dir.exists():
                for log_file in self.rustfs_logs_dir.glob("*.log"):
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            error_count += content.count("Heal queue is full")
                    except:
                        continue
                        
        except Exception as e:
            logger.warning(f"檢查 heal queue 錯誤時失敗: {e}")
        
        return error_count
    
    async def cleanup_expired_media(self) -> Dict[str, Any]:
        """清理過期媒體檔案"""
        cleanup_result = {
            "files_deleted": 0,
            "space_freed_mb": 0,
            "database_cleaned": 0,
            "errors": []
        }
        
        try:
            logger.info("[CLEAN] 開始清理過期媒體檔案...")
            
            # 1. 使用 RustFS 客戶端清理
            try:
                from services.rustfs_client import get_rustfs_client
                rustfs_client = await get_rustfs_client()
                
                # 清理失敗的下載
                failed_cleaned = await rustfs_client.cleanup_failed_downloads(self.max_file_age_days * 24)
                cleanup_result["database_cleaned"] = failed_cleaned
                logger.info(f"[OK] 清理了 {failed_cleaned} 個失敗的下載記錄")
                
            except Exception as e:
                cleanup_result["errors"].append(f"RustFS 客戶端清理失敗: {str(e)}")
                logger.error(f"RustFS 客戶端清理失敗: {e}")
            
            # 2. 清理本地存儲中的舊檔案
            if self.rustfs_data_dir.exists():
                cutoff_time = datetime.now() - timedelta(days=self.max_file_age_days)
                
                for root, dirs, files in os.walk(self.rustfs_data_dir):
                    for file in files:
                        filepath = Path(root) / file
                        try:
                            file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                            if file_mtime < cutoff_time:
                                file_size = filepath.stat().st_size
                                filepath.unlink()
                                cleanup_result["files_deleted"] += 1
                                cleanup_result["space_freed_mb"] += file_size / (1024 * 1024)
                        except Exception as e:
                            cleanup_result["errors"].append(f"刪除檔案失敗 {filepath}: {str(e)}")
                
                logger.info(f"[OK] 清理了 {cleanup_result['files_deleted']} 個過期檔案，釋放 {cleanup_result['space_freed_mb']:.2f} MB 空間")
            
            # 3. 清理日誌檔案
            self._cleanup_old_logs()
            
        except Exception as e:
            cleanup_result["errors"].append(f"清理過程失敗: {str(e)}")
            logger.error(f"清理過程失敗: {e}")
        
        return cleanup_result
    
    def _cleanup_old_logs(self):
        """清理舊日誌檔案"""
        try:
            if not self.rustfs_logs_dir.exists():
                return
            
            cutoff_time = datetime.now() - timedelta(days=self.max_log_age_days)
            cleaned_count = 0
            
            for log_file in self.rustfs_logs_dir.glob("*.log"):
                try:
                    file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        log_file.unlink()
                        cleaned_count += 1
                except:
                    continue
            
            if cleaned_count > 0:
                logger.info(f"[OK] 清理了 {cleaned_count} 個舊日誌檔案")
                
        except Exception as e:
            logger.error(f"清理日誌檔案失敗: {e}")
    
    def restart_rustfs(self) -> bool:
        """重啟 RustFS 服務"""
        try:
            logger.info("[RESTART] 重啟 RustFS 服務...")
            
            # 停止服務
            result = self._run_command([
                self.docker_compose_cmd.split()[0], 
                *self.docker_compose_cmd.split()[1:], 
                "stop", "rustfs"
            ])
            
            stderr_content = result.stderr or ""
            if result.returncode != 0:
                logger.error(f"停止 RustFS 失敗: {stderr_content}")
                return False
            
            # 等待停止
            time.sleep(5)
            
            # 啟動服務
            result = self._run_command([
                self.docker_compose_cmd.split()[0], 
                *self.docker_compose_cmd.split()[1:], 
                "up", "-d", "rustfs"
            ])
            
            stderr_content = result.stderr or ""
            if result.returncode != 0:
                logger.error(f"啟動 RustFS 失敗: {stderr_content}")
                return False
            
            # 等待服務啟動
            time.sleep(10)
            
            # 驗證服務狀態
            health = self.check_rustfs_health()
            if health["container_running"]:
                logger.info("[OK] RustFS 重啟成功")
                return True
            else:
                logger.error("[ERROR] RustFS 重啟後仍未正常運行")
                return False
                
        except Exception as e:
            logger.error(f"重啟 RustFS 失敗: {e}")
            return False
    
    async def auto_maintenance(self):
        """自動維護模式"""
        logger.info("[AUTO] 開始自動維護模式...")
        
        # 1. 檢查健康狀態
        health = self.check_rustfs_health()
        logger.info(f"[INFO] 健康狀態: {json.dumps(health, indent=2, ensure_ascii=False)}")
        
        # 2. 如果存在 heal queue 錯誤，執行清理
        if health["heal_queue_status"] == "full":
            logger.warning("[WARN] 檢測到 heal queue 已滿，執行清理...")
            cleanup_result = await self.cleanup_expired_media()
            logger.info(f"[CLEAN] 清理結果: {json.dumps(cleanup_result, indent=2, ensure_ascii=False)}")
            
            # 如果清理後仍有問題，重啟服務
            time.sleep(5)
            health_after_cleanup = self.check_rustfs_health()
            if health_after_cleanup["heal_queue_status"] == "full":
                logger.warning("[WARN] 清理後仍有問題，重啟 RustFS...")
                self.restart_rustfs()
        
        # 3. 檢查存儲使用率
        if "storage_usage" in health and health["storage_usage"].get("usage_percent", 0) > 80:
            logger.warning("[WARN] 存儲使用率過高，執行清理...")
            await self.cleanup_expired_media()
        
        # 4. 定期清理（即使沒有問題也執行輕度清理）
        if datetime.now().hour == 2:  # 每天凌晨 2 點執行
            logger.info("[TIME] 定期清理時間，執行維護...")
            await self.cleanup_expired_media()

        # 5. 驗證 RustFS 與資料庫一致性（每日一次或每次 auto 都跑輕量批次）
        try:
            logger.info("[VERIFY] 開始驗證 RustFS 與 DB 一致性（輕量批次）...")
            # 在 mcp-server 容器內執行，確保環境變數一致
            result = self._run_command([
                self.docker_compose_cmd.split()[0],
                *self.docker_compose_cmd.split()[1:],
                "exec", "-T", "mcp-server",
                "python", "scripts/verify_rustfs_media.py", "--batch-size", "500"
            ], timeout=120)
            logger.info(f"[VERIFY] 結果: {(result.stdout or '').strip()}")
        except Exception as e:
            logger.warning(f"[VERIFY] 一致性驗證失敗：{e}")

        logger.info("[OK] 自動維護完成")
    
    def monitor_mode(self, interval_minutes: int = 30):
        """監控模式 - 持續監控 RustFS 狀態"""
        logger.info(f"[MONITOR] 開始監控模式，每 {interval_minutes} 分鐘檢查一次...")
        
        while True:
            try:
                asyncio.run(self.auto_maintenance())
                logger.info(f"[SLEEP] 等待 {interval_minutes} 分鐘後下次檢查...")
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("[STOP] 監控已停止")
                break
            except Exception as e:
                logger.error(f"監控過程中出錯: {e}")
                time.sleep(60)  # 出錯後等待 1 分鐘再繼續


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description="RustFS 自動管理工具")
    parser.add_argument(
        "--action", 
        choices=["cleanup", "monitor", "restart", "auto", "health"],
        default="health",
        help="執行的操作"
    )
    parser.add_argument(
        "--interval", 
        type=int, 
        default=30,
        help="監控模式的檢查間隔（分鐘）"
    )
    
    args = parser.parse_args()
    
    manager = RustFSAutoManager()
    
    try:
        if args.action == "health":
            # 健康檢查
            health = manager.check_rustfs_health()
            print(json.dumps(health, indent=2, ensure_ascii=False))
            
        elif args.action == "cleanup":
            # 執行清理
            result = asyncio.run(manager.cleanup_expired_media())
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.action == "restart":
            # 重啟服務
            success = manager.restart_rustfs()
            print(f"重啟結果: {'成功' if success else '失敗'}")
            
        elif args.action == "auto":
            # 自動維護
            asyncio.run(manager.auto_maintenance())
            
        elif args.action == "monitor":
            # 監控模式
            manager.monitor_mode(args.interval)
            
    except KeyboardInterrupt:
        logger.info("[STOP] 操作已中斷")
    except Exception as e:
        logger.error(f"操作失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
