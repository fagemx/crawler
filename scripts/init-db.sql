-- Social Media Content Generator 資料庫初始化腳本
-- 基於 Plan E 架構的完整資料庫設置

-- ============================================================================
-- Tier-1: 長期資料存儲 (PostgreSQL)
-- ============================================================================

-- 貼文基本資料表
CREATE TABLE IF NOT EXISTS posts (
    url               TEXT PRIMARY KEY,
    author            TEXT,
    markdown          TEXT,          -- Jina Reader 提取的 markdown 內容
    media_urls        JSONB,         -- 媒體 URL 列表 ["https://...jpg", ...]
    created_at        TIMESTAMPTZ DEFAULT now(),  -- 爬蟲處理時間
    post_published_at TIMESTAMPTZ,  -- 真實貼文發布時間 (從DOM提取)
    tags              JSONB DEFAULT '[]',  -- 主題標籤列表 (從標籤連結提取)
    last_seen         TIMESTAMPTZ DEFAULT now()
);

-- 貼文指標表（與 posts 分離，支援獨立更新）
CREATE TABLE IF NOT EXISTS post_metrics (
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

-- 兼容舊環境：若已存在舊版 post_metrics（無 score 欄位），補齊欄位與觸發器
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name='post_metrics' AND column_name='score'
  ) THEN
    ALTER TABLE post_metrics ADD COLUMN score DOUBLE PRECISION;
    UPDATE post_metrics 
      SET score = COALESCE(views,0)*1.0 
                + COALESCE(likes,0)*0.3 
                + COALESCE(comments,0)*0.3 
                + COALESCE(reposts,0)*0.1 
                + COALESCE(shares,0)*0.1;
    CREATE OR REPLACE FUNCTION refresh_post_metrics_score() RETURNS trigger AS $f$
    BEGIN
      NEW.score = COALESCE(NEW.views,0)*1.0 
                + COALESCE(NEW.likes,0)*0.3 
                + COALESCE(NEW.comments,0)*0.3 
                + COALESCE(NEW.reposts,0)*0.1 
                + COALESCE(NEW.shares,0)*0.1;
      RETURN NEW;
    END
    $f$ LANGUAGE plpgsql;
    DROP TRIGGER IF EXISTS trg_refresh_post_metrics_score ON post_metrics;
    CREATE TRIGGER trg_refresh_post_metrics_score
      BEFORE INSERT OR UPDATE ON post_metrics
      FOR EACH ROW EXECUTE FUNCTION refresh_post_metrics_score();
  END IF;
END $$;

-- 媒體檔案管理表（支援 RustFS 存儲）
CREATE TABLE IF NOT EXISTS media_files (
    id              SERIAL PRIMARY KEY,
    post_url        TEXT NOT NULL REFERENCES posts(url) ON DELETE CASCADE,
    original_url    TEXT NOT NULL,
    media_type      TEXT NOT NULL CHECK (media_type IN ('image', 'video', 'audio', 'document')),
    file_extension  TEXT,
    rustfs_key      TEXT UNIQUE,        -- RustFS 存儲鍵值
    rustfs_url      TEXT,               -- RustFS 訪問 URL
    file_size       BIGINT,
    width           INTEGER,
    height          INTEGER,
    duration        INTEGER,            -- 影片/音頻長度（秒）
    download_status TEXT DEFAULT 'pending' CHECK (download_status IN ('pending', 'downloading', 'completed', 'failed')),
    download_error  TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    downloaded_at   TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'
);

