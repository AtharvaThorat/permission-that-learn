# Future setup and execution

Update: the user has since reported 68 CPU blackbox tests passing on Windows.
The original phase status below describes what was run during implementation.
For a prepared notebook workflow, use [the Colab runbook](COLAB_RUNBOOK.md).

**All installation, serving, preflight, test and benchmark commands below are for
later user execution; none were run during implementation.** Only the separate
AST/diff source checker was executed, as recorded in the implementation report.
Run Windows commands from the repository root. No automatic startup is installed.

## 1. Install dependencies later

Select a Python interpreter compatible with the retained lock and native framework.
The historical standalone Laya environment used Python 3.13.9; the combined
integration dependencies have not been resolved. Do not automatically change
historical pins if resolution fails; record the actual conflict first.

```powershell
$Python = '<ABSOLUTE_PATH_TO_SELECTED_PYTHON.exe>'
.\scripts\setup_blackbox.ps1 -Python $Python
$BBPython = (Resolve-Path '.venv-blackbox\Scripts\python.exe').Path
& $BBPython -m pip check
```

The script creates a fresh `.venv-blackbox` and installs `requirements-blackbox.txt`,
including the preserved full lock and exact inspected AgentDojo Git revision.
Alternatively, a separate fake/native-test environment can install
`requirements-blackbox-test.txt` without the Laya/Torch inference stack. Do not
install another AgentDojo fork alongside this pin.

## 2. Supply local assets and selections

Obtain actor weights/tokenizer assets yourself. Supply the exact Qwen revision,
local directory, template provenance, served name and server version. Record any
quantization explicitly. Laya retains its separate checkpoint manifest and expects
this Hugging Face cache layout, plus all required encoder/tokenizer dependencies:

```text
<LAYA_CACHE>/hub/models--convaiinnovations--laya/snapshots/7b928d828b7b0e022f929d9bd2e44165aa270148/
```

Missing assets later fail offline. The first real gate evaluation initializes and
warms up the existing persistent worker; this has not happened in this branch.

```powershell
Copy-Item configs\blackbox\wall_gatekeeper.json configs\blackbox\experiment.local.json
$ConfigPath = 'configs\blackbox\experiment.local.json'
$config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$config.actor.local_model_path = '<EXISTING_LOCAL_ACTOR_DIRECTORY>'
$config.actor.model_revision = '<EXACT_40_CHARACTER_QWEN_COMMIT>'
$config.actor.template_provenance = '<TOKENIZER_REVISION_AND_TEMPLATE_PROVENANCE>'
$config.actor.server_version = '<EXACT_SELECTED_VLLM_VERSION>'
$config.gatekeeper.cache_dir = '<EXISTING_LAYA_CACHE_DIRECTORY>'
$config.agentdojo.user_task_ids = @('<SELECTED_REAL_USER_TASK_ID>')
$config | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $ConfigPath
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:BLACKBOX_ACTOR_API_KEY = '<LOCAL_SERVER_KEY>'
```

The reader accepts the UTF-8 BOM produced by Windows PowerShell 5.1. Personal
`*.local.json` configurations are ignored. Review the reference policy: the empty
approved-recipient lists intentionally block outgoing recipients. `{}` resource
scopes impose no identity restriction; per-kind empty lists permit none. Supply
reviewed scope/labels where needed. Never derive labels from benchmark answers.

This future offline command lists real task IDs without running a task/model:

```powershell
& $BBPython -c "from agentdojo.task_suite.load_suites import get_suite; s=get_suite('v1.2.2','workspace'); print('User IDs:',list(s.user_tasks)); print('Injection IDs:',list(s.injection_tasks))"
```

Committed examples deliberately select no tasks. Empty selection never means all
tasks. V1 offers no all-task switch.

## 3. Start the actor server later

Prepare a separate Linux GPU environment using
[ACTOR_SERVER_ENVIRONMENT.md](../../configs/blackbox/ACTOR_SERVER_ENVIRONMENT.md).
After selecting/installing an exact compatible vLLM version:

```bash
export BLACKBOX_ACTOR_API_KEY='<same local server key>'
bash scripts/serve_blackbox_actor.sh /absolute/existing/Qwen3-8B Qwen3-8B '<EXACT_VLLM_VERSION>'
```

