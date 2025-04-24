# backend/app/strategies/action_registry.py

from typing import Dict, List, Type
from app.services.action_suggester import ActionStrategy


class ActionRegistry:
    """Registry for managing action strategies"""

    _strategies: Dict[str, List[Type[ActionStrategy]]] = {}

    @classmethod
    def register(cls, context: str, strategy: Type[ActionStrategy]) -> None:
        """Register a new action strategy for a specific context"""
        if context not in cls._strategies:
            cls._strategies[context] = []
        cls._strategies[context].append(strategy)

    @classmethod
    def get_strategies(cls, context: str) -> List[Type[ActionStrategy]]:
        """Get all registered strategies for a context"""
        return cls._strategies.get(context, [])

    @classmethod
    def get_default_strategies(cls) -> List[Type[ActionStrategy]]:
        """Get default strategies for unknown contexts"""
        return cls._strategies.get("default", [])
