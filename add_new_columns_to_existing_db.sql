-- 為現有數據庫的 post_metrics_sql 表添加新欄位
-- 執行方式：連接到你的 PostgreSQL 數據庫並執行這個檔案

-- 添加真實貼文發布時間欄位
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS post_published_at TIMESTAMPTZ;

-- 添加主題標籤列表欄位
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]';

-- 驗證欄位是否成功添加
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'post_metrics_sql' 
AND column_name IN ('post_published_at', 'tags');

-- 顯示完整的表結構
\d post_metrics_sql

COMMENT ON COLUMN post_metrics_sql.post_published_at IS '真實貼文發布時間 (從DOM提取)';
COMMENT ON COLUMN post_metrics_sql.tags IS '主題標籤列表 (從標籤連結提取)';

-- 執行完成訊息
SELECT '✅ 數據庫欄位更新完成！新欄位：post_published_at, tags' AS status;