This loads a model and starts a foreground server; it is not an inspection command.
The script requires local assets, sets offline flags and uses the Hermes parser.
Each client request disables thinking via the vLLM extension. Verify parser,
template, API and `VLLM_API_KEY` behavior for the selected server version later.
No CUDA combination, memory capacity or GPU job configuration is claimed tested.
For a remote GPU host, explicitly configure an endpoint/tunnel; loopback is default.

## 4. Offline configuration inspection later

```powershell
& $BBPython -m blackbox.cli inspect-config --config $ConfigPath
& $BBPython -m blackbox.cli preflight --config $ConfigPath
```

These validate configuration/policy files, inspect installed package metadata and
local asset existence, and report missing setup. They do not initialize Laya,
probe endpoints or generate text. Exit 2 means setup items are missing. Even exit
0 reports runtime compatibility **NOT VERIFIED**. Encoder assets are not
exhaustively inspected by this preflight.

The source-only checker is separate and does not import the application:

```powershell
& $Python scripts\static_blackbox_review.py
```

It parses Python/JSON, checks the one native dispatch location and compares the
retained Laya prompts, state, manifest, and dependency pins with HEAD. Passing it
is not behavioral verification.

## 5. Run tests later, after execution is authorized

```powershell
& $BBPython -m pytest tests\blackbox -q
```

Tests use scripted actors/gates, counting runtimes, synthetic native functions,
mock HTTP transport and controlled clocks. No model initialization or endpoint
probe is needed. The tests written here are **NOT RUN**, not observed successes.

## 6. One explicitly selected clean task later

With exactly one real user-task ID configured and no attack selection:

```powershell
& $BBPython -m integrations.agentdojo.runner --config $ConfigPath --native-raw-logs
```

This performs real actor/gate inference and simulated tool execution. The explicit
flag permits AgentDojo's raw synthetic transcript/injection logging. Our default
audit uses hashes/categories. Each run gets a unique directory with manifest,
events and native scores. Earlier run directories are not overwritten. No real
email/calendar adapters are connected.

## 7. Selected attacked comparison later

Create `configs/blackbox/attack.local.json` using actual native vector IDs:

```json
{
  "<SELECTED_REAL_USER_TASK_ID>": {
    "<SELECTED_REAL_INJECTION_TASK_ID>": {
      "<REAL_NATIVE_INJECTION_VECTOR_ID>": "<EXPLICIT_SYNTHETIC_ATTACK_TEXT>"
    }
  }
}
```

This is data for native attack placement. The runner validates keys, preserves
official scoring, and does not use a ground-truth pipeline to discover candidates.
No attacker model or hidden extra objective episode is invoked.

```powershell
Copy-Item $ConfigPath configs\blackbox\attacked.local.json
$AttackedPath = 'configs\blackbox\attacked.local.json'
$attacked = Get-Content -Raw $AttackedPath | ConvertFrom-Json
$attacked.agentdojo.attack_name = 'fixed_file'
$attacked.agentdojo.injection_task_ids = @('<SELECTED_REAL_INJECTION_TASK_ID>')
$attacked.agentdojo | Add-Member -NotePropertyName attack_file -NotePropertyValue 'attack.local.json' -Force
$attacked | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $AttackedPath
& $BBPython -m integrations.agentdojo.runner --config $AttackedPath --native-raw-logs
```

Compare modes by copying the same resolved config and changing only `mode` to
`unprotected`, `wall_only`, `wall_gatekeeper`, or explicitly `wall_rules`. Keep actor
decoding, policies, budgets and task/attack selections identical. Every invocation
gets a fresh output directory. Report utility, pending episodes and infrastructure
failures alongside attack success.

Native `official_security_field` remains unchanged; attacked `attack_success`
uses verified injection-success polarity, while clean attack success is null.
Native trace checkers can count denied proposals. Our execution counters/audit
distinguish actual dispatch. False blocks and unauthorized automatic ALLOWs still
require independent action labels; do not infer them from attack success.

## Cleanup and limits

The runner context manager closes the reused HTTP client and Laya worker on errors
and exit. Stop the foreground model server with Ctrl+C. No service/job is installed.
Pending episodes do not resume; new episodes get fresh authorization state. The
in-memory ledger cannot guarantee exactly-once behavior across process crashes.
Synchronous native tools have pre/post deadline checks, not forced cancellation.
Final text remains outside the tool-permission guarantee. The experimental Laya
classifier may over-allow inside the configured wall.
