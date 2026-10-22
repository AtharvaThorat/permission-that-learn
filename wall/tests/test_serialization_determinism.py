"""model_dump of a policy must not depend on the Python hash seed.

The experiment platform hashes the dumped preset into each job's pair_id, so an
unstable set order gave the same frozen config different identities in
different processes and broke `experiment resume` and paired comparisons.
"""
import json
import os
import subprocess
import sys

SNIPPET = (
    "import json; from ptl.wall import presets; "
    "print(json.dumps([getattr(presets, n).model_dump(mode='json') for n in "
    "('STRICT_WORKSPACE', 'WORKSPACE_RELAXED', 'READ_ONLY', 'ALLOW_ALL')], sort_keys=True))"
)


def test_model_dump_identical_across_hash_seeds():
    outputs = set()
    for seed in ("0", "1", "2", "3", "4", "5"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.add(subprocess.check_output([sys.executable, "-c", SNIPPET], env=env, text=True))
    assert len(outputs) == 1


def test_dumped_sets_are_sorted_and_round_trip():
    from ptl.wall import presets
    from ptl.wall.policy import WallPolicy

    dumped = presets.STRICT_WORKSPACE.model_dump(mode="json")
    for grant in dumped["grants"]:
        assert grant["targets"] == sorted(grant["targets"])
    assert dumped["attachments_allowed_to"] == sorted(dumped["attachments_allowed_to"])
    assert WallPolicy.model_validate(json.loads(json.dumps(dumped))) == presets.STRICT_WORKSPACE
