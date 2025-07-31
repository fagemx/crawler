#!/usr/bin/env python3
"""
MCP Server 啟動腳本

用於開發環境啟動 MCP Server
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common.settings import get_settings, validate_required_configs
from common.db_client import get_db_client
from mcp_server.server import mcp_server


async def check_dependencies():
    """檢查依賴服務"""
    print("🔍 Checking dependencies...")
    
    # 檢查配置
    missing_configs = validate_required_configs()
    if missing_configs:
        print(f"❌ Missing required configurations: {', '.join(missing_configs)}")
        return False
    
    # 檢查資料庫連接
    try:
        db_client = await get_db_client()
        async with db_client.get_connection() as conn:
            await conn.fetchval("SELECT 1")
        print("✅ Database connection OK")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # 檢查 Redis 連接
    try:
        import redis.asyncio as redis
        settings = get_settings()
        redis_client = redis.from_url(settings.redis.url)
        await redis_client.ping()
        await redis_client.close()
        print("✅ Redis connection OK")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False
    
    return True


async def initialize_database():
    """初始化資料庫"""
    print("🔧 Initializing database...")
    
    try:
        db_client = await get_db_client()
        
        # 檢查是否需要初始化
        async with db_client.get_connection() as conn:
            # 檢查 mcp_agents 表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'mcp_agents'
                )
            """)
            
            if not table_exists:
                print("📋 Running database initialization script...")
                
                # 讀取並執行初始化腳本
                init_script_path = project_root / "scripts" / "init-db.sql"
                if init_script_path.exists():
                    with open(init_script_path, 'r', encoding='utf-8') as f:
                        init_script = f.read()
                    
                    await conn.execute(init_script)
                    print("✅ Database initialized successfully")
                else:
                    print("❌ Database initialization script not found")
                    return False
            else:
                print("✅ Database already initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False


async def start_server():
    """啟動 MCP Server"""
    print("🚀 Starting MCP Server...")
    
    # 檢查依賴
    if not await check_dependencies():
        print("❌ Dependency check failed")
        return False
    
    # 初始化資料庫
    if not await initialize_database():
        print("❌ Database initialization failed")
        return False
    
    # 初始化 MCP Server
    try:
        await mcp_server.initialize()
        print("✅ MCP Server initialized successfully")
    except Exception as e:
        print(f"❌ MCP Server initialization failed: {e}")
        return False
    
    # 啟動 FastAPI 服務器
    import uvicorn
    from mcp_server.server import app
    
    settings = get_settings()
    
    print(f"🌐 Starting server on {settings.mcp.server_host}:{settings.mcp.server_port}")
    print(f"📊 Dashboard: http://{settings.mcp.server_host}:{settings.mcp.server_port}/docs")
    
    try:
        uvicorn.run(
            app,
            host=settings.mcp.server_host,
            port=settings.mcp.server_port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server failed: {e}")
        return False
    
    return True


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Server Starter")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies, don't start server"
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize database and exit"
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        # 只檢查依賴
        async def check_only():
            success = await check_dependencies()
            exit(0 if success else 1)
        
        asyncio.run(check_only())
    
    elif args.init_db:
        # 只初始化資料庫
        async def init_only():
            success = await initialize_database()
            exit(0 if success else 1)
        
        asyncio.run(init_only())
    
    else:
        # 啟動服務器
        asyncio.run(start_server())


if __name__ == "__main__":
    main()