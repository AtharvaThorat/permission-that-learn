from typing import Protocol

class FactsResolver(Protocol):
    def resolve(self, tool: str, arguments: dict, env) -> dict: ...
