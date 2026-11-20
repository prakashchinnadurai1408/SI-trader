"""LLM Provider Configuration for SI-Trader Broker Wrapper.

Trader can configure multiple LLM providers with primary and fallback ordering.
Each provider requires API keys (from vault/environment, never plain-text in chat).

Supported Providers:
- openai: ChatGPT (gpt-4, gpt-3.5-turbo)
- anthropic: Claude (claude-3-opus, claude-3-sonnet, claude-3-haiku)
- nvidia: NVIDIA NIM/LLMs (nvidia/llama-3.1-nemotron-ultra-253b-v1, etc.)
- gemini: Google Gemini (gemini-1.5-flash, gemini-1.5-pro)
- deepseek: DeepSeek (deepseek-coder, deepseek-v3)
- grok: xAI Grok (grok-beta, grok-2)
- z.ai: Z.ai MaaS (glm-4, glm-3.5)
- kimi: KIMI (kimi-k2, kimi-hardware)
- qwen: Alibaba Qwen (qwen-max, qwen-2-72b, qwen-4)
- ollama: Local Ollama (llama3, mistral, phi3, etc.)

Configuration Format:
- Provider: string identifier
- api_key: from vault/environment (write-only)
- model_name: specific model identifier
- base_url: API endpoint URL
- temperature: sampling temperature (0.0-1.0)
- max_tokens: maximum response tokens
- enabled: whether provider is active
- priority: ordering (1=primary, 2=fallback, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Any
import json
import os
from pathlib import Path


class LlmProvider(Enum):
    """Enumeration of supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    NVIDIA = "nvidia"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    GROK = "grok"
    Z_AI = "z.ai"
    KIMI = "kimi"
    QWEN = "qwen"
    OLLAMA = "ollama"
    # Additional providers can be added
    CUSTOM = "custom"


# Human-readable display names for each provider
PROVIDER_DISPLAY_NAMES: Dict[LlmProvider, str] = {
    LlmProvider.OPENAI: "OpenAI ChatGPT",
    LlmProvider.ANTHROPIC: "Anthropic Claude",
    LlmProvider.NVIDIA: "NVIDIA NIM/LLMs",
    LlmProvider.GEMINI: "Google Gemini",
    LlmProvider.DEEPSEEK: "DeepSeek",
    LlmProvider.GROK: "xAI Grok",
    LlmProvider.Z_AI: "Z.ai MaaS",
    LlmProvider.KIMI: "KIMI",
    LlmProvider.QWEN: "Alibaba Qwen",
    LlmProvider.OLLAMA: "Ollama (Local)",
    LlmProvider.CUSTOM: "Custom Provider",
}

# Default model names per provider (can be overridden by trader)
DEFAULT_MODELS: Dict[LlmProvider, str] = {
    LlmProvider.OPENAI: "gpt-4o-mini",
    LlmProvider.ANTHROPIC: "claude-3-haiku-20240307",
    LlmProvider.NVIDIA: "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    LlmProvider.GEMINI: "gemini-1.5-flash",
    LlmProvider.DEEPSEEK: "deepseek-coder-v2",
    LlmProvider.GROK: "grok-beta",
    LlmProvider.Z_AI: "glm-4",
    LlmProvider.KIMI: "kimi-k2",
    LlmProvider.QWEN: "qwen-max",
    LlmProvider.OLLAMA: "llama3",
    LlmProvider.CUSTOM: "custom-model",
}

# Default base URLs per provider
DEFAULT_BASE_URLS: Dict[LlmProvider, str] = {
    LlmProvider.OPENAI: "https://api.openai.com/v1",
    LlmProvider.ANTHROPIC: "https://api.anthropic.com/v1",
    LlmProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
    LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    LlmProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    LlmProvider.GROK: "https://api.x.ai/v1",
    LlmProvider.Z_AI: "https://open.bigmodel.cn/api/v1",
    LlmProvider.KIMI: "https://api.moonshot.cn/v1",
    LlmProvider.QWEN: "https://dashscope.aliyuncs.com/compatible/v1",
    LlmProvider.OLLAMA: "http://localhost:11434",
    LlmProvider.CUSTOM: "https://api.example.com/v1",
}

