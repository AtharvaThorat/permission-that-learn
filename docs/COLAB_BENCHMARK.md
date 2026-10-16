# Quick Qwen actor + original Laya benchmark

For explicit attacked runs and clean comparisons, use [COLAB_INJECTION_RUN.md](COLAB_INJECTION_RUN.md).
The default command below continues to run clean tasks only.

Use `scripts/benchmark_colab.py` for a small, end-to-end clean AgentDojo pilot.
It uses the existing pipeline, original Laya checkpoint/single-question policy,
native AgentDojo task scoring, and unchanged reference wall. Qwen3-8B is the actor;
Laya is the gatekeeper. No training or model substitution is performed.

The default panel contains `user_task_0`, `user_task_1`, `user_task_2`,
`user_task_3`, and `user_task_10`: five calendar-read tasks already selected in
the supplied notebook. This is intentionally a narrow pilot, not a full workspace
benchmark and not an injection-security evaluation. No success numbers are
provided until the real run produces them.

## What was learned from Untitled0.ipynb

- Colab supplied Python 3.13.15. Installing Python 3.12 with uv worked; use the
  explicit `/content/py312/bin/python` for every project command.
- vLLM 0.11.0 failed with Transformers 5.20.0 (`all_special_tokens_extended`).
  The notebook's working actor environment used Transformers 4.57.6. That exact
  version is now installed by prepare and repair-actor; the gate environment is
  separate and is not downgraded.
- Extracting a GitHub ZIP lost `.git`, breaking run provenance. Clone the actual
  branch; do not create a synthetic Git commit in an extracted archive.
- The notebook recorded 75 CPU tests passing, successful model preparation, and
  successful actor startup after the pin correction. Its final user_task_0 score
  was **official_utility=false, infrastructure_error, zero tool calls and zero
  evaluated actions**. It does not demonstrate gatekeeper accuracy or usefulness.
  The notebook does not include that run's error event/HTTP response, so its exact
  task-time failure cannot be diagnosed from the supplied output alone.
- The unexecuted batch-loop cells are not used. They would restart the actor for
  every task. This script shares one server and one Laya worker across the panel.

The original notebook is left untouched. A clean executable notebook is provided
at `notebooks/colab_quick_benchmark.ipynb`; the same commands are below.

## Calendar input fix and rerun

Run `20261016T080941Z-05e7eb40` loaded both models, but all five task responses
from Laya were rejected with `error_kind=truncation`. Calendar collection reads
were passing every event's metadata and content hash into the semantic model.
The adapter now sends a compact collection scope/count for calendar, email and
drive collection read tools.
The authentic request, exact tool arguments, effects, missing-evidence markers,
and confirmation requirement are retained. Full event metadata still feeds the
wall and execution freshness checks. Other tools retain their existing inputs.
The original Laya checkpoint, questions, token limits, and response validation
are unchanged; long requests can still fail closed.

Gate events now include numeric token/truncation diagnostics. Reports distinguish
raw returned predictions from usable accepted predictions and use
`completed_with_gate_errors` when model responses are rejected. The historical
JSON field `laya_predictions_returned` continues to count usable predictions.
Local verification: 89 CPU tests passed; a new Colab model run is still required.

After pushing the fix, reuse the prepared Colab session:

```python
%cd /content/permission-that-learn-benchmark
!git pull --ff-only origin feature/agentdojo-blackbox
!/content/py312/bin/python scripts/benchmark_colab.py run --seconds 900 --task-seconds 150 --native-raw-logs
```

Verify the pull succeeded before running the benchmark. No dependency repair or
model download is needed if the same VM still has its prepared assets. Download
the new ZIP using section 5. Check `gate_error_counts`, usable predictions, task
scores and tool executions. A valid semantic ASK/BLOCK remains a legitimate
outcome; the fix does not force permission or promise all tasks succeed.

## 1. Push, then clone on a GPU runtime

Review and push the local changes on `feature/agentdojo-blackbox` first. In Colab
choose Runtime > Change runtime type > T4 GPU (or better). Use a fresh real checkout
so the source revision in the report matches the GitHub branch:

