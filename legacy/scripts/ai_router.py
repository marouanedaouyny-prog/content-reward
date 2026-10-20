#!/usr/bin/env python3
"""
Automation Empire OS — AI Router
Routes LLM requests to available providers (NVIDIA, OpenRouter, Ollama, etc.)
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
from enum import Enum

import httpx
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


class ProviderKind(str, Enum):
    OLLAMA = "ollama"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    GROQ = "groq"


@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    response_format: Optional[Dict] = None


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: ProviderKind
    usage: Optional[Dict] = None
    error: Optional[str] = None


class BaseProvider:
    """Base class for LLM providers"""
    
    def __init__(self, kind: ProviderKind, config: Dict[str, Any]):
        self.kind = kind
        self.config = config
        # Disable SSL verification for development
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
    
    async def health_check(self) -> bool:
        raise NotImplementedError
    
    async def close(self):
        await self.client.aclose()


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(ProviderKind.OLLAMA, config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.default_model = config.get("default_model", "llama3.2")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.default_model
        
        payload = {
            "model": model,
            "messages": request.messages,
            "stream": request.stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }
        
        if request.response_format:
            payload["format"] = request.response_format
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model=model,
                provider=ProviderKind.OLLAMA,
                usage=data.get("eval_count")
            )
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return LLMResponse(content="", model=model, provider=ProviderKind.OLLAMA, error=str(e))
    
    async def health_check(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


class BaseProvider:
    """Base class for LLM providers"""
    
    def __init__(self, kind: ProviderKind, config: Dict[str, Any]):
        self.kind = kind
        self.config = config
        # Disable SSL verification for development
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
    
    async def health_check(self) -> bool:
        raise NotImplementedError
    
    async def close(self):
        await self.client.aclose()


class GroqProvider(BaseProvider):
    """Groq provider (OpenAI-compatible, very fast)"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(ProviderKind.GROQ, config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.groq.com/openai/v1")
        self.default_model = config.get("model", "llama-3.1-8b-instant")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="", model="", provider=ProviderKind.GROQ,
                error="GROQ_API_KEY not configured"
            )
        
        model = request.model or self.default_model
        
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        
        if request.response_format:
            payload["response_format"] = request.response_format
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        endpoints = [
            f"{self.base_url}/chat/completions",
        ]
        
        for endpoint in endpoints:
            try:
                response = await self.client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 404:
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                choice = data.get("choices", [{}])[0]
                return LLMResponse(
                    content=choice.get("message", {}).get("content", ""),
                    model=model,
                    provider=ProviderKind.GROQ,
                    usage=data.get("usage")
                )
            except Exception as e:
                logger.warning(f"Groq endpoint {endpoint} failed: {e}")
                continue
        
        return LLMResponse(content="", model=model, provider=ProviderKind.GROQ, error="Groq failed")
    
    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            return response.status_code == 200
        except Exception:
            # Even if health check fails, if we have API key, allow it to try
            return True


class GeminiProvider(BaseProvider):
    """Gemini provider (OpenAI-compatible)"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(ProviderKind.GEMINI, config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")
        self.default_model = config.get("model", "gemini-1.5-flash")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="", model="", provider=ProviderKind.GEMINI,
                error="GEMINI_API_KEY not configured"
            )
        
        model = request.model or self.default_model
        
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        
        if request.response_format:
            payload["response_format"] = request.response_format
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        endpoints = [
            f"{self.base_url}/chat/completions",
        ]
        
        for endpoint in endpoints:
            try:
                response = await self.client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 404:
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                choice = data.get("choices", [{}])[0]
                return LLMResponse(
                    content=choice.get("message", {}).get("content", ""),
                    model=model,
                    provider=ProviderKind.GEMINI,
                    usage=data.get("usage")
                )
            except Exception as e:
                logger.warning(f"Gemini endpoint {endpoint} failed: {e}")
                continue
        
        return LLMResponse(content="", model=model, provider=ProviderKind.GEMINI, error="Gemini failed")
    
    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            return response.status_code == 200
        except Exception:
            # Even if health check fails, if we have API key, allow it to try
            return True

    async def close(self):
        await self.client.aclose()


class GroqProvider(BaseProvider):
    """NVIDIA API provider (OpenAI-compatible)"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(ProviderKind.NVIDIA, config)
        self.api_key = config.get("api_key")
        # Use the correct NVIDIA API endpoint
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.default_model = config.get("model", "meta/llama-3.1-8b-instruct")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="", model="", provider=ProviderKind.NVIDIA,
                error="NVIDIA_API_KEY not configured"
            )
        
        model = request.model or self.default_model
        
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        
        if request.response_format:
            payload["response_format"] = request.response_format
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Try multiple NVIDIA endpoint formats
        endpoints = [
            f"{self.base_url}/chat/completions",
            "https://api.nvidia.com/v1/chat/completions",
            f"{self.base_url.rstrip('/v1')}/chat/completions",
        ]
        
        last_error = None
        for endpoint in endpoints:
            try:
                response = await self.client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 410 or response.status_code == 404:
                    continue  # Try next endpoint
                
                response.raise_for_status()
                data = response.json()
                
                choice = data.get("choices", [{}])[0]
                return LLMResponse(
                    content=choice.get("message", {}).get("content", ""),
                    model=model,
                    provider=ProviderKind.NVIDIA,
                    usage=data.get("usage")
                )
            except Exception as e:
                last_error = e
                logger.warning(f"NVIDIA endpoint {endpoint} failed: {e}")
                continue
        
        # All endpoints failed
        logger.error(f"NVIDIA all endpoints failed: {last_error}")
        return LLMResponse(content="", model=model, provider=ProviderKind.NVIDIA, error=str(last_error))
    
    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            return response.status_code == 200
        except Exception:
            # Even if health check fails, if we have API key, allow it to try
            return True

    async def close(self):
        await self.client.aclose()


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider (OpenAI-compatible)"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(ProviderKind.OPENROUTER, config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        self.default_model = config.get("model", "meta-llama/llama-3.1-8b-instruct:free")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="", model="", provider=ProviderKind.OPENROUTER,
                error="OPENROUTER_API_KEY not configured"
            )
        
        model = request.model or self.default_model
        
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        
        if request.response_format:
            payload["response_format"] = request.response_format
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://automation-empire.local",
            "X-Title": "Automation Empire OS",
        }
        
        # Try multiple OpenRouter endpoints
        endpoints = [
            f"{self.base_url}/chat/completions",
            "https://api.openrouter.ai/v1/chat/completions",
        ]
        
        last_error = None
        for endpoint in endpoints:
            try:
                response = await self.client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 404:
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                choice = data.get("choices", [{}])[0]
                return LLMResponse(
                    content=choice.get("message", {}).get("content", ""),
                    model=model,
                    provider=ProviderKind.OPENROUTER,
                    usage=data.get("usage")
                )
            except Exception as e:
                last_error = e
                logger.warning(f"OpenRouter endpoint {endpoint} failed: {e}")
                continue
        
        logger.error(f"OpenRouter all endpoints failed: {last_error}")
        return LLMResponse(content="", model=model, provider=ProviderKind.OPENROUTER, error=str(last_error))
    
    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0
            )
            return response.status_code == 200
        except Exception:
            return False


