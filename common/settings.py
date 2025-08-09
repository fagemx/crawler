"""
統一配置管理模組

支援環境變數、.env 檔案和預設值的配置管理
"""

import os
from typing import Optional, List, Any
from pydantic import Field, validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel


class ApifySettings(BaseModel):
    """Apify 配置 - 簡化版本"""
    token: Optional[str] = None
    threads_actor_id: str = Field(default="curious_coder/threads-scraper")
    default_max_posts: int = Field(default=50, description="預設單次爬取最大貼文數")
    timeout_seconds: int = Field(default=300)


class DatabaseSettings(BaseModel):
    """資料庫配置"""
    pool_size: int = 10
    url: str = "postgresql://postgres:password@localhost:5432/social_media_db"
    max_overflow: int = Field(default=20)
    echo: bool = Field(default=False)
    
    # 添加獨立的資料庫連接參數（從URL解析或環境變數）
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    user: str = Field(default="postgres")
    password: str = Field(default="password")
    name: str = Field(default="social_media_db")
    
    class Config:
        env_prefix = "DATABASE_"


class RedisSettings(BaseModel):
    """Redis 配置"""
    url: str = "redis://localhost:6379/0"
    session_db: int = Field(default=1)
    cache_db: int = Field(default=2)
    max_connections: int = Field(default=10)
    
    class Config:
        env_prefix = "REDIS_"


class NATSSettings(BaseSettings):
    """NATS 配置"""
    url: str = Field(default="nats://localhost:4222")
    stream_name: str = Field(default="social_media_tasks")
    consumer_name: str = Field(default="content_generator")
    
    model_config = SettingsConfigDict(
        env_prefix="NATS_",
        extra='ignore'
    )


class GeminiSettings(BaseSettings):
    """Gemini AI 配置"""
    api_key: str = Field(default="")
    model_text: str = Field(default="gemini-2.5-pro")
    model_vision_fast: str = Field(default="gemini-2.5-flash")
    model_vision_pro: str = Field(default="gemini-2.5-pro")
    max_tokens_per_day: int = Field(default=1000000)
    max_tokens_per_session: int = Field(default=50000)
    token_warning_threshold: float = Field(default=0.8)
    
    class Config:
        env_prefix = "GEMINI_"


class JinaSettings(BaseSettings):
    """Jina AI 配置"""
    api_key: str = Field(default="", description="設定為空字串以使用免費版。會被 JINA_API_KEY 環境變數覆蓋。")
    base_url: str = Field(default="https://r.jina.ai/{url}")
    max_posts_per_batch: int = Field(default=100, description="每批次最大處理貼文數量")
    concurrent_requests: int = Field(default=5, description="同時並發請求數量，0=自動, 10=壓力測試, 5=快速模式穩定值")
    
    # 根據 Jina API 文檔的速率限制
    free_tier_rpm: int = Field(default=20, description="免費版每分鐘請求限制")
    paid_tier_rpm: int = Field(default=5000, description="付費版每分鐘請求限制")
    
    model_config = SettingsConfigDict(
        env_prefix="JINA_", # <-- 恢復，使其能從 .env 讀取 JINA_API_KEY
        extra='ignore'
    )
    
    def get_optimal_concurrency(self) -> int:
        """根據是否有 API Key 自動計算最佳並發數 (防呆加強版)"""
        # 1. 優先使用手動設定，但要過濾掉 0
        if self.concurrent_requests > 0:
            return self.concurrent_requests
        
        # 2. 根據 API Key 計算，並設置安全邊界
        concurrency = 1 # 預設值，確保永不為 0
        if self.api_key:
            # 付費版：RPM / 60s = RPS。用 min 限制上限，用 max 確保下限
            # 即使 paid_tier_rpm 被設為 0，max(1, ...) 也能確保結果至少為 1
            concurrency = max(1, min(20, self.paid_tier_rpm // 60))
        else:
            # 免費版：固定為 1 就好，因為 20 RPM 太低，不適合並發
            concurrency = 1
            
        # 3. 最後再檢查一次，確保不會是 0
        return max(1, concurrency)


class MCPSettings(BaseModel):
    """MCP Server 配置"""
    server_host: str = "0.0.0.0"
    server_port: int = 10100
    server_url: str = Field(default="http://localhost:10100")
    
    class Config:
        env_prefix = "MCP_"


class ServiceURLSettings(BaseSettings):
    """服務間通信 URL 配置"""
    orchestrator_url: str = Field(default="http://localhost:8000")
    clarification_url: str = Field(default="http://localhost:8004") 
    content_writer_url: str = Field(default="http://localhost:8003")
    form_api_url: str = Field(default="http://localhost:8010")
    
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False
    )


class AgentSettings(BaseModel):
    """Agent 服務配置"""
    orchestrator_port: int = Field(default=8000)
    crawler_agent_port: int = Field(default=8001)
    analysis_agent_port: int = Field(default=8002)
    content_writer_port: int = Field(default=8003)
    jina_agent_port: int = Field(default=8004)
    vision_agent_port: int = Field(default=8005)
    playwright_crawler_agent_port: int = Field(default=8006)
    
    class Config:
        env_prefix = "AGENT_"


class PlaywrightSettings(BaseSettings):
    """Playwright 爬蟲配置"""
    headless: bool = Field(default=True, description="是否以無頭模式運行 Playwright")
    concurrency: int = Field(default=3, description="每台機器同時運行的瀏覽器實例數")
    navigation_timeout: int = Field(default=60000, description="頁面導航超時時間（毫秒）")
    scroll_delay_min: float = Field(default=2.0, description="每次滾動後的最小延遲（秒）")
    scroll_delay_max: float = Field(default=3.5, description="每次滾動後的最大延遲（秒）")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        description="Playwright 使用的 User-Agent"
    )
    enable_details_filling: bool = Field(default=True, description="是否啟用詳細數據補齊（likes, content, images等）")
    
    # 允許忽略未知鍵，避免如 PLAYWRIGHT_BROWSERS_PATH 這類環境變數
    # 透過 env_nested_delimiter 解析為 playwright.browsers.path 時觸發 extra_forbidden
    model_config = SettingsConfigDict(
        env_prefix="PLAYWRIGHT_",
        extra='ignore'
    )


