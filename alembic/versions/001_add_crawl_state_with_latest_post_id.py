"""add crawl_state with latest_post_id optimization

Revision ID: 001
Revises: 
Create Date: 2025-08-02 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """創建優化的crawl_state表，支持增量爬取和早停機制"""
    
    # 創建crawl_state表（基於用戶優化建議）
    op.execute(text("""
        CREATE TABLE crawl_state (
            username        TEXT PRIMARY KEY,
            latest_post_id  TEXT,                    -- 最新post_id，避免全表掃描
            total_crawled   INTEGER DEFAULT 0,       -- 總爬取數量
            last_crawl_at   TIMESTAMPTZ DEFAULT NOW(), -- 最後爬取時間
            created_at      TIMESTAMPTZ DEFAULT NOW()  -- 創建時間
        );
    """))
    
    # 為PostMetrics添加唯一約束（如果使用SQL表的話）
    # 注意：這裡假設你後續會從Pydantic轉換到真正的SQL表
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS post_metrics_sql (
            id              SERIAL PRIMARY KEY,
            post_id         TEXT UNIQUE NOT NULL,     -- 關鍵：唯一約束
            username        TEXT NOT NULL,
            url             TEXT NOT NULL,
            content         TEXT,
            likes_count     INTEGER DEFAULT 0,
            comments_count  INTEGER DEFAULT 0,
            reposts_count   INTEGER DEFAULT 0,
            shares_count    INTEGER DEFAULT 0,
            views_count     BIGINT DEFAULT 0,
            calculated_score DOUBLE PRECISION,
            images          JSONB DEFAULT '[]',
            videos          JSONB DEFAULT '[]',
            created_at      TIMESTAMPTZ NOT NULL,
            fetched_at      TIMESTAMPTZ DEFAULT NOW(),
            views_fetched_at TIMESTAMPTZ,
            -- 新增PostMetrics模型的額外字段
            source          TEXT DEFAULT 'unknown',   -- 數據來源
            processing_stage TEXT DEFAULT 'initial',  -- 處理階段  
            is_complete     BOOLEAN DEFAULT FALSE     -- 數據是否完整
        );
    """))
    
    # 性能優化索引
    op.execute(text("""
        CREATE INDEX idx_crawl_state_latest_post_id ON crawl_state(latest_post_id);
        CREATE INDEX idx_post_metrics_username ON post_metrics_sql(username);
        CREATE INDEX idx_post_metrics_created_at ON post_metrics_sql(created_at DESC);
        CREATE INDEX idx_post_metrics_score ON post_metrics_sql(calculated_score DESC);
    """))


def downgrade() -> None:
    """回滾migration"""
    op.execute(text("DROP TABLE IF EXISTS crawl_state CASCADE;"))
    op.execute(text("DROP TABLE IF EXISTS post_metrics_sql CASCADE;"))