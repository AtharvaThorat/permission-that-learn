# Reproduce the research pipeline

Use Python 3.12 in an editable checkout. Commands below use `python` from the selected environment.
For model dependencies, offline caches, Colab and CARC see [setup](setup.md) and [CARC](carc.md).

```bash
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r environments/cpu.txt
python -m grids permissions check --output results/reproduction/permissions-01
```

Open `results/reproduction/permissions-01/report.html`. This runs 36 constructed sequences through
the real Wall, controller, exact-grant store and simulated tools. Gatekeeper outputs in this
command are fixtures. CSV, JSONL, SQLite and summary artifacts describe each outcome.
Use a fresh output directory for each attempt.

For real Laya, activate the Laya environment documented in setup and supply a populated cache:

```bash
python -m grids permissions check --output results/reproduction/laya-01 --real-laya --cache workspace/cache
python -m grids permissions report --run-dir results/reproduction/laya-01
```

The opt-in check uses 12 real base-Laya CPU inputs. Report regeneration makes no inference calls.
The [permission guide](experiments.md#scoped-permission-learning-local-research) documents grant
issuance, rejection, revocation, reviewed feedback and the existing operator approval channel.
The [offline learning commands](experiments.md#offline-contextual-policy-comparisons) reproduce
the teammate-derived synthetic Workspace studies with cached real model predictions.

Native AgentDojo execution uses the existing CLI:

```bash
python -m grids benchmark discover
python -m grids benchmark plan --config configs/experiments/smoke.json
```

Serving, execution, collection, identical-action replay and independent-label import are described
in [experiments](experiments.md). Planning does not launch servers or allocate a GPU.

## Reading released evidence

Download/open `docs/results/research-release/report.html` locally. GitHub displays its source;
the adjacent Markdown summary and CSV are readable directly on GitHub. The complete comparison
CSV includes every saved screening variant, errors and the selected full-cohort runs.
Historical question-search source modules are absent from this checkout; these comparisons are
preserved observations, not a claim that their full sweep can currently be regenerated. The
supported prediction and permission-check paths above remain executable.

## Release checks

```bash
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
```

Retained tests protect authorization and reproducibility. They do not measure model quality.
No full benchmark, GPU job or new model training is part of the publication cleanup.
