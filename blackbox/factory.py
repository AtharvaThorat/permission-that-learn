"""Public factory: construction performs no endpoint/model initialization."""
from pathlib import Path
from uuid import uuid4
from .config import Config, load_config
from .contracts import Dependencies

def build_agentdojo_pipeline(config, dependencies=None):
    from integrations.agentdojo.pipeline import GuardedAgentDojoPipeline
    if isinstance(config, (str, Path)):
        config = load_config(config)
    elif isinstance(config, dict):
        config = Config.model_validate(config)
    if not isinstance(config, Config):
        raise TypeError('Expected Config, config dictionary, or configuration path')
    return GuardedAgentDojoPipeline(config, dependencies or Dependencies())
