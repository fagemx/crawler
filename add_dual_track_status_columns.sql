-- 為現有post_metrics_sql表添加雙軌狀態追蹤欄位
-- 執行方式：連接到PostgreSQL數據庫並執行此檔案

-- 添加Reader狀態欄位
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS reader_status TEXT DEFAULT 'pending';

-- 添加DOM狀態欄位  
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS dom_status TEXT DEFAULT 'pending';

-- 添加Reader處理時間欄位
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS reader_processed_at TIMESTAMPTZ;

-- 添加DOM處理時間欄位
ALTER TABLE post_metrics_sql 
ADD COLUMN IF NOT EXISTS dom_processed_at TIMESTAMPTZ;

-- 為現有數據推斷狀態（基於已有數據）
UPDATE post_metrics_sql 
SET reader_status = 'success', 
    reader_processed_at = fetched_at
WHERE (content IS NOT NULL AND content != '') 
  AND source IN ('reader', 'jina')
  AND reader_status = 'pending';

UPDATE post_metrics_sql 
SET dom_status = 'success',
    dom_processed_at = fetched_at  
WHERE is_complete = true 
  AND source IN ('playwright', 'crawler', 'apify')
  AND dom_status = 'pending';

-- 創建索引優化查詢性能
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_reader_status ON post_metrics_sql(reader_status);
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_dom_status ON post_metrics_sql(dom_status);
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_dual_status ON post_metrics_sql(username, reader_status, dom_status);

-- 添加註釋
COMMENT ON COLUMN post_metrics_sql.reader_status IS 'Reader處理狀態: pending/success/failed';
COMMENT ON COLUMN post_metrics_sql.dom_status IS 'DOM爬取狀態: pending/success/failed';  
COMMENT ON COLUMN post_metrics_sql.reader_processed_at IS 'Reader處理完成時間';
COMMENT ON COLUMN post_metrics_sql.dom_processed_at IS 'DOM處理完成時間';

-- 驗證結果
SELECT 
    'Columns added successfully' as status,
    COUNT(*) as total_posts,
    COUNT(CASE WHEN reader_status = 'success' THEN 1 END) as reader_complete,
    COUNT(CASE WHEN dom_status = 'success' THEN 1 END) as dom_complete
FROM post_metrics_sql;