# Default temperature per provider
DEFAULT_TEMPERATURES: Dict[LlmProvider, float] = {
    LlmProvider.OPENAI: 0.3,
    LlmProvider.ANTHROPIC: 0.3,
    LlmProvider.NVIDIA: 0.3,
    LlmProvider.GEMINI: 0.3,
    LlmProvider.DEEPSEEK: 0.3,
    LlmProvider.GROK: 0.3,
    LlmProvider.Z_AI: 0.3,
    LlmProvider.KIMI: 0.3,
    LlmProvider.QWEN: 0.3,
    LlmProvider.OLLAMA: 0.7,
    LlmProvider.CUSTOM: 0.3,
}

# Default max tokens per provider
DEFAULT_MAX_TOKENS: Dict[LlmProvider, int] = {
    LlmProvider.OPENAI: 2048,
    LlmProvider.ANTHROPIC: 2048,
    LlmProvider.NVIDIA: 2048,
    LlmProvider.GEMINI: 2048,
    LlmProvider.DEEPSEEK: 2048,
    LlmProvider.GROK: 2048,
    LlmProvider.Z_AI: 2048,
    LlmProvider.KIMI: 2048,
    LlmProvider.QWEN: 2048,
    LlmProvider.OLLAMA: 4096,
    LlmProvider.CUSTOM: 2048,
}


