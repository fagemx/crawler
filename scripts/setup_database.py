#!/usr/bin/env python3
"""
自動資料庫初始化腳本
確保所有必要的資料表和索引都已建立，支援 idempotent 重複執行
"""

import asyncio
import asyncpg
import os
import sys
import logging
from pathlib import Path

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def setup_database():
    """自動初始化資料庫（若目標 DB 不存在則自動建立）"""
    # 從環境變數獲取資料庫連線資訊
    db_host = os.getenv('POSTGRES_HOST', 'postgres')
    db_port = int(os.getenv('POSTGRES_PORT', 5432))
    db_name = os.getenv('POSTGRES_DB', 'social_media_db')
    db_user = os.getenv('POSTGRES_USER', 'postgres')
    db_password = os.getenv('POSTGRES_PASSWORD', 'password')

    max_retries = 30
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            logger.info(f"嘗試連線資料庫 {db_name} ... (第 {attempt + 1}/{max_retries} 次)")

            conn = None
            try:
                # 直接嘗試連線到目標資料庫
                conn = await asyncpg.connect(
                    host=db_host,
                    port=db_port,
                    database=db_name,
                    user=db_user,
                    password=db_password,
                )
            except asyncpg.InvalidCatalogNameError:
                # 目標資料庫不存在 → 切到系統庫 postgres 建立後再連
                logger.warning(f"目標資料庫 {db_name} 不存在，嘗試自動建立...")
                admin_conn = await asyncpg.connect(
                    host=db_host,
                    port=db_port,
                    database='postgres',
                    user=db_user,
                    password=db_password,
                )
                try:
                    # 注意：CREATE DATABASE 需在非交易中執行，asyncpg 預設可行
                    await admin_conn.execute(f'CREATE DATABASE {db_name};')
                    logger.info(f"已建立資料庫 {db_name}")
                except asyncpg.DuplicateDatabaseError:
                    logger.info(f"資料庫 {db_name} 已存在（競態條件），忽略錯誤")
                finally:
                    await admin_conn.close()

                # 稍等片刻讓新庫可用，再次連線
                await asyncio.sleep(1)
                conn = await asyncpg.connect(
                    host=db_host,
                    port=db_port,
                    database=db_name,
                    user=db_user,
                    password=db_password,
                )

            logger.info("資料庫連線成功，開始執行初始化腳本...")

            # 讀取初始化 SQL 腳本
            sql_file = Path(__file__).parent / 'init-db.sql'
            if not sql_file.exists():
                logger.error(f"找不到 SQL 腳本檔案: {sql_file}")
                return False

            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            # 執行 SQL 腳本（允許包含多個語句與 DO $$ ... $$ 區塊）
            await conn.execute(sql_content)

            # 檢查關鍵表格是否存在
            tables_to_check = [
                'posts', 'post_metrics', 'media_files', 'media_descriptions',
                'mcp_agents', 'crawl_state', 'post_metrics_sql', 'playwright_post_metrics'
            ]

            missing_tables = []
            for table in tables_to_check:
                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = $1
                    )
                    """,
                    table,
                )

                if not exists:
                    missing_tables.append(table)
                else:
                    logger.info(f"✓ 表格 {table} 已存在")

            if missing_tables:
                logger.error(f"以下表格缺失: {missing_tables}")
                return False

            # 關閉連線
            await conn.close()

            logger.info("🎉 資料庫初始化完成！所有必要的表格和索引都已就緒")
            return True

        except (OSError, asyncpg.PostgresError) as e:
            logger.warning(f"連線或資料庫錯誤 (第 {attempt + 1} 次): {e}")
            if attempt < max_retries - 1:
                logger.info(f"等待 {retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("資料庫連線失敗，已達最大重試次數")
                return False

        except Exception as e:
            logger.error(f"執行資料庫初始化時發生錯誤: {e}")
            logger.error(f"錯誤類型: {type(e).__name__}")
            import traceback
            logger.error(f"詳細錯誤: {traceback.format_exc()}")
            return False

async def main():
    """主程式進入點"""
    logger.info("🚀 開始自動資料庫初始化...")
    
    success = await setup_database()
    
    if success:
        logger.info("✅ 資料庫初始化成功完成")
        sys.exit(0)
    else:
        logger.error("❌ 資料庫初始化失敗")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())