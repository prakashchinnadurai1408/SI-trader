"""SI-Trader LLM Frontend Configuration UI.

Provides a trader-facing configuration interface for managing LLM providers
with primary/fallback ordering. Can be run as CLI or imported as module.

Features:
- Add/remove LLM providers with API keys
- Set primary/fallback ordering (priority 1, 2, 3, etc.)
- Configure model name, temperature, max tokens
- Save/load configuration to JSON
- Provider status validation
- Integration with BrokerWrapper
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import json
import os
import sys
from pathlib import Path

# SI-Trader imports
from .llm_providers import (
    LlmProvider, LlmSettings, LlmConfigurationManager,
    PROVIDER_DISPLAY_NAMES, DEFAULT_MODELS, DEFAULT_BASE_URLS,
    DEFAULT_TEMPERATURES, DEFAULT_MAX_TOKENS
)


class ConfigMode(Enum):
    """UI display modes."""
    ADD_PROVIDER = "add"
    EDIT_PROVIDER = "edit"
    VIEW_PROVIDER = "view"
    REORDER_PROVIDERS = "reorder"
    DELETE_PROVIDER = "delete"
    SAVE_AND_EXIT = "save"


@dataclass
class ProviderFormState:
    """State for provider configuration form."""
    name: str = ""
    api_key: str = ""
    model_name: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    enabled: bool = True
    priority: int = 1


class LlmFrontend:
    """Trader-facing LLM configuration frontend."""

    def __init__(self, config_path: str = "llm_settings.json"):
        self.config_path = config_path
        self.settings = LlmSettings.load(config_path)
        self.manager = LlmConfigurationManager(self.settings)

    def run(self) -> None:
        """Run the LLM frontend configuration loop."""
        while True:
            self._print_header()
            self._print_provider_list()
            print()
            print("Commands:")
            print("  1. Add LLM provider")
            print("  2. Edit provider")
            print("  3. Remove provider")
            print("  4. Reorder providers")
            print("  5. Test current configuration")
            print("  6. Save and exit")
            print("  0. Exit without saving")
            print()

            choice = input("Enter choice (0-6): ").strip()
            print()

            if choice == "0":
                print("👋 Exiting without saving")
                break
            elif choice == "1":
                self._handle_add_provider()
            elif choice == "2":
                self._handle_edit_provider()
            elif choice == "3":
                self._handle_delete_provider()
            elif choice == "4":
                self._handle_reorder()
            elif choice == "5":
                self._test_configuration()
            elif choice == "6":
                self._save_and_exit()
                break
            else:
                print("❌ Invalid choice, please enter 0-6")
                input("Press Enter to continue...")

    def _print_header(self) -> None:
        """Print the UI header."""
        print("=" * 60)
        print("SI-TRADER LLM PROVIDER CONFIGURATION")
        print("=" * 60)
        summary = self.manager.get_config_summary()
        print(f"Primary: {summary.primary_provider}")
        print(f"Fallbacks: {', '.join(summary.fallback_providers) if summary.fallback_providers else 'none'}")
        print(f"Total enabled: {summary.total_enabled}")
        print(f"Auto-failover: {summary.auto_failover}")
        print()

    def _print_provider_list(self) -> None:
        """Print the list of configured providers."""
        enabled = self.manager.get_all_enabled()
        if not enabled:
            print("  No LLM providers currently configured")
            print("  Add a provider to enable LLM features")
            return

        print(f"  Current providers ({len(enabled)} enabled):")
        for p in enabled:
            display_name = PROVIDER_DISPLAY_NAMES.get(p["provider"], p["provider"])
            model = p.get("model_name", "").split("/")[-1] if "/" in p.get("model_name", "") else p.get("model_name", "")
            print(f"    Priority {p['priority']}: {display_name} - {model}")
        if len(enabled) < 3:
            print(f"  (Add more providers for fallback protection)")

    def _handle_add_provider(self) -> None:
        """Handle adding a new LLM provider."""
        print("=" * 60)
        print("Add LLM Provider")
        print("=" * 60)

        # Select provider
        print("Select provider:")
        for i, provider in enumerate(LlmProvider):
            print(f"  {i+1}. {PROVIDER_DISPLAY_NAMES.get(provider, provider.value)}")

        while True:
            try:
                prov_choice = input("Enter provider number (0 to cancel): ").strip()
                if prov_choice == "0":
                    return
                prov_idx = int(prov_choice) - 1
                if 0 <= prov_idx < len(LlmProvider):
                    selected_provider = list(LlmProvider)[prov_idx]
                    break
                else:
                    print("❌ Invalid number, try again")
            except ValueError:
                print("❌ Please enter a number")

        # Get API key
        api_key = input("API key (from vault/environment, press Enter to use default placeholder): ").strip()
        if not api_key:
            api_key = f"<{selected_provider.value.upper()}_KEY>"

        # Get model name
        model_name = input(f"Model name (press Enter for default: {DEFAULT_MODELS.get(selected_provider, '')}): ").strip() or None

        # Get base URL
        base_url = input(f"Base URL (press Enter for default): ").strip() or None

        # Get temperature
        temp_input = input(f"Temperature (press Enter for default: {DEFAULT_TEMPERATURES.get(selected_provider, 0.3)}): ").strip()
        temperature = float(temp_input) if temp_input else None

        # Get max tokens
        max_tokens_input = input(f"Max tokens (press Enter for default: {DEFAULT_MAX_TOKENS.get(selected_provider, 2048)}): ").strip()
        max_tokens = int(max_tokens_input) if max_tokens_input else None

        # Get enabled status
        enabled_input = input("Enabled? (y/n, default y): ").strip().lower()
        enabled = enabled_input not in ('n', 'no') if enabled_input else True

        # Get priority
        priority_input = input("Priority (1=primary, 2=fallback, press Enter for auto): ").strip()
        priority = int(priority_input) if priority_input else None

        # Add the provider
        self.manager.configure_from_trader({
            'providers': [{
                'name': PROVIDER_DISPLAY_NAMES.get(selected_provider, selected_provider.value),
                'api_key': api_key,
                'model_name': model_name,
                'base_url': base_url,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'enabled': enabled,
                'priority': priority or len(self.manager.get_enabled_providers()) + 1
            }]
        })

        print(f"✅ Provider added: {PROVIDER_DISPLAY_NAMES.get(selected_provider, selected_provider.value)}")
        input("Press Enter to continue...")

    def _handle_edit_provider(self) -> None:
        """Handle editing an existing provider."""
        enabled = self.manager.get_enabled_providers()
        if not enabled:
            print("❌ No providers to edit")
            input("Press Enter to continue...")
            return

        print("=" * 60)
        print("Edit LLM Provider")
        print("=" * 60)
        for i, p in enumerate(enabled):
            display_name = PROVIDER_DISPLAY_NAMES.get(p["provider"], p["provider"])
            print(f"  {i+1}. {display_name} - {p['model_name']} (Priority {p['priority']})")

        while True:
            try:
                prov_choice = input("Enter provider number to edit (0 to cancel): ").strip()
                if prov_choice == "0":
                    return
                prov_idx = int(prov_choice) - 1
                if 0 <= prov_idx < len(enabled):
                    selected = enabled[prov_idx]
                    break
                else:
                    print("❌ Invalid number, try again")
            except ValueError:
                print("❌ Please enter a number")

        print(f"\nEditing: {PROVIDER_DISPLAY_NAMES.get(selected['provider'], selected['provider'])}")
        print(f"Current model: {selected['model_name']}")
        print(f"Current API key: {selected['api_key'][:8]}...{selected['api_key'][-4:] if len(selected['api_key']) > 12 else selected['api_key']}")

        # Edit fields
        model_input = input(f"Model name (press Enter to keep: {selected['model_name']}): ").strip()
        model_name = model_input if model_input else selected['model_name']

        key_input = input(f"API key (press Enter to keep): ").strip()
        api_key = key_input if key_input else selected['api_key']

        base_input = input(f"Base URL (press Enter to keep): ").strip()
        base_url = base_input if base_input else selected.get('base_url', '')

        temp_input = input(f"Temperature (press Enter to keep: {selected.get('temperature', 0.3)}): ").strip()
        temperature = float(temp_input) if temp_input else selected.get('temperature', 0.3)

        tokens_input = input(f"Max tokens (press Enter to keep): ").strip()
        max_tokens = int(tokens_input) if tokens_input else selected.get('max_tokens', 2048)

        enabled_input = input(f"Enabled? (y/n, current: {selected['enabled']}, press Enter to keep): ").strip().lower()
        enabled = enabled_input not in ('n', 'no') if enabled_input else selected['enabled']

        priority_input = input(f"Priority (press Enter to keep: {selected['priority']}): ").strip()
        priority = int(priority_input) if priority_input else selected['priority']

        # Update the provider in the manager
        # Need to find and update by provider key
        provider_key = selected['provider']
        for i, p in enumerate(self.manager.llm_settings.providers):
            if p['provider'] == provider_key:
                self.manager.llm_settings.providers[i] = {
                    'provider': provider_key,
                    'api_key': api_key,
                    'model_name': model_name,
                    'base_url': base_url,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'enabled': enabled,
                    'priority': priority,
                }
                break

        print("✅ Provider updated")
        input("Press Enter to continue...")

    def _handle_delete_provider(self) -> None:
        """Handle deleting a provider."""
        enabled = self.manager.get_enabled_providers()
        if not enabled:
            print("❌ No providers to delete")
            input("Press Enter to continue...")
            return

        print("=" * 60)
        print("Delete LLM Provider")
        print("=" * 60)
        for i, p in enumerate(enabled):
            display_name = PROVIDER_DISPLAY_NAMES.get(p['provider'], p['provider'])
            print(f"  {i+1}. {display_name} - {p['model_name']} (Priority {p['priority']})")

        while True:
            try:
                prov_choice = input("Enter provider number to delete (0 to cancel): ").strip()
                if prov_choice == "0":
                    return
                prov_idx = int(prov_choice) - 1
                if 0 <= prov_idx < len(enabled):
                    selected = enabled[prov_idx]
                    break
                else:
                    print("❌ Invalid number, try again")
            except ValueError:
                print("❌ Please enter a number")

        # Remove from settings
        provider_key = selected['provider']
        self.manager.remove_provider(provider_key)
        self.settings.providers = self.manager.llm_settings.providers  # Sync

        print("✅ Provider removed")
        input("Press Enter to continue...")

    def _handle_reorder(self) -> None:
        """Handle reordering providers."""
        enabled = self.manager.get_enabled_providers()
        if len(enabled) < 2:
            print("❌ Need at least 2 providers to reorder")
            input("Press Enter to continue...")
            return

        print("=" * 60)
        print("Reorder LLM Providers")
        print("=" * 60)
        for i, p in enumerate(enabled):
            display_name = PROVIDER_DISPLAY_NAMES.get(p['provider'], p['provider'])
            print(f"  {i+1}. {display_name} - Priority {p['priority']}")

        print("\nEnter new priority order (1, 2, 3, ...):")
        while True:
            try:
                order_input = input("Enter comma-separated priority numbers: ").strip()
                new_order = [int(x.strip()) for x in order_input.split(",")]
                if len(new_order) == len(enabled) and sorted(new_order) == list(range(1, len(enabled) + 1)):
                    # Reorder the providers
                    provider_map = {p['priority']: p for p in enabled}
                    new_providers = [provider_map[p] for p in new_order]
                    self.manager.llm_settings.providers = new_providers
                    self.settings.providers = new_providers
                    print("✅ Providers reordered")
                    input("Press Enter to continue...")
                    return
                else:
                    print(f"❌ Please enter {len(enabled)} unique numbers from 1-{len(enabled)}")
            except ValueError:
                print("❌ Please enter valid numbers separated by commas")

    def _test_configuration(self) -> None:
        """Test the current LLM configuration."""
        print("=" * 60)
        print("Testing LLM Configuration")
        print("=" * 60)

        enabled = self.manager.get_all_enabled()
        if not enabled:
            print("❌ No enabled providers")
            input("Press Enter to continue...")
            return

        primary = enabled[0]
        print(f"Testing primary provider: {PROVIDER_DISPLAY_NAMES.get(primary['provider'], primary['provider'])}")
        print(f"Model: {primary['model_name']}")
        print(f"API key present: {bool(primary.get('api_key', '').strip())}")
        print(f"Temperature: {primary.get('temperature', 0.3)}")
        print(f"Max tokens: {primary.get('max_tokens', 2048)}")

        # Verify configuration
        is_valid = self.manager.verify_configuration()
        if is_valid:
            print("✅ Configuration validated successfully")
        else:
            print("⚠️ Configuration has issues (check warnings above)")

        input("Press Enter to continue...")

    def _save_and_exit(self) -> None:
        """Save configuration and exit."""
        self.settings.save(self.config_path)
        print(f"💾 LLM settings saved to {self.config_path}")
        print("✅ Configuration complete")
        input("Press Enter to return to main menu...")

    def _print_config_summary(self) -> None:
        """Print configuration summary before saving."""
        summary = self.manager.get_config_summary()
        print("\nConfiguration Summary:")
        print(f"  Primary provider: {summary.primary_provider}")
        print(f"  Fallback providers: {', '.join(summary.fallback_providers) if summary.fallback_providers else 'none'}")
        print(f"  Total enabled: {summary.total_enabled}")
        print(f"  Auto-failover: {summary.auto_failover}")
        print()

def main():
    """Entry point for LLM frontend."""
    frontend = LlmFrontend()
    frontend.run()


if __name__ == "__main__":
    main()