@dataclass
class LlmSettings:
    """LLM configuration settings for SI-Trader broker wrapper.

    Trader configures these settings (primary/fallback ordering, API keys,
    model preferences) through the wrapper configuration page.

    Key Features:
    - Primary + fallback provider ordering
    - Per-provider API keys (secure, from vault)
    - Per-provider model selection
    - Per-provider temperature and token limits
    - Save/load configuration to JSON
    - Automatic failover when primary provider fails
    """

    # Provider configuration in priority order
    # Index 0 = primary, 1 = first fallback, 2 = second fallback, etc.
    providers: List[Dict[str, Any]] = field(default_factory=lambda: [])

    # Default parameters used when no per-provider settings override
    default_temperature: float = 0.3
    default_max_tokens: int = 2048

    # Whether to auto-enable next provider if current fails
    auto_failover: bool = True

    # Cache for resolved provider configs (populated at runtime)
    _provider_configs: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self):
        """Ensure providers list is properly initialized after dataclass creation."""
        if not self.providers:
            # Initialize with default NVIDIA provider
            self.providers = [
                {
                    "provider": LlmProvider.NVIDIA.value,
                    "api_key": "",
                    "model_name": DEFAULT_MODELS[LlmProvider.NVIDIA],
                    "base_url": DEFAULT_BASE_URLS[LlmProvider.NVIDIA],
                    "temperature": DEFAULT_TEMPERATURES[LlmProvider.NVIDIA],
                    "max_tokens": DEFAULT_MAX_TOKENS[LlmProvider.NVIDIA],
                    "enabled": True,
                    "priority": 1,
                }
            ]

    def add_provider(
        self,
        provider: LlmProvider,
        api_key: str = "",
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enabled: bool = True,
        priority: Optional[int] = None,
    ) -> None:
        """Add or update an LLM provider configuration.

        Args:
            provider: LlmProvider enum value
            api_key: API key from vault/environment (write-only)
            model_name: specific model identifier (uses default if None)
            base_url: API endpoint URL (uses default if None)
            temperature: sampling temperature (uses default if None)
            max_tokens: maximum response tokens (uses default if None)
            enabled: whether this provider is active
            priority: priority order (1=primary, 2=fallback, etc.) auto-assigned if None
        """
        # Determine priority if not specified
        if priority is None:
            # Assign next available priority
            existing_priorities = [p.get("priority", 0) for p in self.providers]
            priority = max(existing_priorities) + 1 if existing_priorities else 1

        # Check if provider already exists (update it)
        provider_key = provider.value
        for i, prov in enumerate(self.providers):
            if prov["provider"] == provider_key:
                # Update existing
                self.providers[i] = {
                    "provider": provider_key,
                    "api_key": api_key,
                    "model_name": model_name or DEFAULT_MODELS.get(provider, ""),
                    "base_url": base_url or DEFAULT_BASE_URLS.get(provider, ""),
                    "temperature": temperature or DEFAULT_TEMPERATURES.get(provider, 0.3),
                    "max_tokens": max_tokens or DEFAULT_MAX_TOKENS.get(provider, 2048),
                    "enabled": enabled,
                    "priority": priority,
                }
                return

        # Add new provider
        self.providers.append(
            {
                "provider": provider_key,
                "api_key": api_key,
                "model_name": model_name or DEFAULT_MODELS.get(provider, ""),
                "base_url": base_url or DEFAULT_BASE_URLS.get(provider, ""),
                "temperature": temperature or DEFAULT_TEMPERATURES.get(provider, 0.3),
                "max_tokens": max_tokens or DEFAULT_MAX_TOKENS.get(provider, 2048),
                "enabled": enabled,
                "priority": priority,
            }
        )

        # Sort by priority
        self.providers.sort(key=lambda p: p.get("priority", 999))

    def remove_provider(self, provider: LlmProvider) -> None:
        """Remove an LLM provider configuration."""
        provider_key = provider.value
        self.providers = [p for p in self.providers if p["provider"] != provider_key]

    def get_primary_provider(self) -> Optional[Dict[str, Any]]:
        """Get the primary (first) configured provider."""
        if self.providers and self.providers[0].get("enabled"):
            return self.providers[0]
        return None

    def get_fallback_providers(self) -> List[Dict[str, Any]]:
        """Get all configured fallback providers (excluding primary)."""
        if len(self.providers) <= 1:
            return []
        return [p for p in self.providers[1:] if p.get("enabled")]

    def get_provider(self, priority: int) -> Optional[Dict[str, Any]]:
        """Get provider at specific priority position."""
        for p in self.providers:
            if p.get("priority") == priority:
                return p
        return None

    def is_provider_enabled(self, provider: LlmProvider) -> bool:
        """Check if a specific provider is enabled."""
        provider_key = provider.value
        for p in self.providers:
            if p.get("provider") == provider_key:
                return p.get("enabled", False)
        return False

    def get_effective_temperature(self, provider_index: int = 0) -> float:
        """Get the effective temperature for the provider at given priority."""
        provider = self.get_provider(provider_index + 1)  # +1 because priority 1 is index 0
        if provider:
            return provider.get("temperature", self.default_temperature)
        return self.default_temperature

    def get_effective_max_tokens(self, provider_index: int = 0) -> int:
        """Get the effective max tokens for the provider at given priority."""
        provider = self.get_provider(provider_index + 1)
        if provider:
            return provider.get("max_tokens", self.default_max_tokens)
        return self.default_max_tokens

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for serialization."""
        return {
            "default_temperature": self.default_temperature,
            "default_max_tokens": self.default_max_tokens,
            "auto_failover": self.auto_failover,
            "providers": self.providers,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LlmSettings:
        """Create LlmSettings from dictionary (for deserialization)."""
        settings = cls(
            default_temperature=data.get("default_temperature", 0.3),
            default_max_tokens=data.get("default_max_tokens", 2048),
            auto_failover=data.get("auto_failover", True),
        )
        # Restore providers
        if "providers" in data:
            settings.providers = data["providers"]
        return settings

    def save(self, path: str = "llm_settings.json") -> None:
        """Save LLM settings to JSON file."""
        data = self.to_dict()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"💾 LLM settings saved to {path}")

    @classmethod
    def load(cls, path: str = "llm_settings.json") -> LlmSettings:
        """Load LLM settings from JSON file."""
        if not os.path.exists(path):
            print(f"⚠️ LLM settings file not found: {path}, using defaults")
            return cls()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Failed to load LLM settings: {e}, using defaults")
            return cls()

    def get_enabled_providers(self) -> List[Dict[str, Any]]:
        """Get list of enabled providers sorted by priority."""
        return [p for p in self.providers if p.get("enabled")]

    def get_provider_info(self, provider: LlmProvider) -> Optional[Dict[str, Any]]:
        """Get configuration info for a specific provider."""
        provider_key = provider.value
        for p in self.providers:
            if p.get("provider") == provider_key:
                return {
                    "name": PROVIDER_DISPLAY_NAMES.get(provider, provider.value.title()),
                    "provider": provider_key,
                    "model": p.get("model_name", ""),
                    "base_url": p.get("base_url", ""),
                    "temperature": p.get("temperature", 0.3),
                    "max_tokens": p.get("max_tokens", 2048),
                    "enabled": p.get("enabled", False),
                    "priority": p.get("priority", 999),
                }
        return None


@dataclass
class LlmConfigSummary:
    """Summary of LLM configuration for display/UI purposes."""

    primary_provider: str
    primary_model: str
    fallback_providers: List[str]
    total_enabled: int
    auto_failover: bool
    trader_can_configure: bool = True


class LlmConfigurationManager:
    """Manages LLM configuration for the SI-Trader broker wrapper.

    Handles:
    - Trader configuration of primary/fallback LLM providers
    - API key management (secure, from vault)
    - Provider failover logic
    - Integration with broker wrapper
    - Configuration save/load for frontend integration
    """

    def __init__(self, llm_settings: Optional[LlmSettings] = None):
        self.llm_settings = llm_settings or LlmSettings()
        self._current_provider_index: int = 0  # Start with primary

    def configure_from_trader(self, config_data: Dict[str, Any]) -> None:
        """Configure LLM settings from trader input (frontend form submission).

        Args:
            config_data: Dictionary with provider configurations from trader
        """
        # Clear existing providers
        self.llm_settings.providers = []

        # Add providers from trader config
        for i, provider_config in enumerate(config_data.get("providers", [])):
            provider_name = provider_config.get("name", "").lower()
            # Map string to LlmProvider enum
            provider_map = {
                "openai": LlmProvider.OPENAI,
                "anthropic": LlmProvider.ANTHROPIC,
                "nvidia": LlmProvider.NVIDIA,
                "gemini": LlmProvider.GEMINI,
                "deepseek": LlmProvider.DEEPSEEK,
                "grok": LlmProvider.GROK,
                "z.ai": LlmProvider.Z_AI,
                "kimi": LlmProvider.KIMI,
                "qwen": LlmProvider.QWEN,
                "ollama": LlmProvider.OLLAMA,
                "custom": LlmProvider.CUSTOM,
            }

            provider = provider_map.get(provider_name, LlmProvider.CUSTOM)

            self.llm_settings.add_provider(
                provider=provider,
                api_key=provider_config.get("api_key", ""),
                model_name=provider_config.get("model_name", ""),
                base_url=provider_config.get("base_url", ""),
                temperature=provider_config.get("temperature", 0.3),
                max_tokens=provider_config.get("max_tokens", 2048),
                enabled=provider_config.get("enabled", True),
                priority=provider_config.get("priority", i + 1),
            )

        print(f"🤖 LLM configuration updated by trader:")
        for p in self.llm_settings.get_enabled_providers():
            print(f"   Priority {p['priority']}: {PROVIDER_DISPLAY_NAMES.get(p['provider'], p['provider'])} - {p['model_name']}")

    def get_current_provider(self) -> Optional[Dict[str, Any]]:
        """Get the currently active (primary) provider configuration."""
        return self.llm_settings.get_primary_provider()

    def get_next_fallback(self) -> Optional[Dict[str, Any]]:
        """Get the next fallback provider for failover."""
        fallbacks = self.llm_settings.get_fallback_providers()
        return fallbacks[0] if fallbacks else None

    def get_all_enabled(self) -> List[Dict[str, Any]]:
        """Get all enabled providers in priority order."""
        return self.llm_settings.get_enabled_providers()

    def get_config_summary(self) -> LlmConfigSummary:
        """Get a summary of the LLM configuration for display."""
        enabled = self.llm_settings.get_enabled_providers()

        primary = enabled[0] if enabled else {}
        fallback_names = [
            PROVIDER_DISPLAY_NAMES.get(p["provider"], p["provider"])
            for p in enabled[1:]
        ]

        return LlmConfigSummary(
            primary_provider=primary.get("model_name", "None") if primary else "None",
            primary_model=primary.get("model_name", "") if primary else "",
            fallback_providers=fallback_names,
            total_enabled=len(enabled),
            auto_failover=self.llm_settings.auto_failover,
        )

    def reset_to_defaults(self) -> None:
        """Reset LLM configuration to defaults (NVIDIA provider)."""
        self.llm_settings = LlmSettings()
        print("♻️ LLM configuration reset to defaults (NVIDIA primary)")

    def verify_configuration(self) -> bool:
        """Verify that LLM configuration is valid and usable."""
        enabled = self.llm_settings.get_enabled_providers()

        if not enabled:
            print("⚠️ No LLM providers enabled - configure at least one provider")
            return False

        # Check that primary provider has API key
        primary = enabled[0]
        if not primary.get("api_key", "").strip():
            print("⚠️ Primary provider has no API key - configure API key from vault")
            return False

        # Check that at least one model name is set
        for p in enabled:
            if not p.get("model_name", "").strip():
                print(f"⚠️ Provider {p['provider']} has no model name configured")
                # Continue - might use default

        print(f"✅ LLM configuration verified: {len(enabled)} provider(s) enabled")
        return True


# Global instance - will be initialized when wrapper starts
_llm_config_manager: Optional[LlmConfigurationManager] = None


def get_llm_config_manager() -> LlmConfigurationManager:
    """Get the global LLM configuration manager instance."""
    global _llm_config_manager
    if _llm_config_manager is None:
        _llm_config_manager = LlmConfigurationManager()
    return _llm_config_manager


def initialize_llm_config_from_file(path: str = "llm_settings.json") -> LlmConfigurationManager:
    """Initialize LLM config manager from saved settings file."""
    global _llm_config_manager
    settings = LlmSettings.load(path)
    _llm_config_manager = LlmConfigurationManager(settings)
    return _llm_config_manager


# CLI helper for trader to configure LLM settings
def cli_configure_llm():
    """CLI interface for trader to configure LLM providers."""
    import sys

    print("=" * 60)
    print("SI-Trader LLM Provider Configuration")
    print("=" * 60)
    print()
    print("Configure LLM providers with primary/fallback ordering.")
    print("API keys should be from vault/environment, never plain-text.")
    print()
    print("Supported providers:")
    for i, provider in enumerate(LlmProvider):
        print(f"  {i+1}. {PROVIDER_DISPLAY_NAMES.get(provider, provider.value)}")
    print()
    print("0. Exit configuration")
    print()

    while True:
        choice = input("Select provider number (or 0 to exit): ").strip()
        if choice == "0":
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(LlmProvider):
                print("❌ Invalid choice, try again")
                continue

            selected_provider = list(LlmProvider)[idx]
            print(f"\nConfiguring: {PROVIDER_DISPLAY_NAMES.get(selected_provider, selected_provider.value)}")

            api_key = input("API key (from vault/press Enter to skip): ").strip()
            model_name = input(f"Model name (press Enter for default: {DEFAULT_MODELS.get(selected_provider, '')}): ").strip() or None
            base_url = input(f"Base URL (press Enter for default): ").strip() or None
            temp_input = input(f"Temperature (press Enter for default: {DEFAULT_TEMPERATURES.get(selected_provider, 0.3)}): ").strip()
            temperature = float(temp_input) if temp_input else None
            max_tokens_input = input(f"Max tokens (press Enter for default: {DEFAULT_MAX_TOKENS.get(selected_provider, 2048)}): ").strip()
            max_tokens = int(max_tokens_input) if max_tokens_input else None

            enabled_input = input("Enabled? (y/n, default y): ").strip().lower()
            enabled = enabled_input not in ('n', 'no') if enabled_input else True

            priority_input = input("Priority (1=primary, 2=fallback, press Enter for auto): ").strip()
            priority = int(priority_input) if priority_input else None

            # Add to settings
            from nifty100_weekly.nifty100_adapter.broker.llm_providers import LlmSettings
            settings = LlmSettings.load() if os.path.exists("llm_settings.json") else LlmSettings()
            settings.add_provider(
                provider=selected_provider,
                api_key=api_key if api_key else "",
                model_name=model_name,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                enabled=enabled,
                priority=priority,
            )
            settings.save("llm_settings.json")

            print(f"✅ Provider configured and saved")
            print(f"   Model: {model_name or DEFAULT_MODELS.get(selected_provider, '')}")
            print(f"   Temperature: {temperature or DEFAULT_TEMPERATURES.get(selected_provider, 0.3)}")
            print(f"   Enabled: {enabled}")

        except ValueError:
            print("❌ Invalid input, please enter a number")

    print("\nLLM configuration complete. Use 'python run_si_trader.bat' to start.")


if __name__ == "__main__":
    cli_configure_llm()