"""
統一 LLM 管理器
支持多供應商、智能路由、成本追蹤和性能監控
"""

import os
import time
import json
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import httpx
import os
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from .settings import get_settings
from .llm_usage_recorder import log_usage, get_service_name


class LLMProvider(Enum):
    """LLM 供應商枚舉"""
    GEMINI = "gemini"
    OPENAI = "openai"
    CLAUDE = "claude"
    OPENROUTER = "openrouter"
    T8STAR = "t8star_cn"


@dataclass
class LLMRequest:
    """LLM 請求數據結構"""
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    provider: Optional[LLMProvider] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class LLMResponse:
    """LLM 響應數據結構"""
    content: str
    provider: LLMProvider
    model: str
    usage: Dict[str, int]
    cost: float
    latency: float
    request_id: str
    timestamp: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class LLMUsageStats:
    """LLM 使用統計"""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_latency: float = 0.0
    success_rate: float = 0.0
    last_updated: float = 0.0


class BaseLLMProvider(ABC):
    """LLM 供應商基類"""
    
    def __init__(self, provider_type: LLMProvider, config: Dict[str, Any]):
        self.provider_type = provider_type
        self.config = config
        self.logger = logging.getLogger(f"llm.{provider_type.value}")
        self.stats = LLMUsageStats()
        
    @abstractmethod
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """執行聊天完成請求"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """檢查供應商是否可用"""
        pass
    
    @abstractmethod
    def get_cost_per_token(self, model: str) -> Dict[str, float]:
        """獲取每個 token 的成本"""
        pass
    
    def update_stats(self, response: LLMResponse, success: bool):
        """更新使用統計"""
        self.stats.total_requests += 1
        if success:
            self.stats.total_tokens += response.usage.get('total_tokens', 0)
            self.stats.total_cost += response.cost
            
            # 更新平均延遲
            if self.stats.total_requests == 1:
                self.stats.avg_latency = response.latency
            else:
                self.stats.avg_latency = (
                    (self.stats.avg_latency * (self.stats.total_requests - 1) + response.latency) 
                    / self.stats.total_requests
                )
        
        # 更新成功率
        success_count = self.stats.total_requests * self.stats.success_rate
        if success:
            success_count += 1
        self.stats.success_rate = success_count / self.stats.total_requests
        self.stats.last_updated = time.time()


class GeminiProvider(BaseLLMProvider):
    """Gemini 供應商實現"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(LLMProvider.GEMINI, config)
        
        self.api_key = config.get('api_key') or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found")
        
        # 配置 Gemini
        genai.configure(api_key=self.api_key)
        
        # 預設模型
        self.default_model = config.get('default_model', 'gemini-2.0-flash')
        
        # 安全設定
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # 成本配置 (每 1M tokens 的美元成本)
        self.cost_config = {
            'gemini-2.0-flash': {'input': 0.075, 'output': 0.30},
            'gemini-2.0-flash-exp': {'input': 0.075, 'output': 0.30},
            'gemini-1.5-pro': {'input': 3.50, 'output': 10.50},
            'gemini-1.5-flash': {'input': 0.075, 'output': 0.30},
        }
    
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """執行 Gemini 聊天完成請求"""
        start_time = time.time()
        request_id = f"gemini_{int(time.time() * 1000)}"
        
        try:
            model_name = request.model or self.default_model
            model = genai.GenerativeModel(model_name)
            
            # 轉換消息格式
            prompt_parts = []
            for msg in request.messages:
                if msg['role'] == 'system':
                    prompt_parts.append(f"System: {msg['content']}")
                elif msg['role'] == 'user':
                    prompt_parts.append(f"User: {msg['content']}")
                elif msg['role'] == 'assistant':
                    prompt_parts.append(f"Assistant: {msg['content']}")
            
            prompt = "\n\n".join(prompt_parts)
            
            # 生成配置
            generation_config = genai.types.GenerationConfig(
                temperature=request.temperature,
                max_output_tokens=request.max_tokens,
            )
            
            # 調用 Gemini API
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=self.safety_settings
            )
            
            # 檢查響應狀態
            if not response.candidates:
                raise Exception("Gemini API 沒有返回任何候選響應")
            
            candidate = response.candidates[0]
            
            # 檢查 finish_reason
            if candidate.finish_reason == 2:  # SAFETY
                raise Exception("Gemini API 因安全過濾而拒絕生成內容，請嘗試修改提示詞")
            elif candidate.finish_reason == 3:  # RECITATION
                raise Exception("Gemini API 檢測到重複內容，請嘗試修改提示詞")
            elif candidate.finish_reason != 1:  # STOP (正常完成)
                raise Exception(f"Gemini API 異常終止，finish_reason: {candidate.finish_reason}")
            
            # 計算使用量和成本
            usage = {
                'prompt_tokens': response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                'completion_tokens': response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                'total_tokens': response.usage_metadata.total_token_count if response.usage_metadata else 0
            }
            
            cost = self._calculate_cost(model_name, usage)
            latency = time.time() - start_time
            
            # 安全地獲取文本內容
            try:
                content = response.text
            except Exception as text_error:
                self.logger.error(f"無法獲取 Gemini 響應文本: {text_error}")
                content = "無法獲取響應內容"
            
            llm_response = LLMResponse(
                content=content,
                provider=LLMProvider.GEMINI,
                model=model_name,
                usage=usage,
                cost=cost,
                latency=latency,
                request_id=request_id,
                timestamp=time.time(),
                metadata={'safety_ratings': candidate.safety_ratings if hasattr(candidate, 'safety_ratings') else []}
            )
            
            self.update_stats(llm_response, True)
            # 記錄使用（吞錯，不影響主流程）
            try:
                usage_scene = request.metadata.get('usage_scene') if request and request.metadata else None
                await log_usage(
                    provider=self.provider_type.value,
                    model=model_name,
                    request_id=request_id,
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                    cost=cost,
                    latency_ms=int((latency) * 1000),
                    status="success",
                    service=(os.getenv("AGENT_NAME") or get_service_name()),
                    metadata={**(request.metadata or {}), **({"usage_scene": usage_scene} if usage_scene else {})},
                )
            except Exception:
                pass
            return llm_response
            
        except Exception as e:
            self.logger.error(f"Gemini API error: {e}")
            # 創建錯誤響應
            error_response = LLMResponse(
                content=f"Error: {str(e)}",
                provider=LLMProvider.GEMINI,
                model=request.model or self.default_model,
                usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                cost=0.0,
                latency=time.time() - start_time,
                request_id=request_id,
                timestamp=time.time(),
                metadata={'error': str(e)}
            )
            self.update_stats(error_response, False)
            try:
                await log_usage(
                    provider=self.provider_type.value,
                    model=request.model or self.default_model,
                    request_id=request_id,
                    cost=0.0,
                    latency_ms=int((time.time() - start_time) * 1000),
                    status="error",
                    error=str(e),
                    service=os.getenv("AGENT_NAME") or get_service_name(),
                    metadata={"error": str(e)}
                )
            except Exception:
                pass
            raise
    
    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """計算成本"""
        if model not in self.cost_config:
            return 0.0
        
        costs = self.cost_config[model]
        input_cost = (usage.get('prompt_tokens', 0) / 1_000_000) * costs['input']
        output_cost = (usage.get('completion_tokens', 0) / 1_000_000) * costs['output']
        return input_cost + output_cost
    
    def is_available(self) -> bool:
        """檢查 Gemini 是否可用"""
        return bool(self.api_key)
    
    def get_cost_per_token(self, model: str) -> Dict[str, float]:
        """獲取每個 token 的成本"""
        return self.cost_config.get(model, {'input': 0.0, 'output': 0.0})


