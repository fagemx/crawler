-- Plan E 資料庫架構
-- 基於三層資料策略的最小化設計

-- ============================================================================
-- Tier-1: 長期資料存儲 (PostgreSQL)
-- ============================================================================

-- 貼文基本資料表
CREATE TABLE posts (
    url            TEXT PRIMARY KEY,
    author         TEXT,
    markdown       TEXT,          -- Jina Reader 提取的 markdown 內容
    media_urls     JSONB,         -- 媒體 URL 列表 ["https://...jpg", ...]
    created_at     TIMESTAMPTZ DEFAULT now(),
    last_seen      TIMESTAMPTZ DEFAULT now()
);

-- 貼文指標表（與 posts 分離，支援獨立更新）
CREATE TABLE post_metrics (
    url          TEXT PRIMARY KEY REFERENCES posts(url) ON DELETE CASCADE,
    views        BIGINT DEFAULT 0,
    likes        BIGINT DEFAULT 0,
    comments     BIGINT DEFAULT 0,
    reposts      BIGINT DEFAULT 0,
    shares       BIGINT DEFAULT 0,
    score        DOUBLE PRECISION GENERATED ALWAYS AS 
                 (views*1.0 + likes*0.3 + comments*0.3 + reposts*0.1 + shares*0.1) STORED,
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- 索引優化
CREATE INDEX idx_posts_author ON posts(author);
CREATE INDEX idx_posts_created_at ON posts(created_at DESC);
CREATE INDEX idx_post_metrics_score ON post_metrics(score DESC);
CREATE INDEX idx_post_metrics_updated_at ON post_metrics(updated_at DESC);

-- ============================================================================
-- 輔助表格
-- ============================================================================

-- Agent 處理記錄（追蹤處理狀態）
CREATE TABLE processing_log (
    id           SERIAL PRIMARY KEY,
    url          TEXT NOT NULL,
    agent_name   TEXT NOT NULL,
    stage        TEXT NOT NULL,  -- 'markdown', 'vision_fill', 'analysis'
    status       TEXT NOT NULL,  -- 'pending', 'completed', 'failed'
    started_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_msg    TEXT,
    metadata     JSONB
);

CREATE INDEX idx_processing_log_url ON processing_log(url);
CREATE INDEX idx_processing_log_status ON processing_log(status);

-- ============================================================================
-- Redis Key 設計文檔（註解形式）
-- ============================================================================

/*
Tier-0: Redis 臨時快取策略

1. 指標快取 (TTL: 30 天)
   HSET metrics:{url} views 4000 likes 267 comments 3 reposts 0 shares 1
   EXPIRE metrics:{url} 2592000

2. 排序快取 (TTL: 10 分鐘)
   ZADD ranking:{username} {score} {url}
   EXPIRE ranking:{username} 600

3. 處理狀態快取 (TTL: 1 小時)
   HSET task:{task_id} status running progress 0.5 posts_processed 25
   EXPIRE task:{task_id} 3600

4. 批次處理佇列
   LPUSH queue:jina_markdown {url}
   LPUSH queue:vision_fill {url}
*/

-- ============================================================================
-- 視圖和函數
-- ============================================================================

-- 完整貼文資料視圖
CREATE VIEW posts_with_metrics AS
SELECT 
    p.url,
    p.author,
    p.markdown,
    p.media_urls,
    p.created_at,
    p.last_seen,
    COALESCE(pm.views, 0) as views,
    COALESCE(pm.likes, 0) as likes,
    COALESCE(pm.comments, 0) as comments,
    COALESCE(pm.reposts, 0) as reposts,
    COALESCE(pm.shares, 0) as shares,
    COALESCE(pm.score, 0) as score,
    pm.updated_at as metrics_updated_at
FROM posts p
LEFT JOIN post_metrics pm ON p.url = pm.url;

-- 取得用戶 Top-K 貼文的函數
CREATE OR REPLACE FUNCTION get_top_posts(
    username TEXT,
    limit_count INTEGER DEFAULT 30
) RETURNS TABLE (
    url TEXT,
    markdown TEXT,
    media_urls JSONB,
    score DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.url,
        p.markdown,
        p.media_urls,
        COALESCE(pm.score, 0) as score
    FROM posts p
    LEFT JOIN post_metrics pm ON p.url = pm.url
    WHERE p.author = username
    ORDER BY COALESCE(pm.score, 0) DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- 批次插入貼文的函數
CREATE OR REPLACE FUNCTION upsert_post(
    p_url TEXT,
    p_author TEXT,
    p_markdown TEXT DEFAULT NULL,
    p_media_urls JSONB DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO posts (url, author, markdown, media_urls)
    VALUES (p_url, p_author, p_markdown, p_media_urls)
    ON CONFLICT (url) DO UPDATE SET
        markdown = COALESCE(EXCLUDED.markdown, posts.markdown),
        media_urls = COALESCE(EXCLUDED.media_urls, posts.media_urls),
        last_seen = now();
END;
$$ LANGUAGE plpgsql;

-- 批次更新指標的函數
CREATE OR REPLACE FUNCTION upsert_metrics(
    p_url TEXT,
    p_views BIGINT DEFAULT NULL,
    p_likes BIGINT DEFAULT NULL,
    p_comments BIGINT DEFAULT NULL,
    p_reposts BIGINT DEFAULT NULL,
    p_shares BIGINT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO post_metrics (url, views, likes, comments, reposts, shares)
    VALUES (p_url, 
            COALESCE(p_views, 0),
            COALESCE(p_likes, 0), 
            COALESCE(p_comments, 0),
            COALESCE(p_reposts, 0),
            COALESCE(p_shares, 0))
    ON CONFLICT (url) DO UPDATE SET
        views = COALESCE(EXCLUDED.views, post_metrics.views),
        likes = COALESCE(EXCLUDED.likes, post_metrics.likes),
        comments = COALESCE(EXCLUDED.comments, post_metrics.comments),
        reposts = COALESCE(EXCLUDED.reposts, post_metrics.reposts),
        shares = COALESCE(EXCLUDED.shares, post_metrics.shares),
        updated_at = now();
END;
$$ LANGUAGE plpgsql;