-- 媒體描述結果（Gemini 產出）
CREATE TABLE IF NOT EXISTS media_descriptions (
    id               SERIAL PRIMARY KEY,
    media_id         INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    post_url         TEXT,
    username         TEXT,
    media_type       TEXT NOT NULL CHECK (media_type IN ('image','video')),
    model            TEXT DEFAULT 'gemini-2.5-pro',
    prompt           TEXT,
    response_json    JSONB DEFAULT '{}',
    language         TEXT DEFAULT 'zh-TW',
    status           TEXT DEFAULT 'completed' CHECK (status IN ('completed','failed')),
    error            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_media_desc_media_id ON media_descriptions(media_id);
CREATE INDEX IF NOT EXISTS idx_media_desc_username ON media_descriptions(username);
CREATE INDEX IF NOT EXISTS idx_media_desc_created_at ON media_descriptions(created_at DESC);

-- Agent 處理記錄（追蹤處理狀態）
CREATE TABLE IF NOT EXISTS processing_log (
    id           SERIAL PRIMARY KEY,
    url          TEXT NOT NULL,
    agent_name   TEXT NOT NULL,
    stage        TEXT NOT NULL,  -- 'markdown', 'vision_fill', 'analysis', 'media_download'
    status       TEXT NOT NULL,  -- 'pending', 'completed', 'failed'
    started_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_msg    TEXT,
    metadata     JSONB
);
-- =========================================================================
-- MCP Server 管理表格
-- =========================================================================

-- Agent 註冊表
CREATE TABLE IF NOT EXISTS mcp_agents (
    id              SERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    description     TEXT,
    version         TEXT DEFAULT '1.0.0',
    url             TEXT NOT NULL,
    health_check_url TEXT,
    capabilities    JSONB DEFAULT '{}',
    skills          JSONB DEFAULT '[]',
    requirements    JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'unknown' CHECK (status IN ('active', 'inactive', 'error', 'unknown')),
    registered_at   TIMESTAMPTZ DEFAULT now(),
    last_seen       TIMESTAMPTZ DEFAULT now(),
    last_health_check TIMESTAMPTZ,
    health_check_count INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0
);

-- Agent 健康檢查歷史
CREATE TABLE IF NOT EXISTS agent_health_history (
    id              SERIAL PRIMARY KEY,
    agent_name      TEXT NOT NULL REFERENCES mcp_agents(name) ON DELETE CASCADE,
    status          TEXT NOT NULL CHECK (status IN ('healthy', 'unhealthy', 'timeout', 'error')),
    response_time_ms INTEGER,
    error_message   TEXT,
    checked_at      TIMESTAMPTZ DEFAULT now(),
    metadata        JSONB DEFAULT '{}'
);

-- 系統操作日誌
CREATE TABLE IF NOT EXISTS system_operation_log (
    id              SERIAL PRIMARY KEY,
    operation_type  TEXT NOT NULL,  -- 'agent_register', 'agent_unregister', 'health_check', 'task_execute', 'media_download'
    operation_name  TEXT NOT NULL,
    agent_name      TEXT,
    user_id         TEXT,
    status          TEXT NOT NULL CHECK (status IN ('success', 'failed', 'pending')),
    request_data    JSONB,
    response_data   JSONB,
    error_message   TEXT,
    execution_time_ms INTEGER,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    ip_address      INET,
    user_agent      TEXT
);

-- 系統錯誤記錄
CREATE TABLE IF NOT EXISTS system_error_log (
    id              SERIAL PRIMARY KEY,
    error_type      TEXT NOT NULL,  -- 'agent_error', 'database_error', 'network_error', 'validation_error', 'media_error'
    error_code      TEXT,
    error_message   TEXT NOT NULL,
    stack_trace     TEXT,
    agent_name      TEXT,
    operation_context TEXT,
    request_data    JSONB,
    severity        TEXT DEFAULT 'error' CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    occurred_at     TIMESTAMPTZ DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    resolution_notes TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- 應用使用者清單（簡易登入用）
CREATE TABLE IF NOT EXISTS app_users (
    user_id        TEXT PRIMARY KEY,
    display_name   TEXT,
    created_at     TIMESTAMPTZ DEFAULT now(),
    last_login_at  TIMESTAMPTZ
);

-- 使用者表欄位補齊（標準登入）
-- 拆分為多條 ALTER，避免部分環境對多列 ADD 的解析問題
ALTER TABLE IF EXISTS app_users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE IF EXISTS app_users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE IF EXISTS app_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_app_users_role ON app_users(role);

-- 使用者操作日誌（區隔於系統/Agent 操作）
CREATE TABLE IF NOT EXISTS user_operation_log (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 身分/會話（登入前也能追）
    user_id          TEXT,
    anonymous_id     TEXT,
    session_id       TEXT,
    actor_type       TEXT NOT NULL DEFAULT 'user' CHECK (actor_type IN ('user')),

    -- 主功能與動作
    menu_name        TEXT NOT NULL,                           -- 例：🛠 監控面板
    page_name        TEXT,                                    -- 次層/元件（可空）
    action_type      TEXT NOT NULL,                           -- 例：navigate/click/submit/export
    action_name      TEXT NOT NULL,                           -- 例：切換到「🛠 監控面板」
    resource_id      TEXT,                                    -- 目標資源ID（如任務ID，可空）

    -- 結果與效能
    status           TEXT NOT NULL CHECK (status IN ('success','failed','pending')),
    latency_ms       INTEGER,
    error_message    TEXT,

    -- 請求環境與關聯
    ip_address       INET,
    user_agent       TEXT,
    request_id       TEXT,
    trace_id         TEXT,

    -- 其他
    metadata         JSONB DEFAULT '{}'
);

-- ============================================================================
-- 索引優化
-- ============================================================================

-- 基本表格索引
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_post_metrics_score ON post_metrics(score DESC);
CREATE INDEX IF NOT EXISTS idx_post_metrics_updated_at ON post_metrics(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_processing_log_url ON processing_log(url);
CREATE INDEX IF NOT EXISTS idx_processing_log_status ON processing_log(status);

-- 使用者操作日誌索引（90天熱儲存主查詢設計）
CREATE INDEX IF NOT EXISTS idx_user_ops_ts_desc ON user_operation_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_user_ops_user ON user_operation_log (user_id);
CREATE INDEX IF NOT EXISTS idx_user_ops_anon ON user_operation_log (anonymous_id);
CREATE INDEX IF NOT EXISTS idx_user_ops_menu ON user_operation_log (menu_name);
CREATE INDEX IF NOT EXISTS idx_user_ops_action ON user_operation_log (action_type);
CREATE INDEX IF NOT EXISTS idx_user_ops_trace ON user_operation_log (trace_id);

-- 媒體檔案索引
CREATE INDEX IF NOT EXISTS idx_media_files_post_url ON media_files(post_url);
CREATE INDEX IF NOT EXISTS idx_media_files_download_status ON media_files(download_status);
CREATE INDEX IF NOT EXISTS idx_media_files_media_type ON media_files(media_type);
CREATE INDEX IF NOT EXISTS idx_media_files_created_at ON media_files(created_at DESC);

-- MCP Server 索引
CREATE INDEX IF NOT EXISTS idx_mcp_agents_status ON mcp_agents(status);
CREATE INDEX IF NOT EXISTS idx_mcp_agents_last_seen ON mcp_agents(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_agent_health_history_agent ON agent_health_history(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_health_history_checked_at ON agent_health_history(checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_operation_log_type ON system_operation_log(operation_type);
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name='system_operation_log' AND column_name='started_at'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_system_operation_log_started_at ON system_operation_log(started_at DESC)';
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_system_error_log_type ON system_error_log(error_type);
CREATE INDEX IF NOT EXISTS idx_system_error_log_severity ON system_error_log(severity);
CREATE INDEX IF NOT EXISTS idx_system_error_log_occurred_at ON system_error_log(occurred_at DESC);
-- =========================================================================
-- 視圖和函數
-- =========================================================================

-- 完整貼文資料視圖（包含媒體檔案）
CREATE OR REPLACE VIEW posts_with_metrics AS
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
    pm.updated_at as metrics_updated_at,
    (
        SELECT COUNT(*) 
        FROM media_files mf 
        WHERE mf.post_url = p.url AND mf.download_status = 'completed'
    ) as downloaded_media_count,
    (
        SELECT COUNT(*) 
        FROM media_files mf 
        WHERE mf.post_url = p.url
    ) as total_media_count
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
-- =========================================================================
-- MCP Server 管理函數
-- =========================================================================

-- 註冊或更新 Agent
CREATE OR REPLACE FUNCTION upsert_agent(
    p_name TEXT,
    p_description TEXT DEFAULT NULL,
    p_version TEXT DEFAULT '1.0.0',
    p_url TEXT DEFAULT NULL,
    p_health_check_url TEXT DEFAULT NULL,
    p_capabilities JSONB DEFAULT '{}',
    p_skills JSONB DEFAULT '[]',
    p_requirements JSONB DEFAULT '{}',
    p_metadata JSONB DEFAULT '{}'
) RETURNS VOID AS $$
BEGIN
    INSERT INTO mcp_agents (
        name, description, version, url, health_check_url,
        capabilities, skills, requirements, metadata, status
    )
    VALUES (
        p_name, p_description, p_version, p_url, p_health_check_url,
        p_capabilities, p_skills, p_requirements, p_metadata, 'active'
    )
    ON CONFLICT (name) DO UPDATE SET
        description = COALESCE(EXCLUDED.description, mcp_agents.description),
        version = COALESCE(EXCLUDED.version, mcp_agents.version),
        url = COALESCE(EXCLUDED.url, mcp_agents.url),
        health_check_url = COALESCE(EXCLUDED.health_check_url, mcp_agents.health_check_url),
        capabilities = COALESCE(EXCLUDED.capabilities, mcp_agents.capabilities),
        skills = COALESCE(EXCLUDED.skills, mcp_agents.skills),
        requirements = COALESCE(EXCLUDED.requirements, mcp_agents.requirements),
        metadata = COALESCE(EXCLUDED.metadata, mcp_agents.metadata),
        status = 'active',
        last_seen = now();
END;
$$ LANGUAGE plpgsql;

-- 記錄健康檢查結果
CREATE OR REPLACE FUNCTION record_health_check(
    p_agent_name TEXT,
    p_status TEXT,
    p_response_time_ms INTEGER DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'
) RETURNS VOID AS $$
BEGIN
    -- 插入健康檢查歷史
    INSERT INTO agent_health_history (
        agent_name, status, response_time_ms, error_message, metadata
    )
    VALUES (
        p_agent_name, p_status, p_response_time_ms, p_error_message, p_metadata
    );
    
    -- 更新 Agent 狀態
    UPDATE mcp_agents 
    SET 
        status = CASE 
            WHEN p_status = 'healthy' THEN 'active'
            WHEN p_status = 'unhealthy' THEN 'inactive'
            ELSE 'error'
        END,
        last_health_check = now(),
        health_check_count = health_check_count + 1,
        error_count = CASE 
            WHEN p_status != 'healthy' THEN error_count + 1
            ELSE error_count
        END,
        last_seen = now()
    WHERE name = p_agent_name;
END;
$$ LANGUAGE plpgsql;

-- 記錄系統操作
CREATE OR REPLACE FUNCTION log_system_operation(
    p_operation_type TEXT,
    p_operation_name TEXT,
    p_agent_name TEXT DEFAULT NULL,
    p_user_id TEXT DEFAULT NULL,
    p_status TEXT DEFAULT 'pending',
    p_request_data JSONB DEFAULT NULL,
    p_response_data JSONB DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL,
    p_execution_time_ms INTEGER DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    log_id INTEGER;
BEGIN
    INSERT INTO system_operation_log (
        operation_type, operation_name, agent_name, user_id, status,
        request_data, response_data, error_message, execution_time_ms,
        ip_address, user_agent, completed_at
    )
    VALUES (
        p_operation_type, p_operation_name, p_agent_name, p_user_id, p_status,
        p_request_data, p_response_data, p_error_message, p_execution_time_ms,
        p_ip_address, p_user_agent,
        CASE WHEN p_status != 'pending' THEN now() ELSE NULL END
    )
    RETURNING id INTO log_id;
    
    RETURN log_id;
END;
$$ LANGUAGE plpgsql;

-- 記錄系統錯誤
CREATE OR REPLACE FUNCTION log_system_error(
    p_error_type TEXT,
    p_error_code TEXT DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL,
    p_stack_trace TEXT DEFAULT NULL,
    p_agent_name TEXT DEFAULT NULL,
    p_operation_context TEXT DEFAULT NULL,
    p_request_data JSONB DEFAULT NULL,
    p_severity TEXT DEFAULT 'error',
    p_metadata JSONB DEFAULT '{}'
) RETURNS INTEGER AS $$
DECLARE
    error_id INTEGER;
BEGIN
    INSERT INTO system_error_log (
        error_type, error_code, error_message, stack_trace, agent_name,
        operation_context, request_data, severity, metadata
    )
    VALUES (
        p_error_type, p_error_code, p_error_message, p_stack_trace, p_agent_name,
        p_operation_context, p_request_data, p_severity, p_metadata
    )
    RETURNING id INTO error_id;
    
    RETURN error_id;
END;
$$ LANGUAGE plpgsql;

-- 媒體檔案管理函數
CREATE OR REPLACE FUNCTION upsert_media_file(
    p_post_url TEXT,
    p_original_url TEXT,
    p_media_type TEXT,
    p_file_extension TEXT DEFAULT NULL,
    p_rustfs_key TEXT DEFAULT NULL,
    p_rustfs_url TEXT DEFAULT NULL,
    p_file_size BIGINT DEFAULT NULL,
    p_width INTEGER DEFAULT NULL,
    p_height INTEGER DEFAULT NULL,
    p_duration INTEGER DEFAULT NULL,
    p_download_status TEXT DEFAULT 'pending',
    p_metadata JSONB DEFAULT '{}'
) RETURNS INTEGER AS $$
DECLARE
    media_id INTEGER;
BEGIN
    INSERT INTO media_files (
        post_url, original_url, media_type, file_extension, rustfs_key, rustfs_url,
        file_size, width, height, duration, download_status, metadata,
        downloaded_at
    )
    VALUES (
        p_post_url, p_original_url, p_media_type, p_file_extension, p_rustfs_key, p_rustfs_url,
        p_file_size, p_width, p_height, p_duration, p_download_status, p_metadata,
        CASE WHEN p_download_status = 'completed' THEN now() ELSE NULL END
    )
    ON CONFLICT (rustfs_key) DO UPDATE SET
        download_status = EXCLUDED.download_status,
        rustfs_url = COALESCE(EXCLUDED.rustfs_url, media_files.rustfs_url),
        file_size = COALESCE(EXCLUDED.file_size, media_files.file_size),
        width = COALESCE(EXCLUDED.width, media_files.width),
        height = COALESCE(EXCLUDED.height, media_files.height),
        duration = COALESCE(EXCLUDED.duration, media_files.duration),
        metadata = COALESCE(EXCLUDED.metadata, media_files.metadata),
        downloaded_at = CASE 
            WHEN EXCLUDED.download_status = 'completed' AND media_files.downloaded_at IS NULL 
            THEN now() 
            ELSE media_files.downloaded_at 
        END
    RETURNING id INTO media_id;
    
    RETURN media_id;
END;
$$ LANGUAGE plpgsql;
-- ============================================================================
-- 初始數據插入
-- ============================================================================

-- 插入預設的 Agent 配置（如果不存在）
INSERT INTO mcp_agents (name, description, url, health_check_url, capabilities, skills) 
VALUES 
    ('orchestrator', 'Orchestrator Agent - 總協調器', 'http://orchestrator-agent:8000', 'http://orchestrator-agent:8000/health', 
     '{"coordination": true, "task_management": true}', 
     '[{"name": "task_coordination", "description": "協調各個 Agent 的任務執行"}]'),
    ('crawler', 'Crawler Agent - 爬蟲代理', 'http://crawler-agent:8001', 'http://crawler-agent:8001/health',
     '{"web_scraping": true, "data_extraction": true}',
     '[{"name": "web_crawling", "description": "網頁爬取和數據提取"}]'),
    ('analysis', 'Analysis Agent - 分析代理', 'http://analysis-agent:8002', 'http://analysis-agent:8002/health',
     '{"content_analysis": true, "ranking": true}',
     '[{"name": "content_analysis", "description": "內容分析和排序"}]'),
    ('content-writer', 'Content Writer Agent - 內容生成代理', 'http://content-writer-agent:8003', 'http://content-writer-agent:8003/health',
     '{"content_generation": true, "writing": true}',
     '[{"name": "content_writing", "description": "內容生成和寫作"}]'),
    ('vision', 'Vision Agent - 視覺分析代理', 'http://vision-agent:8005', 'http://vision-agent:8005/health',
     '{"image_analysis": true, "video_analysis": true}',
     '[{"name": "visual_analysis", "description": "圖片和影片分析"}]'),
    ('playwright-crawler', 'Playwright Crawler Agent - 瀏覽器爬蟲代理', 'http://playwright-crawler-agent:8006', 'http://playwright-crawler-agent:8006/health',
     '{"browser_automation": true, "dynamic_content": true}',
     '[{"name": "browser_crawling", "description": "瀏覽器自動化爬取"}]')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- 增量爬取支持表 (新增)
-- ============================================================================

-- 爬取狀態跟踪表
CREATE TABLE IF NOT EXISTS crawl_state (
    username        TEXT PRIMARY KEY,
    latest_post_id  TEXT,                    -- 最新post_id，避免全表掃描
    total_crawled   INTEGER DEFAULT 0,       -- 總爬取數量
    last_crawl_at   TIMESTAMPTZ DEFAULT NOW(), -- 最後爬取時間
    created_at      TIMESTAMPTZ DEFAULT NOW()  -- 創建時間
);

-- 增量爬取專用貼文表 (與原有 posts/post_metrics 並行)
CREATE TABLE IF NOT EXISTS post_metrics_sql (
    id              SERIAL PRIMARY KEY,
    post_id         TEXT UNIQUE NOT NULL,     -- 關鍵：唯一約束 (natgeo_DM2oBhXqFcx)
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
    created_at      TIMESTAMPTZ NOT NULL,     -- 爬蟲處理時間
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    views_fetched_at TIMESTAMPTZ,
    source          TEXT DEFAULT 'unknown',   -- 數據來源
    processing_stage TEXT DEFAULT 'initial',  -- 處理階段  
    is_complete     BOOLEAN DEFAULT FALSE,    -- 數據是否完整
    post_published_at TIMESTAMPTZ,            -- 真實貼文發布時間 (從DOM提取)
    tags            JSONB DEFAULT '[]',       -- 主題標籤列表 (從標籤連結提取)
    
    -- 新增：雙軌處理狀態追蹤
    reader_status   TEXT DEFAULT 'pending',   -- Reader處理狀態: pending/success/failed
    dom_status      TEXT DEFAULT 'pending',   -- DOM爬取狀態: pending/success/failed
    reader_processed_at TIMESTAMPTZ,          -- Reader處理完成時間
    dom_processed_at TIMESTAMPTZ              -- DOM處理完成時間
);

-- Playwright 爬蟲專用貼文表
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

-- 性能優化索引
CREATE INDEX IF NOT EXISTS idx_crawl_state_latest_post_id ON crawl_state(latest_post_id);
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_username ON post_metrics_sql(username);
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_created_at ON post_metrics_sql(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_post_metrics_sql_score ON post_metrics_sql(calculated_score DESC);

-- Playwright 表索引
CREATE INDEX IF NOT EXISTS idx_playwright_username_created ON playwright_post_metrics(username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playwright_crawl_id ON playwright_post_metrics(crawl_id);
CREATE INDEX IF NOT EXISTS idx_playwright_source ON playwright_post_metrics(source);
CREATE INDEX IF NOT EXISTS idx_playwright_crawler_type ON playwright_post_metrics(crawler_type);

-- 完成初始化
SELECT 'Database initialization completed successfully!' as status;

-- ============================================================================
-- Schema repair (idempotent) - 保證既有環境補齊缺漏欄位/索引
-- 注意：以下均為 IF NOT EXISTS，重複執行安全
-- ============================================================================

-- playwright_post_metrics 欄位補齊
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS views_count INTEGER;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS likes_count INTEGER;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS comments_count INTEGER;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS reposts_count INTEGER;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS shares_count INTEGER;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS calculated_score DECIMAL;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS post_published_at TIMESTAMP;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS tags TEXT;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS images TEXT;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS videos TEXT;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS source VARCHAR(100) DEFAULT 'playwright_agent';
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS crawler_type VARCHAR(50) DEFAULT 'playwright';
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS crawl_id VARCHAR(255);
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
ALTER TABLE IF EXISTS playwright_post_metrics ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- media_files 欄位補齊
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS file_extension TEXT;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS rustfs_key TEXT;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS rustfs_url TEXT;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS width INTEGER;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS height INTEGER;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS duration INTEGER;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS download_status TEXT DEFAULT 'pending';
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS download_error TEXT;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS media_files ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- media_files created_at 預設補齊（避免 NOT NULL 無預設導致插入失敗）
DO $$ BEGIN
  PERFORM 1
  FROM information_schema.columns
  WHERE table_name='media_files' AND column_name='created_at';
  IF FOUND THEN
    EXECUTE 'ALTER TABLE media_files ALTER COLUMN created_at SET DEFAULT now()';
    EXECUTE 'UPDATE media_files SET created_at = NOW() WHERE created_at IS NULL';
  END IF;
END $$;

-- media_files 索引補齊
CREATE INDEX IF NOT EXISTS idx_media_files_original_url ON media_files(original_url);
CREATE INDEX IF NOT EXISTS idx_media_files_rustfs_key ON media_files(rustfs_key);

-- post_metrics_sql 欄位補齊（增量表）
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS likes_count INTEGER DEFAULT 0;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS comments_count INTEGER DEFAULT 0;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS reposts_count INTEGER DEFAULT 0;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS shares_count INTEGER DEFAULT 0;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS views_count BIGINT DEFAULT 0;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS calculated_score DOUBLE PRECISION;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS images JSONB DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS videos JSONB DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS views_fetched_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'unknown';
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS processing_stage TEXT DEFAULT 'initial';
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS is_complete BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS post_published_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS reader_status TEXT DEFAULT 'pending';
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS dom_status TEXT DEFAULT 'pending';
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS reader_processed_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS post_metrics_sql ADD COLUMN IF NOT EXISTS dom_processed_at TIMESTAMPTZ;

-- playwright_post_metrics 唯一鍵與索引補齊（無 IF NOT EXISTS 支援 → 以 pg_constraint 檢查）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conrelid = 'playwright_post_metrics'::regclass
      AND conname = 'uniq_playwright_user_post_type'
  ) THEN
    ALTER TABLE playwright_post_metrics
      ADD CONSTRAINT uniq_playwright_user_post_type UNIQUE (username, post_id, crawler_type);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_playwright_username_created ON playwright_post_metrics(username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playwright_crawl_id ON playwright_post_metrics(crawl_id);
