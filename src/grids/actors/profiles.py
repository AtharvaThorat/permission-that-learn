"""Serving provenance is data, never permission-controller behavior."""
import json
from pathlib import Path
import re

PARSERS = {'hermes', 'qwen3_coder', 'mistral', 'llama3_json', 'granite4', 'phi4_mini_json'}


def load_profile(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('model_id', 'served_model_name', 'chat_template', 'dtype', 'vllm_version', 'transformers_version'):
        if not isinstance(data.get(key), str) or not data[key]: raise ValueError('Missing model profile field: '+key)
    if not re.fullmatch('[a-f0-9]{40}', data.get('revision', '')):
        raise ValueError('Model profiles require an immutable revision')
    if data.get('tool_call_parser') not in PARSERS: raise ValueError('Unsupported profile tool parser')
    if not re.fullmatch(r'actor(?:-[a-z0-9]+)*', data.get('environment_name', 'actor')):
        raise ValueError('Invalid isolated environment name')
    for key in ('context_limit', 'max_num_seqs'):
        if type(data.get(key)) is not int or data[key] <= 0: raise ValueError('Invalid '+key)
    if not 0 < data['gpu_memory_utilization'] < 1: raise ValueError('Invalid GPU allocation')
    return data