class SecuritySettings(BaseSettings):
    """安全配置"""
    secret_key: str = Field(default="your-super-secret-key-change-this-in-production")
    jwt_secret_key: str = Field(default="your-jwt-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_hours: int = Field(default=24)
    bcrypt_rounds: int = Field(default=12)
    
    class Config:
        env_prefix = "SECURITY_"


class MonitoringSettings(BaseSettings):
    """監控配置"""
    jaeger_endpoint: str = Field(default="http://localhost:14268/api/traces")
    service_name: str = Field(default="social-media-content-generator")
    prometheus_port: int = Field(default=9090)
    metrics_enabled: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")
    
    class Config:
        env_prefix = "MONITORING_"


class PerformanceSettings(BaseSettings):
    """性能配置"""
    max_concurrent_crawls: int = Field(default=3)
    max_concurrent_analysis: int = Field(default=2)
    max_concurrent_generations: int = Field(default=1)
    http_timeout_seconds: int = Field(default=30)
    crawler_timeout_seconds: int = Field(default=300)
    analysis_timeout_seconds: int = Field(default=120)
    generation_timeout_seconds: int = Field(default=180)
    max_retry_attempts: int = Field(default=3)
    retry_backoff_factor: float = Field(default=2.0)
    
    class Config:
        env_prefix = "PERFORMANCE_"


class FeatureFlags(BaseSettings):
    """功能開關"""
    enable_media_analysis: bool = Field(default=True)
    enable_video_stt: bool = Field(default=True)
    enable_auto_hashtags: bool = Field(default=True)
    enable_multi_language: bool = Field(default=False)
    enable_redis_cache: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=3600)
    
    class Config:
        env_prefix = "FEATURE_"


class LLMSettings(BaseModel):
    """Settings for a single LLM provider."""
    api_key: str = ""
    base_url: str = ""
    # Store models as a simple comma-separated string to avoid parsing issues from .env
    models: str = ""

class LLMProviderSettings(BaseModel):
    """Container for different LLM providers."""
    t8star_cn: LLMSettings = Field(default_factory=LLMSettings)
    openrouter: LLMSettings = Field(default_factory=LLMSettings)
    # Add other providers here in the future, e.g., openai: LLMSettings = Field(default_factory=LLMSettings)

