# Test catalog

Tests exercise behaviors and security boundaries, not model quality. CPU tests
block model loading/downloads through `tests/conftest.py`.

`tests/unit/core/test_scoped_permissions.py` covers persistent exact scopes, user isolation,
mandatory asks and Wall/Laya denial, malformed probabilities, expiry during final audit,
revocation/dispatch serialization, atomic use limits, replay/restart rejection, storage/audit
failure, reviewed feedback/consent, learner reproducibility, frozen state, and report regeneration.
The constructed `grids permissions check` sequences use the production Wall/controller with
simulated tools. `--real-laya` separately evaluates 12 inputs using the pinned local CPU model;
it is never part of the model-free test suite. On 2026-11-11: 362 CPU tests and Ruff passed.

| Location | Essential coverage |
|---|---|
| `tests/unit/core` | Parsing, exact binding, ALLOW/BLOCK/ASK, stale/replayed approvals, bounded execution, context limits, snapshot layout and initialization errors, actor transport, Laya training data (published files, exact and reproducible model input, attacker identities, review selection), compact_v1 input (verbatim request/action, trust classes, injection evidence, fail-closed preflight, published compact data), approval memory (judgment asks only, no Wall-DENY contact, bound answers, pattern scope, counting and bandit learners, runtime wrapper, deterministic simulator and its invariants), permission grants (approvals never authorize alone, grant scope, revocation and expiry, controller path, live decision order, published labels and Laya predictions, rotated Laya options with label averaging, tie to ASK and fail-closed validation of every answer and truncation diagnostic) |
| `tests/unit/wall` | Policy/context normalization, unknown identities/resources, determinism and property-based invariants |
| `tests/integration/test_platform.py` | Planning identities, all live modes with native fixtures, scheduler caps, claims, stateful capture and attempt aggregation |
| `tests/integration/test_authorization.py` | Same-input comparators, no actor/tool replay, independent label identities, corruption, missing metrics and model-error exclusion |
| Other `tests/integration` files | Three-suite discovery/mapping, approvals, context diagnostics, live reporting, native attacks, setup and seven model profile commands |
| `tests/fixtures` | Synthetic runtime configurations and isolated reference-Wall test double; never production fallback |

```bash
python -m ruff check src tests
python -m pytest tests/integration/test_authorization.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
git diff --check
```

The single GitHub workflow runs lint and CPU tests on Python 3.12. It does not
download weights or claim real-model compatibility. Retired wrapper/report tests
and frozen experiment-layout assertions were removed along with their obsolete
entry points; enforcement and meaningful failure tests remain.

Real inference is a separate opt-in layer: `grids validate laya`, `grids validate
actor --multi-turn`, then small native episodes. Follow [setup](../guides/setup.md),
inspect artifacts, and record the actual hardware/pins/outcome in a milestone.
No mocked prediction may be presented as real Laya or actor evidence.

Teammate integration adds 9 tests in `test_permission_learning.py`: contextual estimation, per-user/policy isolation, deterministic synthetic splits and file hashes, Wall invariants, guarded grants, prediction-cache reuse, preserved raw outputs and duplicate rejection. Free/pooled policies are offline controls only.
