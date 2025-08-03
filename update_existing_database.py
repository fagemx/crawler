#!/usr/bin/env python3
"""
為現有數據庫添加新欄位的一次性更新腳本
執行方式: python update_existing_database.py
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

async def update_database():
    """添加新欄位到現有數據庫"""
    
    print("🔧 開始更新現有數據庫...")
    
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
            AND column_name IN ('post_published_at', 'tags');
            """
            
            existing_columns = await conn.fetch(check_columns_sql)
            existing_column_names = [row['column_name'] for row in existing_columns]
            
            print(f"📋 現有新欄位: {existing_column_names}")
            
            # 添加 post_published_at 欄位
            if 'post_published_at' not in existing_column_names:
                print("➕ 添加 post_published_at 欄位...")
                await conn.execute("""
                    ALTER TABLE post_metrics_sql 
                    ADD COLUMN post_published_at TIMESTAMPTZ;
                """)
                await conn.execute("""
                    COMMENT ON COLUMN post_metrics_sql.post_published_at 
                    IS '真實貼文發布時間 (從DOM提取)';
                """)
                print("✅ post_published_at 欄位添加成功")
            else:
                print("ℹ️ post_published_at 欄位已存在")
            
            # 添加 tags 欄位
            if 'tags' not in existing_column_names:
                print("➕ 添加 tags 欄位...")
                await conn.execute("""
                    ALTER TABLE post_metrics_sql 
                    ADD COLUMN tags JSONB DEFAULT '[]';
                """)
                await conn.execute("""
                    COMMENT ON COLUMN post_metrics_sql.tags 
                    IS '主題標籤列表 (從標籤連結提取)';
                """)
                print("✅ tags 欄位添加成功")
            else:
                print("ℹ️ tags 欄位已存在")
            
            # 驗證最終結果
            final_check_sql = """
            SELECT column_name, data_type, is_nullable, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'post_metrics_sql' 
            AND column_name IN ('post_published_at', 'tags')
            ORDER BY column_name;
            """
            
            final_columns = await conn.fetch(final_check_sql)
            
            print("\n📊 新欄位驗證結果:")
            for col in final_columns:
                print(f"  - {col['column_name']}: {col['data_type']} "
                      f"(nullable: {col['is_nullable']}, default: {col['column_default']})")
            
            if len(final_columns) == 2:
                print("\n🎉 數據庫更新完成！")
                print("💡 現在可以使用 docker compose up -d --build 重新部署")
                return True
            else:
                print(f"\n❌ 更新失敗，只找到 {len(final_columns)}/2 個欄位")
                return False
                
    except Exception as e:
        print(f"❌ 數據庫更新失敗: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(update_database())
    sys.exit(0 if success else 1)