class Settings(BaseSettings):
    """Main settings for the application."""
    app_name: str = "Social Media Content Generator"
    development_mode: bool = False
    
    # 此處不再需要 jina_api_key，它已經被移到 JinaSettings 內
    
    apify: ApifySettings = Field(default_factory=ApifySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    nats: NATSSettings = Field(default_factory=NATSSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    playwright: PlaywrightSettings = Field(default_factory=PlaywrightSettings)
    jina: JinaSettings = Field(default_factory=JinaSettings)
    llm_providers: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    service_urls: ServiceURLSettings = Field(default_factory=ServiceURLSettings)

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_nested_delimiter='_',
        case_sensitive=False,
        extra='ignore'
    )

    def is_development(self) -> bool:
        """Checks if the application is in development mode."""
        return self.development_mode
    
    @property
    def DATABASE_HOST(self) -> str:
        """快捷訪問資料庫主機"""
        return self.database.host
    
    @property
    def DATABASE_PORT(self) -> int:
        """快捷訪問資料庫端口"""
        return self.database.port
    
    @property
    def DATABASE_USER(self) -> str:
        """快捷訪問資料庫用戶"""
        return self.database.user
    
    @property
    def DATABASE_PASSWORD(self) -> str:
        """快捷訪問資料庫密碼"""
        return self.database.password
    
    @property
    def DATABASE_NAME(self) -> str:
        """快捷訪問資料庫名稱"""
        return self.database.name

# Global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Returns the global settings instance."""
    return settings


def get_database_url() -> str:
    """獲取資料庫連接 URL"""
    return get_settings().database.url


def get_redis_url() -> str:
    """獲取 Redis 連接 URL"""
    return get_settings().redis.url


def get_mcp_server_url() -> str:
    """獲取 MCP Server URL"""
    return get_settings().mcp.server_url


def get_agent_port(agent_name: str) -> int:
    """獲取指定 Agent 的端口"""
    port_mapping = {
        "orchestrator": get_settings().agents.orchestrator_port,
        "crawler": get_settings().agents.crawler_agent_port,
        "analysis": get_settings().agents.analysis_agent_port,
        "content_writer": get_settings().agents.content_writer_port,
    }
    return port_mapping.get(agent_name, 8000)


def is_feature_enabled(feature_name: str) -> bool:
    """檢查功能是否啟用"""
    feature_mapping = {
        "media_analysis": get_settings().features.enable_media_analysis,
        "video_stt": get_settings().features.enable_video_stt,
        "auto_hashtags": get_settings().features.enable_auto_hashtags,
        "multi_language": get_settings().features.enable_multi_language,
        "redis_cache": get_settings().features.enable_redis_cache,
    }
    return feature_mapping.get(feature_name, False)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._settings = get_settings()
    
    def get(self, key: str, default: Any = None) -> Any:
        """獲取配置值"""
        keys = key.split('.')
        value = self._settings
        
        try:
            for k in keys:
                value = getattr(value, k)
            return value
        except AttributeError:
            return default
    
    def set(self, key: str, value: Any) -> None:
        """設置配置值（僅限開發環境）"""
        if not self._settings.is_development():
            raise RuntimeError("Configuration can only be modified in development mode")
        
        keys = key.split('.')
        obj = self._settings
        
        for k in keys[:-1]:
            obj = getattr(obj, k)
        
        setattr(obj, keys[-1], value)
    
    def reload(self) -> None:
        """重新載入配置"""
        global settings
        settings = Settings()
        self._settings = settings


# 全域配置管理器實例
config_manager = ConfigManager()


# 便利函數
def get_config(key: str, default: Any = None) -> Any:
    """獲取配置值的便利函數"""
    return config_manager.get(key, default)


def validate_required_configs() -> List[str]:
    """驗證必要配置是否存在"""
    missing_configs = []
    
    # 檢查必要的 API 金鑰
    if not get_settings().apify.token:
        missing_configs.append("APIFY_TOKEN")
    
    if not get_settings().gemini.api_key:
        missing_configs.append("GEMINI_API_KEY")
    
    # 檢查資料庫連接
    if not get_settings().database.url:
        missing_configs.append("DATABASE_URL")
    
    return missing_configs


def print_config_summary() -> None:
    """打印配置摘要"""
    print("=== 配置摘要 ===")
    print(f"環境: {get_settings().environment}")
    print(f"除錯模式: {get_settings().debug}")
    print(f"資料庫: {get_settings().database.url}")
    print(f"Redis: {get_settings().redis.url}")
    print(f"MCP Server: {get_settings().mcp.server_url}")
    print(f"Apify Token: {'已設置' if get_settings().apify.token else '未設置'}")
    print(f"Gemini API Key: {'已設置' if get_settings().gemini.api_key else '未設置'}")
    print("================")


if __name__ == "__main__":
    # 驗證配置
    missing = validate_required_configs()
    if missing:
        print(f"缺少必要配置: {', '.join(missing)}")
    else:
        print("所有必要配置已設置")
    
    # 打印配置摘要
    print_config_summary()

    # For debugging purposes
    settings = get_settings()
    import json
    # Pydantic models have a model_dump_json method
    print(settings.model_dump_json(indent=2))