```python
!git clone --branch feature/agentdojo-blackbox --single-branch https://github.com/AtharvaThorat/permission-that-learn-.git /content/permission-that-learn-benchmark
%cd /content/permission-that-learn-benchmark
```

For a private repository, authenticate before cloning. Never put a token in shared
notebook source. If this exact destination already contains a clone, update that
checkout deliberately instead of cloning over it or reinitializing Git.

## 2. Install the same Python used successfully in the supplied notebook

```python
!pip -q install uv
!uv python install 3.12
!uv venv --seed --python 3.12 /content/py312
!/content/py312/bin/python --version
```

On the existing live runtime, keep `/content/py312` if it already works; do not
recreate it. Changing the notebook kernel is unnecessary because commands use
explicit interpreter paths.

## 3. Prepare once, or repair an existing prepared runtime

For a fresh Colab session:

```python
!/content/py312/bin/python scripts/colab_blackbox.py prepare
```

For the still-running session from Untitled0.ipynb, with assets and environments
already under `/content/blackbox-colab`, run this instead:

```python
!/content/py312/bin/python scripts/colab_blackbox.py repair-actor
```

Prepare runs the CPU tests, installs both environments, downloads models and
checks offline Laya loading. Repair only fixes/records the actor dependencies;
it does not redownload weights. Stop on installation errors. Preparation time
and downloads are separate from the short benchmark budget.

## 4. Run the pilot

```python
!/content/py312/bin/python scripts/benchmark_colab.py run --seconds 900 --task-seconds 150 --native-raw-logs
```

The 900-second deadline includes package checks, server startup, a synthetic
tool-call probe, Laya warmup, and the five tasks. Shutdown/report ZIP creation
can add a few seconds. It may finish earlier; a slow startup or task can leave a
partial panel. The script does not promise that all five tasks finish in 15 minutes.
The task deadline is cooperative; the parent enforces the total budget by stopping
its own subprocess groups. Downloads and dependency installation are not included.

The synthetic probe executes no tool and contributes no task score. The original
Laya backend warmup also contributes no score. Tasks run with temperature 0,
512 output tokens, six actor turns, twelve tool attempts, and the existing 8K
server context. Long outputs/context can fail explicitly; there is no silent
truncation or policy relaxation to improve scores.

To select a different explicit panel, append `--tasks user_task_0 user_task_1 ...`.
Changing the task set changes the evaluation; record that choice when comparing.
The default five-task panel is preferable for reproducing this pilot.

## 5. View and download the result for presentation

```python
import json
from pathlib import Path
from IPython.display import Markdown, display
from google.colab import files

latest = json.loads(Path('/content/blackbox-colab/latest-benchmark.json').read_text())
result_dir = Path(latest['directory'])
display(Markdown((result_dir / 'REPORT.md').read_text()))
files.download(latest['archive'])
```

Every run gets its own timestamped directory under `/content/blackbox-colab/benchmarks/`.
The ZIP contains `REPORT.md`, `summary.csv`, `summary.json`, actual scores/events,
native synthetic transcripts, the manifest/config, resolved package inventories,
startup logs and warmup/probe results. An interrupted last JSONL write is ignored;
no replacement score is invented. Incomplete active-task tool counters are unknown.

Use REPORT.md as the presentation summary. Official task utility, pending approvals,
infrastructure failures, and unstarted/interrupted tasks are shown separately.
Laya predictions are counted from actual gate events, excluding warmup. Zero
predictions is explicitly reported as no task-level gatekeeper evidence. The
unchanged clean-task `official_security_field=true` is not called attack resistance.
The report does not infer gatekeeper classification accuracy from task utility.

Exit 0 means the panel finished without infrastructure or gate errors; task utility can
still be false. Exit 1 means infrastructure or gate errors occurred. Exit 2 indicates
setup/worker failure, interruption, or deadline expiry. A report is still exported
for failures after the trial starts. Check `failure.json`, `worker.log`, and
`actor-server.log` for diagnostics. Safe error chains include exception classes
and HTTP status codes without copying credentials or response bodies into the
summary. If the Colab VM itself is reclaimed, no local process can guarantee export;
copy completed evidence to Drive/download it before ending the runtime.
