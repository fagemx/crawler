-- 修復 Ubuntu 部署環境缺少的資料庫表
-- 執行方式：psql -h localhost -U postgres -d social_media_db -f scripts/fix_ubuntu_database.sql

-- 1. 創建 playwright_post_metrics 表（如果不存在）
CREATE TABLE IF NOT EXISTS playwright_post_metrics (
    id                  SERIAL PRIMARY KEY,
    username            VARCHAR(255) NOT NULL,
    post_id             VARCHAR(255) NOT NULL,
    url                 TEXT,
    content             TEXT,
    views_count         INTEGER,
    likes_count         INTEGER,
    comments_count      INTEGER,
    reposts_count       INTEGER,
    shares_count        INTEGER,
    calculated_score    DECIMAL,
    post_published_at   TIMESTAMP,
    tags                TEXT,
    images              TEXT,
    videos              TEXT,
    source              VARCHAR(100) DEFAULT 'playwright_agent',
    crawler_type        VARCHAR(50) DEFAULT 'playwright',
    crawl_id            VARCHAR(255),
    created_at          TIMESTAMP,
    fetched_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, post_id, crawler_type)
);

-- 2. 為 playwright_post_metrics 創建索引
CREATE INDEX IF NOT EXISTS idx_playwright_post_metrics_username_created 
ON playwright_post_metrics(username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_playwright_post_metrics_post_id 
ON playwright_post_metrics(post_id);

CREATE INDEX IF NOT EXISTS idx_playwright_post_metrics_crawl_id 
ON playwright_post_metrics(crawl_id);

CREATE INDEX IF NOT EXISTS idx_playwright_post_metrics_source 
ON playwright_post_metrics(source);

CREATE INDEX IF NOT EXISTS idx_playwright_post_metrics_crawler_type 
ON playwright_post_metrics(crawler_type);

-- 3. 確保其他必要的表也存在（來自 init-db.sql）
-- 這些可能已經通過 alembic 創建，但以防萬一

-- crawl_state 表
CREATE TABLE IF NOT EXISTS crawl_state (
    username        TEXT PRIMARY KEY,
    latest_post_id  TEXT,
    total_crawled   INTEGER DEFAULT 0,
    last_crawl_at   TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 為 crawl_state 創建索引
CREATE INDEX IF NOT EXISTS idx_crawl_state_latest_post_id ON crawl_state(latest_post_id);

-- 檢查所有表是否存在
SELECT 'Table exists: ' || table_name as status 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('post_metrics_sql', 'playwright_post_metrics', 'crawl_state', 'posts', 'post_metrics')
ORDER BY table_name;

-- 顯示完成信息
SELECT 'Ubuntu database fix completed successfully!' as status;