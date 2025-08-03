#!/usr/bin/env python3
"""
執行雙軌狀態欄位遷移的腳本
使用方式: python run_dual_track_migration.py
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 加入專案路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.db_client import DatabaseClient

async def run_migration():
    """執行雙軌狀態欄位遷移"""
    
    print("🔧 開始執行雙軌狀態欄位遷移...")
    
    try:
        # 初始化數據庫連接
        db_client = DatabaseClient()
        
        async with db_client.get_connection() as conn:
            print("🔗 已連接到數據庫")
            
            # 檢查欄位是否已存在
            check_columns_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'post_metrics_sql' 
            AND column_name IN ('reader_status', 'dom_status', 'reader_processed_at', 'dom_processed_at');
            """
            
            existing_columns = await conn.fetch(check_columns_sql)
            existing_column_names = [row['column_name'] for row in existing_columns]
            
            print(f"📋 現有新欄位: {existing_column_names}")
            
            # 執行遷移
            migrations = [
                ("reader_status", "ALTER TABLE post_metrics_sql ADD COLUMN IF NOT EXISTS reader_status TEXT DEFAULT 'pending';"),
                ("dom_status", "ALTER TABLE post_metrics_sql ADD COLUMN IF NOT EXISTS dom_status TEXT DEFAULT 'pending';"),
                ("reader_processed_at", "ALTER TABLE post_metrics_sql ADD COLUMN IF NOT EXISTS reader_processed_at TIMESTAMPTZ;"),
                ("dom_processed_at", "ALTER TABLE post_metrics_sql ADD COLUMN IF NOT EXISTS dom_processed_at TIMESTAMPTZ;")
            ]
            
            for column_name, sql in migrations:
                if column_name not in existing_column_names:
                    print(f"➕ 添加 {column_name} 欄位...")
                    await conn.execute(sql)
                    print(f"✅ {column_name} 欄位添加成功")
                else:
                    print(f"ℹ️ {column_name} 欄位已存在")
            
            # 為現有數據推斷狀態
            print("🔄 為現有數據推斷狀態...")
            
            # 推斷Reader狀態
            reader_update_sql = """
            UPDATE post_metrics_sql 
            SET reader_status = 'success', 
                reader_processed_at = fetched_at
            WHERE (content IS NOT NULL AND content != '') 
              AND source IN ('reader', 'jina')
              AND reader_status = 'pending';
            """
            reader_result = await conn.execute(reader_update_sql)
            print(f"✅ 推斷 Reader 狀態: {reader_result} 筆記錄")
            
            # 推斷DOM狀態
            dom_update_sql = """
            UPDATE post_metrics_sql 
            SET dom_status = 'success',
                dom_processed_at = fetched_at  
            WHERE is_complete = true 
              AND source IN ('playwright', 'crawler', 'apify')
              AND dom_status = 'pending';
            """
            dom_result = await conn.execute(dom_update_sql)
            print(f"✅ 推斷 DOM 狀態: {dom_result} 筆記錄")
            
            # 創建索引
            print("📊 創建性能索引...")
            index_sqls = [
                "CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_reader_status ON post_metrics_sql(reader_status);",
                "CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_dom_status ON post_metrics_sql(dom_status);",
                "CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_dual_status ON post_metrics_sql(username, reader_status, dom_status);"
            ]
            
            for sql in index_sqls:
                await conn.execute(sql)
            print("✅ 索引創建完成")
            
            # 添加註釋
            comment_sqls = [
                "COMMENT ON COLUMN post_metrics_sql.reader_status IS 'Reader處理狀態: pending/success/failed';",
                "COMMENT ON COLUMN post_metrics_sql.dom_status IS 'DOM爬取狀態: pending/success/failed';",
                "COMMENT ON COLUMN post_metrics_sql.reader_processed_at IS 'Reader處理完成時間';",
                "COMMENT ON COLUMN post_metrics_sql.dom_processed_at IS 'DOM處理完成時間';"
            ]
            
            for sql in comment_sqls:
                await conn.execute(sql)
            
            # 驗證結果
            final_check_sql = """
            SELECT 
                COUNT(*) as total_posts,
                COUNT(CASE WHEN reader_status = 'success' THEN 1 END) as reader_complete,
                COUNT(CASE WHEN dom_status = 'success' THEN 1 END) as dom_complete,
                COUNT(CASE WHEN reader_status = 'pending' THEN 1 END) as needs_reader,
                COUNT(CASE WHEN dom_status = 'pending' THEN 1 END) as needs_dom
            FROM post_metrics_sql;
            """
            
            stats = await conn.fetchrow(final_check_sql)
            
            print("\n📊 遷移結果統計:")
            print(f"  - 總貼文數: {stats['total_posts']}")
            print(f"  - Reader完成: {stats['reader_complete']}")
            print(f"  - DOM完成: {stats['dom_complete']}")
            print(f"  - 需要Reader: {stats['needs_reader']}")
            print(f"  - 需要DOM: {stats['needs_dom']}")
            
            print("\n🎉 雙軌狀態欄位遷移完成！")
            print("💡 現在可以使用新的API端點: GET /urls/{username}")
            return True
                
    except Exception as e:
        print(f"❌ 遷移失敗: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)