# Test catalog

Tests exercise behaviors and security boundaries, not model quality. CPU tests
block model loading/downloads through `tests/conftest.py`.

| Location | Essential coverage |
|---|---|
| `tests/unit/core` | Parsing, exact binding, ALLOW/BLOCK/ASK, stale/replayed approvals, bounded execution, context limits, snapshot layout and initialization errors, actor transport |
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
