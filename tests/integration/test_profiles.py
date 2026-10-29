"""Profile/CLI checks do not establish real model compatibility."""
from pathlib import Path
import json
import pytest
from grids.actors.profiles import load_profile
from grids.actors.serving import command
from grids.cli.setup import main


@pytest.mark.parametrize('path', sorted(Path('configs/models').glob('*.json')))
def test_profile_builds_pinned_serving_command_and_experiment(tmp_path, path):
    p = load_profile(path)
    args = command(p, tmp_path/'snapshot', 8001)
    assert args[args.index('--tool-call-parser')+1] == p['tool_call_parser']
    assert args[args.index('--max-model-len')+1] == str(p['context_limit'])
    output = tmp_path/'run.json'
    main(['config', '--base', 'configs/experiments/smoke.json', '--profile', str(path),
          '--cache-dir', str(tmp_path/'cache'), '--output', str(output), '--clean-only'])
    actor = next(iter(json.loads(output.read_text())['actors'].values()))['settings']
    assert actor['model_revision'] == p['revision'] and actor['serving_profile'] == p
    for key, value in p.get('sampling', {}).items():
        assert actor[key] == value
