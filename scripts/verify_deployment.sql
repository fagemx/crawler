-- 部署驗證腳本：確保所有表都正確創建
-- 執行方式：docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/verify_deployment.sql

-- 檢查所有必要的表是否存在
SELECT 'Checking required tables...' as status;

SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'posts') 
        THEN '✅ posts table exists'
        ELSE '❌ posts table missing'
    END as posts_status;

SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'post_metrics') 
        THEN '✅ post_metrics table exists'
        ELSE '❌ post_metrics table missing'
    END as post_metrics_status;

SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'post_metrics_sql') 
        THEN '✅ post_metrics_sql table exists'
        ELSE '❌ post_metrics_sql table missing'
    END as post_metrics_sql_status;

SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'playwright_post_metrics') 
        THEN '✅ playwright_post_metrics table exists'
        ELSE '❌ playwright_post_metrics table missing'
    END as playwright_table_status;

SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'crawl_state') 
        THEN '✅ crawl_state table exists'
        ELSE '❌ crawl_state table missing'
    END as crawl_state_status;

-- 檢查 playwright_post_metrics 的關鍵欄位
SELECT 'Checking playwright_post_metrics columns...' as status;

SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'playwright_post_metrics' 
  AND column_name IN ('source', 'crawler_type', 'username', 'post_id', 'crawl_id')
ORDER BY column_name;

-- 檢查 UNIQUE 約束
SELECT 'Checking UNIQUE constraints...' as status;

SELECT 
    conname as constraint_name,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint 
WHERE conrelid = 'playwright_post_metrics'::regclass 
  AND contype = 'u';

-- 檢查索引
SELECT 'Checking indexes...' as status;

SELECT 
    indexname,
    tablename,
    indexdef
FROM pg_indexes 
WHERE tablename = 'playwright_post_metrics'
ORDER BY indexname;

-- 最終狀態
SELECT 'Deployment verification completed!' as final_status;
SELECT NOW() as verification_time;