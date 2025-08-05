-- 立即修復當前部署環境的 playwright_post_metrics 表
-- 執行方式：docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/fix_current_deployment.sql

-- 1. 添加缺少的欄位到現有表
ALTER TABLE playwright_post_metrics 
ADD COLUMN IF NOT EXISTS source VARCHAR(100) DEFAULT 'playwright_agent';

ALTER TABLE playwright_post_metrics 
ADD COLUMN IF NOT EXISTS crawler_type VARCHAR(50) DEFAULT 'playwright';

-- 2. 創建相關索引
CREATE INDEX IF NOT EXISTS idx_playwright_source ON playwright_post_metrics(source);
CREATE INDEX IF NOT EXISTS idx_playwright_crawler_type ON playwright_post_metrics(crawler_type);

-- 3. 驗證修復結果
SELECT 'Current deployment fix completed!' as status;

-- 4. 顯示表結構確認
\d playwright_post_metrics;

-- 5. 檢查所有必要欄位是否存在
SELECT 'Missing columns check:' as status;
SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'playwright_post_metrics' 
  AND column_name IN ('source', 'crawler_type', 'username', 'post_id', 'crawl_id')
ORDER BY column_name;