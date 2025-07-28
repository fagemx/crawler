-- 添加媒體表以支援 RustFS 媒體存儲
-- 執行時間: 2025-01-25

-- 創建媒體表
CREATE TABLE IF NOT EXISTS media (
    id SERIAL PRIMARY KEY,
    post_id TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
    cdn_url TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'uploaded', 'analyzed', 'failed')) DEFAULT 'pending',
    size_bytes INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    
    -- 確保同一個貼文的同一個 CDN URL 只有一條記錄
    UNIQUE(post_id, cdn_url)
);

-- 創建索引以提升查詢效能
CREATE INDEX IF NOT EXISTS idx_media_post_id ON media(post_id);
CREATE INDEX IF NOT EXISTS idx_media_storage_key ON media(storage_key);
CREATE INDEX IF NOT EXISTS idx_media_status ON media(status);
CREATE INDEX IF NOT EXISTS idx_media_created_at ON media(created_at);

-- 添加外鍵約束（如果 posts 表存在）
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'posts') THEN
        -- 注意：這裡假設 posts 表的主鍵是 url，而 media.post_id 對應 posts.url
        -- 如果結構不同，請調整此約束
        ALTER TABLE media 
        ADD CONSTRAINT fk_media_post_id 
        FOREIGN KEY (post_id) REFERENCES posts(url) 
        ON DELETE CASCADE;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN
        -- 外鍵約束已存在，忽略錯誤
        NULL;
END $$;

-- 創建觸發器以自動更新 last_updated 欄位
CREATE OR REPLACE FUNCTION update_media_last_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_media_last_updated ON media;
CREATE TRIGGER trigger_update_media_last_updated
    BEFORE UPDATE ON media
    FOR EACH ROW
    EXECUTE FUNCTION update_media_last_updated();

-- 添加註釋
COMMENT ON TABLE media IS '媒體檔案存儲記錄表 - 追蹤從 CDN 下載並存儲到 RustFS 的媒體檔案';
COMMENT ON COLUMN media.post_id IS '貼文 ID，對應 posts.url';
COMMENT ON COLUMN media.media_type IS '媒體類型：image 或 video';
COMMENT ON COLUMN media.cdn_url IS '原始 CDN URL';
COMMENT ON COLUMN media.storage_key IS 'RustFS 存儲 key，格式：{post_id}/{hash}.{ext}';
COMMENT ON COLUMN media.status IS '處理狀態：pending, uploaded, analyzed, failed';
COMMENT ON COLUMN media.size_bytes IS '檔案大小（bytes）';

-- 創建便利視圖：貼文及其媒體
CREATE OR REPLACE VIEW posts_with_media AS
SELECT 
    p.url,
    p.author,
    p.markdown,
    p.created_at as post_created_at,
    p.last_seen,
    pm.views,
    pm.likes,
    pm.comments,
    pm.reposts,
    pm.shares,
    pm.score,
    pm.updated_at as metrics_updated_at,
    COALESCE(
        json_agg(
            json_build_object(
                'media_type', m.media_type,
                'cdn_url', m.cdn_url,
                'storage_key', m.storage_key,
                'status', m.status,
                'size_bytes', m.size_bytes
            )
        ) FILTER (WHERE m.id IS NOT NULL),
        '[]'::json
    ) as media_files
FROM posts p
LEFT JOIN post_metrics pm ON p.url = pm.url
LEFT JOIN media m ON p.url = m.post_id
GROUP BY 
    p.url, p.author, p.markdown, p.created_at, p.last_seen,
    pm.views, pm.likes, pm.comments, pm.reposts, pm.shares, pm.score, pm.updated_at;

COMMENT ON VIEW posts_with_media IS '貼文及其媒體檔案的完整視圖';

-- 創建統計視圖：媒體處理統計
CREATE OR REPLACE VIEW media_processing_stats AS
SELECT 
    media_type,
    status,
    COUNT(*) as count,
    SUM(size_bytes) as total_size_bytes,
    AVG(size_bytes) as avg_size_bytes,
    MIN(created_at) as earliest_created,
    MAX(created_at) as latest_created
FROM media
GROUP BY media_type, status
ORDER BY media_type, status;

COMMENT ON VIEW media_processing_stats IS '媒體處理統計視圖';

-- 插入測試數據（可選，用於開發測試）
-- INSERT INTO media (post_id, media_type, cdn_url, storage_key, status, size_bytes)
-- VALUES 
--     ('test_post_001', 'image', 'https://example.com/image1.jpg', 'test_post_001/abc123.jpg', 'uploaded', 150000),
--     ('test_post_002', 'video', 'https://example.com/video1.mp4', 'test_post_002/def456.mp4', 'analyzed', 5000000);

COMMIT;