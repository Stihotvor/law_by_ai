from agents.fetch.registry import autoload

from .base import STRATEGIES

autoload(__name__, STRATEGIES)
