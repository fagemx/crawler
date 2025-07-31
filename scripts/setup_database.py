#!/usr/bin/env python3
"""
資料庫設置腳本

在 PostgreSQL 容器啟動後執行資料庫初始化
"""

import asyncio
import asyncpg
import sys
import time
from pathlib import Path


async def wait_for_postgres(host="localhost", port=5432, user="postgres", password="password", database="social_media_db", max_retries=30):
    """等待 PostgreSQL 準備就緒"""
    print(f"🔍 Waiting for PostgreSQL at {host}:{port}...")
    
    for attempt in range(max_retries):
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=5
            )
            await conn.close()
            print("✅ PostgreSQL is ready")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"   Attempt {attempt + 1}/{max_retries} failed, retrying in 2s...")
                await asyncio.sleep(2)
            else:
                print(f"❌ PostgreSQL not ready after {max_retries} attempts: {e}")
                return False
    
    return False


async def execute_sql_file(sql_file_path: Path, host="localhost", port=5432, user="postgres", password="password", database="social_media_db"):
    """執行 SQL 檔案"""
    print(f"📋 Executing SQL file: {sql_file_path}")
    
    if not sql_file_path.exists():
        print(f"❌ SQL file not found: {sql_file_path}")
        return False
    
    try:
        # 讀取 SQL 檔案
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 連接資料庫
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        
        # 執行 SQL
        await conn.execute(sql_content)
        await conn.close()
        
        print("✅ SQL file executed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to execute SQL file: {e}")
        return False


async def setup_database():
    """設置資料庫"""
    print("🚀 Database Setup Script")
    print("=" * 40)
    
    # 1. 等待 PostgreSQL 準備就緒
    if not await wait_for_postgres():
        return False
    
    # 2. 執行初始化 SQL
    sql_file = Path(__file__).parent / "init-db.sql"
    if not await execute_sql_file(sql_file):
        return False
    
    # 3. 驗證設置
    print("\n🔍 Verifying database setup...")
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="password",
            database="social_media_db"
        )
        
        # 檢查表格是否存在
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        table_names = [row['table_name'] for row in tables]
        print(f"✅ Found {len(table_names)} tables: {', '.join(table_names)}")
        
        await conn.close()
        
        print("\n🎉 Database setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Setup Script")
    parser.add_argument("--host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--user", default="postgres", help="PostgreSQL user")
    parser.add_argument("--password", default="password", help="PostgreSQL password")
    parser.add_argument("--database", default="social_media_db", help="Database name")
    
    args = parser.parse_args()
    
    # 執行設置
    success = asyncio.run(setup_database())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()