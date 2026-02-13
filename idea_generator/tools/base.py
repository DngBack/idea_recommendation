"""
Abstract base class for tools used by the idea generator.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseTool(ABC):
    """
    Base class for defining tools that the LLM can invoke during ideation.

    Attributes:
        name: The tool name (used in ACTION parsing).
        description: Short description shown to the LLM.
        parameters: List of parameter dicts with 'name', 'type', 'description'.
    """

    def __init__(self, name: str, description: str, parameters: List[Dict[str, Any]]):
        self.name = name
        self.description = description
        self.parameters = parameters

    @abstractmethod
    def use_tool(self, **kwargs) -> Any:
        """Execute the tool with the given keyword arguments."""
        pass
