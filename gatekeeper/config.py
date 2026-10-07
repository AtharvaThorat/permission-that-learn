"""Explicit checkpoint pins shared by the API and experiment commands."""
import json
import re
from pathlib import Path


def checkpoint_config():
    return json.loads(Path(__file__).with_name('model_manifest.json').read_text(encoding='utf-8'))


def resolve_checkpoint(checkpoint=None, revision=None, profile=None):
    settings = checkpoint_config()
    if profile is not None:
        if checkpoint is not None:
            raise ValueError('Use a profile or a repository, not both')
        if profile not in ('baseline', 'typed-decisions'):
            raise ValueError('Unknown checkpoint profile')
        spec = settings[profile]
        checkpoint, revision = spec['checkpoint'], revision or spec['revision']
    else:
        checkpoint = checkpoint or settings['baseline']['checkpoint']
        if revision is None:
            matches = [settings[k] for k in ('baseline', 'typed-decisions')
                       if settings[k]['checkpoint'] == checkpoint]
            if not matches:
                raise ValueError('An unregistered checkpoint requires its own explicit revision')
            revision = matches[0]['revision']
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Revision must be an explicit 40-character commit SHA')
    return checkpoint, revision
