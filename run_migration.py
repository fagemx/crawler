"""
資料庫遷移執行腳本

執行新的媒體表遷移
"""

import asyncio
import os
import sys
from pathlib import Path

# 載入環境變數
from dotenv import load_dotenv
load_dotenv()

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.db_client import get_db_client


async def run_migration():
    """執行媒體表遷移"""
    print("🚀 開始執行資料庫遷移...")
    
    try:
        # 讀取遷移 SQL 檔案
        migration_file = project_root / "database" / "migrations" / "add_media_table.sql"
        
        if not migration_file.exists():
            print(f"❌ 遷移檔案不存在: {migration_file}")
            return False
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        print(f"📄 讀取遷移檔案: {migration_file}")
        
        # 獲取資料庫客戶端
        db_client = await get_db_client()
        
        # 執行遷移
        async with db_client.get_connection() as conn:
            print("🔄 執行遷移 SQL...")
            await conn.execute(migration_sql)
            print("✅ 遷移執行成功")
        
        # 驗證遷移結果
        print("🔍 驗證遷移結果...")
        
        async with db_client.get_connection() as conn:
            # 檢查 media 表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'media'
                )
            """)
            
            if table_exists:
                print("✅ media 表創建成功")
                
                # 檢查表結構
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'media'
                    ORDER BY ordinal_position
                """)
                
                print("📋 media 表結構:")
                for col in columns:
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    print(f"   - {col['column_name']}: {col['data_type']} {nullable}")
                
                # 檢查索引
                indexes = await conn.fetch("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'media'
                    ORDER BY indexname
                """)
                
                print("🔍 media 表索引:")
                for idx in indexes:
                    print(f"   - {idx['indexname']}")
                
                # 檢查視圖
                views = await conn.fetch("""
                    SELECT viewname
                    FROM pg_views
                    WHERE viewname IN ('posts_with_media', 'media_processing_stats')
                    ORDER BY viewname
                """)
                
                print("👁️  相關視圖:")
                for view in views:
                    print(f"   - {view['viewname']}")
                
            else:
                print("❌ media 表創建失敗")
                return False
        
        print("🎉 資料庫遷移完成！")
        return True
        
    except Exception as e:
        print(f"❌ 遷移執行失敗: {str(e)}")
        return False
    
    finally:
        # 關閉資料庫連接
        if 'db_client' in locals():
            await db_client.close_pool()


async def rollback_migration():
    """回滾遷移（刪除 media 表）"""
    print("⚠️  開始回滾遷移...")
    
    try:
        db_client = await get_db_client()
        
        async with db_client.get_connection() as conn:
            # 刪除視圖
            await conn.execute("DROP VIEW IF EXISTS posts_with_media CASCADE")
            await conn.execute("DROP VIEW IF EXISTS media_processing_stats CASCADE")
            
            # 刪除觸發器和函數
            await conn.execute("DROP TRIGGER IF EXISTS trigger_update_media_last_updated ON media")
            await conn.execute("DROP FUNCTION IF EXISTS update_media_last_updated()")
            
            # 刪除表
            await conn.execute("DROP TABLE IF EXISTS media CASCADE")
            
            print("✅ 遷移回滾成功")
            return True
            
    except Exception as e:
        print(f"❌ 回滾失敗: {str(e)}")
        return False
    
    finally:
        if 'db_client' in locals():
            await db_client.close_pool()


async def main():
    """主函數"""
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        success = await rollback_migration()
    else:
        success = await run_migration()
    
    exit(0 if success else 1)


if __name__ == "__main__":
    # 檢查環境變數
    if not os.getenv("DATABASE_URL"):
        print("❌ 請設定 DATABASE_URL 環境變數")
        exit(1)
    
    print("資料庫遷移工具")
    print("使用方法:")
    print("  python run_migration.py        # 執行遷移")
    print("  python run_migration.py rollback  # 回滾遷移")
    print()
    
    asyncio.run(main())