class OpenAIProvider(BaseLLMProvider):
    """OpenAI 供應商實現"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(LLMProvider.OPENAI, config)
        
        self.api_key = config.get('api_key') or os.getenv("OPENAI_API_KEY")
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self.default_model = config.get('default_model', 'gpt-4o-mini')
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found")
        
        # 成本配置
        self.cost_config = {
            'gpt-4o': {'input': 2.50, 'output': 10.00},
            'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
            'gpt-4-turbo': {'input': 10.00, 'output': 30.00},
        }
    
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """執行 OpenAI 聊天完成請求"""
        start_time = time.time()
        request_id = f"openai_{int(time.time() * 1000)}"
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": request.model or self.default_model,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
            
            # 解析響應
            content = data['choices'][0]['message']['content']
            usage = data.get('usage', {})
            cost = self._calculate_cost(payload['model'], usage)
            latency = time.time() - start_time
            
            llm_response = LLMResponse(
                content=content,
                provider=LLMProvider.OPENAI,
                model=payload['model'],
                usage=usage,
                cost=cost,
                latency=latency,
                request_id=request_id,
                timestamp=time.time()
            )
            
            self.update_stats(llm_response, True)
            try:
                usage_scene = request.metadata.get('usage_scene') if request and request.metadata else None
                await log_usage(
                    provider=self.provider_type.value,
                    model=payload['model'],
                    request_id=request_id,
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                    cost=cost,
                    latency_ms=int((latency) * 1000),
                    status="success",
                    service=os.getenv("AGENT_NAME") or get_service_name(),
                    metadata={**(request.metadata or {}), **({"usage_scene": usage_scene} if usage_scene else {})},
                )
            except Exception:
                pass
            return llm_response
            
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            error_response = LLMResponse(
                content=f"Error: {str(e)}",
                provider=LLMProvider.OPENAI,
                model=request.model or self.default_model,
                usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                cost=0.0,
                latency=time.time() - start_time,
                request_id=request_id,
                timestamp=time.time(),
                metadata={'error': str(e)}
            )
            self.update_stats(error_response, False)
            try:
                await log_usage(
                    provider=self.provider_type.value,
                    model=request.model or self.default_model,
                    request_id=request_id,
                    cost=0.0,
                    latency_ms=int((time.time() - start_time) * 1000),
                    status="error",
                    error=str(e),
                    service=os.getenv("AGENT_NAME") or get_service_name(),
                    metadata={"error": str(e)}
                )
            except Exception:
                pass
            raise
    
    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """計算成本"""
        if model not in self.cost_config:
            return 0.0
        
        costs = self.cost_config[model]
        input_cost = (usage.get('prompt_tokens', 0) / 1_000_000) * costs['input']
        output_cost = (usage.get('completion_tokens', 0) / 1_000_000) * costs['output']
        return input_cost + output_cost
    
    def is_available(self) -> bool:
        """檢查 OpenAI 是否可用"""
        return bool(self.api_key)
    
    def get_cost_per_token(self, model: str) -> Dict[str, float]:
        """獲取每個 token 的成本"""
        return self.cost_config.get(model, {'input': 0.0, 'output': 0.0})


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter 供應商實現"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(LLMProvider.OPENROUTER, config)
        
        self.api_key = config.get('api_key') or os.getenv("OPENROUTER_API_KEY")
        self.base_url = config.get('base_url', 'https://openrouter.ai/api/v1')
        self.default_model = config.get('default_model', 'openai/gpt-4o-mini')
        self.site_url = config.get('site_url', 'https://localhost:3000')
        self.site_name = config.get('site_name', 'Social Media Content Generator')
        
        if not self.api_key:
            raise ValueError("OpenRouter API key not found")
        
        # 成本配置 (OpenRouter 動態定價，這裡提供估算)
        self.cost_config = {
            'openai/gpt-4o': {'input': 2.50, 'output': 10.00},
            'openai/gpt-4o-mini': {'input': 0.15, 'output': 0.60},
            'anthropic/claude-3.5-sonnet': {'input': 3.00, 'output': 15.00},
            'perplexity/sonar': {'input': 0.20, 'output': 0.20},
            'moonshotai/kimi-k2:free': {'input': 0.00, 'output': 0.00},
            'qwen/qwen3-235b-a22b:free': {'input': 0.00, 'output': 0.00},
        }
    
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """執行 OpenRouter 聊天完成請求"""
        start_time = time.time()
        request_id = f"openrouter_{int(time.time() * 1000)}"
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.site_url,
                "X-Title": self.site_name,
            }
            
            payload = {
                "model": request.model or self.default_model,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
            
            # 解析響應
            content = data['choices'][0]['message']['content']
            usage = data.get('usage', {})
            
            # 計算成本
            model_name = request.model or self.default_model
            cost = self._calculate_cost(model_name, usage)
            latency = time.time() - start_time
            
            llm_response = LLMResponse(
                content=content,
                provider=LLMProvider.OPENROUTER,
                model=model_name,
                usage=usage,
                cost=cost,
                latency=latency,
                request_id=request_id,
                timestamp=time.time(),
                metadata={}
            )
            
            self.update_stats(llm_response, True)
            try:
                usage_scene = request.metadata.get('usage_scene') if request and request.metadata else None
                await log_usage(
                    provider=self.provider_type.value,
                    model=model_name,
                    request_id=request_id,
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                    cost=cost,
                    latency_ms=int((latency) * 1000),
                    status="success",
                    service=os.getenv("AGENT_NAME") or get_service_name(),
                    metadata={**(request.metadata or {}), **({"usage_scene": usage_scene} if usage_scene else {})},
                )
            except Exception:
                pass
            return llm_response
            
        except Exception as e:
            self.logger.error(f"OpenRouter API error: {e}")
            self.update_stats(None, False)
            try:
                await log_usage(
                    provider=self.provider_type.value,
                    model=request.model or self.default_model,
                    request_id=request_id,
                    cost=0.0,
                    latency_ms=int((time.time() - start_time) * 1000),
                    status="error",
                    error=str(e),
                    service=os.getenv("AGENT_NAME") or get_service_name(),
                    metadata={"error": str(e)}
                )
            except Exception:
                pass
            raise
    
    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """計算 OpenRouter API 調用成本"""
        costs = self.get_cost_per_token(model)
        input_cost = (usage.get('prompt_tokens', 0) / 1_000_000) * costs['input']
        output_cost = (usage.get('completion_tokens', 0) / 1_000_000) * costs['output']
        return input_cost + output_cost
    
    def is_available(self) -> bool:
        """檢查 OpenRouter 供應商是否可用"""
        return bool(self.api_key)
    
    def get_cost_per_token(self, model: str) -> Dict[str, float]:
        """獲取 OpenRouter 每個 token 的成本"""
        config = self.cost_config.get(model, self.cost_config.get(self.default_model, {'input': 0.001, 'output': 0.002}))
        return {
            'input': config['input'],
            'output': config['output']
        }


class LLMManager:
    """統一 LLM 管理器"""
    
    def __init__(self):
        self.settings = get_settings()
        self.providers: Dict[LLMProvider, BaseLLMProvider] = {}
        self.logger = logging.getLogger("llm_manager")
        self.default_provider = LLMProvider.GEMINI
        self._initialize_providers()
    
    def _initialize_providers(self):
        """初始化所有可用的供應商"""
        # 初始化 Gemini
        try:
            gemini_config = {
                'api_key': os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
                'default_model': 'gemini-2.0-flash'
            }
            if gemini_config['api_key']:
                self.providers[LLMProvider.GEMINI] = GeminiProvider(gemini_config)
                self.logger.info("Gemini provider initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Gemini provider: {e}")
        
        # 初始化 OpenAI
        try:
            openai_config = {
                'api_key': os.getenv("OPENAI_API_KEY"),
                'default_model': 'gpt-4o-mini'
            }
            if openai_config['api_key']:
                self.providers[LLMProvider.OPENAI] = OpenAIProvider(openai_config)
                self.logger.info("OpenAI provider initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize OpenAI provider: {e}")
        
        # 初始化 OpenRouter
        try:
            openrouter_config = {
                'api_key': os.getenv("OPENROUTER_API_KEY"),
                'default_model': 'openai/gpt-4o-mini'
            }
            if openrouter_config['api_key']:
                self.providers[LLMProvider.OPENROUTER] = OpenRouterProvider(openrouter_config)
                self.logger.info("OpenRouter provider initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize OpenRouter provider: {e}")
        
        # 設置預設供應商
        if LLMProvider.GEMINI in self.providers:
            self.default_provider = LLMProvider.GEMINI
        elif LLMProvider.OPENAI in self.providers:
            self.default_provider = LLMProvider.OPENAI
        else:
            raise ValueError("No LLM providers available")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        provider: Optional[Union[str, LLMProvider]] = None,
        **kwargs
    ) -> LLMResponse:
        """統一的聊天完成接口"""
        
        # 確定使用的供應商
        if provider:
            if isinstance(provider, str):
                provider = LLMProvider(provider)
        else:
            provider = self.default_provider
        
        if provider not in self.providers:
            raise ValueError(f"Provider {provider.value} not available")
        
        # 創建請求
        request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=provider,
            metadata=kwargs
        )
        
        # 執行請求
        return await self.providers[provider].chat_completion(request)
    
    def get_available_providers(self) -> List[LLMProvider]:
        """獲取可用的供應商列表"""
        return [p for p, provider in self.providers.items() if provider.is_available()]
    
    def get_provider_stats(self, provider: LLMProvider) -> Optional[LLMUsageStats]:
        """獲取供應商使用統計"""
        if provider in self.providers:
            return self.providers[provider].stats
        return None
    
    def get_all_stats(self) -> Dict[str, LLMUsageStats]:
        """獲取所有供應商的統計"""
        return {
            provider.value: self.providers[provider].stats 
            for provider in self.providers
        }
    
    def set_default_provider(self, provider: Union[str, LLMProvider]):
        """設置預設供應商"""
        if isinstance(provider, str):
            provider = LLMProvider(provider)
        
        if provider not in self.providers:
            raise ValueError(f"Provider {provider.value} not available")
        
        self.default_provider = provider
        self.logger.info(f"Default provider set to {provider.value}")


# 全域 LLM 管理器實例
_llm_manager = None

def get_llm_manager() -> LLMManager:
    """獲取全域 LLM 管理器實例"""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager


# 便利函數
async def chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    provider: Optional[str] = None,
    **kwargs
) -> str:
    """便利的聊天完成函數，直接返回內容"""
    manager = get_llm_manager()
    response = await manager.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        provider=provider,
        **kwargs
    )
    return response.content


# 向後兼容的 LLMClient 類
class LLMClient:
    """向後兼容的 LLM 客戶端"""
    
    def __init__(self, provider_name: str = "gemini"):
        self.provider_name = provider_name
        self.manager = get_llm_manager()
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Dict[str, Any]:
        """向後兼容的聊天完成方法"""
        response = await self.manager.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=self.provider_name,
            **kwargs
        )
        
        # 轉換為 OpenAI 格式的響應
        return {
            "choices": [{
                "message": {
                    "content": response.content,
                    "role": "assistant"
                },
                "finish_reason": "stop"
            }],
            "usage": response.usage,
            "model": response.model,
            "id": response.request_id,
            "created": int(response.timestamp),
            "object": "chat.completion"
        }