"""Verify the pinned native dependency before execution or replay."""
import importlib.metadata
import json

def verify_distribution(config):
    dist = importlib.metadata.distribution('agentdojo')
    if dist.version != config.agentdojo.distribution_version:
        raise RuntimeError('AgentDojo distribution version mismatch')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    if direct.get('vcs_info', {}).get('commit_id') != config.agentdojo.source_revision:
        raise RuntimeError('Install the exact inspected AgentDojo Git revision; missing/mismatched provenance')
