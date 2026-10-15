"""Guarded agent runtime. Importing this package performs no initialization."""

def build_agentdojo_pipeline(config, dependencies=None):
    from .factory import build_agentdojo_pipeline as build
    return build(config, dependencies)
