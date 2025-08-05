-- 完全修復 playwright_post_metrics 表的最終方案
-- 執行方式：docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/fix_playwright_table_final.sql

-- 1. 備份現有數據（如果有的話）
CREATE TABLE IF NOT EXISTS playwright_post_metrics_backup AS SELECT * FROM playwright_post_metrics;

-- 2. 刪除舊表（結構有問題）
DROP TABLE IF EXISTS playwright_post_metrics CASCADE;

-- 3. 重建正確的表結構
CREATE TABLE playwright_post_metrics (
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
    UNIQUE(username, post_id, crawler_type)  -- 關鍵：UNIQUE 約束
);

-- 4. 創建性能索引
CREATE INDEX IF NOT EXISTS idx_playwright_username_created ON playwright_post_metrics(username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playwright_crawl_id ON playwright_post_metrics(crawl_id);
CREATE INDEX IF NOT EXISTS idx_playwright_source ON playwright_post_metrics(source);
CREATE INDEX IF NOT EXISTS idx_playwright_crawler_type ON playwright_post_metrics(crawler_type);

-- 5. 顯示修復結果
SELECT 'Playwright table completely rebuilt!' as status;

-- 6. 顯示表結構確認
\d playwright_post_metrics;

-- 7. 顯示約束信息
SELECT conname, contype, pg_get_constraintdef(oid) as definition
FROM pg_constraint 
WHERE conrelid = 'playwright_post_metrics'::regclass;