class AIRouter:
    """
    Routes LLM requests to available providers with fallback.
    Priority: Groq -> NVIDIA -> OpenRouter -> Ollama (local)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.providers: Dict[ProviderKind, BaseProvider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all configured providers"""
        # Ollama (always available as fallback)
        self.providers[ProviderKind.OLLAMA] = OllamaProvider({
            "base_url": self.settings.ollama_base_url,
            "default_model": self.settings.ollama_default_model,
        })
        
        # Groq (fast, generous free tier)
        if self.settings.groq_api_key:
            self.providers[ProviderKind.GROQ] = GroqProvider({
                "api_key": self.settings.groq_api_key,
                "base_url": self.settings.groq_base_url,
                "model": self.settings.groq_model,
            })
        
        # NVIDIA
        if self.settings.nvidia_api_key:
            self.providers[ProviderKind.NVIDIA] = NVIDIAProvider({
                "api_key": self.settings.nvidia_api_key,
                "base_url": self.settings.nvidia_base_url,
                "model": self.settings.nvidia_model,
            })
        
        # OpenRouter
        if self.settings.openrouter_api_key:
            self.providers[ProviderKind.OPENROUTER] = OpenRouterProvider({
                "api_key": self.settings.openrouter_api_key,
                "base_url": self.settings.openrouter_base_url,
                "model": self.settings.openrouter_model,
            })
        
        # Gemini
        if self.settings.gemini_api_key:
            self.providers[ProviderKind.GEMINI] = GeminiProvider({
                "api_key": self.settings.gemini_api_key,
                "base_url": self.settings.gemini_base_url,
                "model": self.settings.gemini_model,
            })
    
    def get_provider(self, kind: ProviderKind) -> Optional[BaseProvider]:
        return self.providers.get(kind)
    
    def get_available_providers(self) -> List[ProviderKind]:
        return list(self.providers.keys())
    
    async def complete(self, request: LLMRequest, preferred: Optional[ProviderKind] = None) -> LLMResponse:
        """
        Complete request with fallback logic.
        Priority order: preferred -> Groq -> NVIDIA -> OpenRouter -> Ollama
        """
        # Determine provider order
        provider_order = []
        if preferred and preferred in self.providers:
            provider_order.append(preferred)
        
        # Add remaining in priority order
        for kind in [ProviderKind.GROQ, ProviderKind.NVIDIA, ProviderKind.OPENROUTER, ProviderKind.OLLAMA]:
            if kind in self.providers and kind not in provider_order:
                provider_order.append(kind)
        
        last_error = None
        for kind in provider_order:
            provider = self.providers[kind]
            if kind != ProviderKind.OLLAMA:
                # Check health for cloud providers
                healthy = await provider.health_check()
                if not healthy:
                    logger.warning(f"Provider {kind} unhealthy, skipping")
                    continue
            
            logger.info(f"Using provider: {kind}")
            response = await provider.complete(request)
            
            if not response.error:
                return response
            
            last_error = response.error
            logger.warning(f"Provider {kind} failed: {last_error}")
        
        # All failed
        return LLMResponse(
            content="",
            model=request.model or "unknown",
            provider=preferred or ProviderKind.OLLAMA,
            error=last_error or "All providers failed"
        )
    
    async def health_check_all(self) -> Dict[ProviderKind, bool]:
        """Check health of all providers"""
        results = {}
        for kind, provider in self.providers.items():
            try:
                results[kind] = await provider.health_check()
            except Exception:
                results[kind] = False
        return results
    
    async def close(self):
        for provider in self.providers.values():
            await provider.close()


# Global router instance
_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    global _router
    if _router is None:
        _router = AIRouter()
    return _router


# Synchronous wrapper for agents
def llm_complete(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    response_format: Optional[Dict] = None,
    preferred_provider: Optional[str] = None
) -> LLMResponse:
    """Synchronous LLM completion for agents"""
    import asyncio
    
    router = get_router()
    request = LLMRequest(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format
    )
    
    preferred = None
    if preferred_provider:
        try:
            preferred = ProviderKind(preferred_provider)
        except ValueError:
            pass
    
    return asyncio.run(router.complete(request, preferred))