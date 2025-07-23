#!/usr/bin/env python3
"""
開發環境啟動腳本

用於快速啟動所有必要的服務進行開發和測試
"""

import os
import sys
import subprocess
import time
import signal
import asyncio
from pathlib import Path
from typing import List, Dict

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common.settings import get_settings, validate_required_configs


class ServiceManager:
    """服務管理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.processes: List[subprocess.Popen] = []
        self.services = {
            "mcp_server": {
                "command": ["python", "-m", "mcp_server.server"],
                "port": self.settings.mcp.server_port,
                "name": "MCP Server"
            },
            "crawler_agent": {
                "command": ["python", "-m", "agents.crawler.main"],
                "port": self.settings.agents.crawler_agent_port,
                "name": "Crawler Agent"
            }
        }
    
    def check_prerequisites(self) -> bool:
        """檢查前置條件"""
        print("=== 檢查前置條件 ===")
        
        # 檢查必要配置
        missing_configs = validate_required_configs()
        if missing_configs:
            print(f"❌ 缺少必要配置: {', '.join(missing_configs)}")
            print("請檢查 .env 檔案或環境變數")
            return False
        
        print("✅ 所有必要配置已設置")
        
        # 檢查端口是否被佔用
        for service_name, service_info in self.services.items():
            port = service_info["port"]
            if self.is_port_in_use(port):
                print(f"❌ 端口 {port} 已被佔用 ({service_info['name']})")
                return False
        
        print("✅ 所有端口可用")
        return True
    
    def is_port_in_use(self, port: int) -> bool:
        """檢查端口是否被佔用"""
        import socket
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    
    def start_service(self, service_name: str) -> subprocess.Popen:
        """啟動單個服務"""
        service_info = self.services[service_name]
        
        print(f"🚀 啟動 {service_info['name']} (端口 {service_info['port']})")
        
        try:
            process = subprocess.Popen(
                service_info["command"],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes.append(process)
            return process
            
        except Exception as e:
            print(f"❌ 啟動 {service_info['name']} 失敗: {e}")
            return None
    
    def wait_for_service(self, port: int, timeout: int = 30) -> bool:
        """等待服務啟動"""
        import socket
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    if s.connect_ex(('localhost', port)) == 0:
                        return True
            except:
                pass
            
            time.sleep(1)
        
        return False
    
    def start_all_services(self):
        """啟動所有服務"""
        print("=== 啟動開發環境 ===")
        
        # 按順序啟動服務
        service_order = ["mcp_server", "crawler_agent"]
        
        for service_name in service_order:
            process = self.start_service(service_name)
            
            if process:
                # 等待服務啟動
                port = self.services[service_name]["port"]
                if self.wait_for_service(port, timeout=15):
                    print(f"✅ {self.services[service_name]['name']} 啟動成功")
                else:
                    print(f"⚠️  {self.services[service_name]['name']} 可能啟動失敗")
            
            time.sleep(2)  # 給服務一些時間完全啟動
        
        print("\n=== 服務狀態 ===")
        self.print_service_status()
    
    def print_service_status(self):
        """打印服務狀態"""
        for service_name, service_info in self.services.items():
            port = service_info["port"]
            name = service_info["name"]
            
            if self.is_port_in_use(port):
                print(f"✅ {name}: http://localhost:{port}")
            else:
                print(f"❌ {name}: 未運行")
    
    def stop_all_services(self):
        """停止所有服務"""
        print("\n=== 停止所有服務 ===")
        
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print("✅ 服務已停止")
            except subprocess.TimeoutExpired:
                process.kill()
                print("⚠️  強制終止服務")
            except Exception as e:
                print(f"❌ 停止服務時發生錯誤: {e}")
    
    def run_interactive(self):
        """互動式運行"""
        if not self.check_prerequisites():
            return
        
        try:
            self.start_all_services()
            
            print("\n=== 開發環境已啟動 ===")
            print("按 Ctrl+C 停止所有服務")
            print("\n可用端點:")
            print(f"- MCP Server: http://localhost:{self.settings.mcp.server_port}")
            print(f"- Crawler Agent: http://localhost:{self.settings.agents.crawler_agent_port}")
            print(f"- Health Check: curl http://localhost:{self.settings.mcp.server_port}/health")
            
            # 等待中斷信號
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n收到中斷信號，正在停止服務...")
        finally:
            self.stop_all_services()


def main():
    """主函數"""
    print("🚀 社交媒體內容生成系統 - 開發環境啟動器")
    print("=" * 50)
    
    # 檢查是否在專案根目錄
    if not (project_root / ".env.example").exists():
        print("❌ 請在專案根目錄執行此腳本")
        sys.exit(1)
    
    # 檢查 .env 檔案
    env_file = project_root / ".env"
    if not env_file.exists():
        print("⚠️  未找到 .env 檔案")
        print("請複製 .env.example 為 .env 並填入必要配置")
        
        response = input("是否要自動創建基本的 .env 檔案？(y/N): ")
        if response.lower() == 'y':
            import shutil
            shutil.copy(project_root / ".env.example", env_file)
            print("✅ 已創建 .env 檔案，請編輯後重新運行")
        
        sys.exit(1)
    
    # 創建服務管理器並運行
    service_manager = ServiceManager()
    service_manager.run_interactive()


if __name__ == "__main__":
    main()