"""Rebuild the static paper page from committed, aggregate research evidence."""
from pathlib import Path
import csv
import html
import json

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
EVIDENCE = DOCS / 'results/research-release'
REPO = 'https://github.com/AtharvaThorat/permission-that-learn'
DATASET = 'https://huggingface.co/datasets/siddharth-magesh/grids-laya-permission-v1'


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{html.escape("—" if v is None else str(v))}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def number(value, precision=2):
    return '—' if value is None or value == '' else f'{float(value):.{precision}f}'


def build():
    comparisons = list(csv.DictReader((EVIDENCE / 'laya-comparison.csv').open(encoding='utf-8-sig')))
    permissions = json.loads((EVIDENCE / 'permission-summary.json').read_text())
    local = json.loads((EVIDENCE / 'local-runs.json').read_text())['runs']
    ptable = table(['Strategy', 'Actions', 'Questions', 'Questions saved', 'Forbidden dispatches'],
                   [[k, v['actions'], v['questions'], v['questions_saved'], v['forbidden_dispatches']] for k, v in permissions.items()])
    ctable = table(['Cohort', 'Model / variant', 'Correct / total', 'Agreement', 'False approvals', 'Median / p95 (s)', 'CPU (s)', 'Peak RAM (MiB)'],
                   [[r['phase'], r['model_key']+' / '+r['variant'], r['correct']+'/'+r['examples'], number(float(r['accuracy'])*100)+'%', r['false_approvals'], number(r['median_s'])+' / '+number(r['p95_s']), number(r['cpu_s']), number(r['peak_ram_mib'],0)] for r in comparisons])
    ltable = table(['Recorded run', 'Status', 'Correct / scored', 'Agreement', 'Timed calls', 'Failed calls', 'Median (s)', 'CPU (s)'],
                   [[r['run'], r.get('status'), number(r.get('correct_vs_source_label'), 0)+' / '+number(r.get('scored_examples'), 0), '—' if r.get('accuracy') is None else number(r['accuracy']*100)+'%', r.get('timed_calls'), r.get('failed_calls'), number(r.get('median_success_latency_s')), number(r.get('process_cpu_seconds'))] for r in local])
    bars = ''.join(f'<div class="barrow"><span>{html.escape(r["model_key"]+" / "+r["variant"])}</span><div class="track"><div style="width:{float(r["accuracy"])*100:.2f}%"></div></div><b>{r["correct"]}/{r["examples"]}</b></div>' for r in comparisons if r['phase'] != 'screen')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Permissions That Learn — Policy-Bounded Authorization</title><meta name="description" content="Research on a shared Wall, Laya and scoped permission-learning pipeline for tool-using agents."><link rel="stylesheet" href="assets/research.css"></head>
<body><nav><a href="#">Permissions That Learn</a><div><a href="#architecture">Architecture</a><a href="#dataset">Dataset</a><a href="#results">Results</a><a href="#reproduce">Reproduce</a></div></nav>
<header><p class="eyebrow">A RESEARCH PROJECT · UNIVERSITY OF SOUTHERN CALIFORNIA</p><h1>Policy-Bounded Authorization<br>and Approval Learning<br><em>for Tool-Using LLM Agents</em></h1>
<p class="authors"><a href="https://github.com/Siddharth-magesh">Siddharth Magesh</a> · <a href="https://github.com/AtharvaThorat">Atharva Thorat</a> · <a href="https://github.com/kaustubhadhe1206">Kaustubh Adhe</a></p>
<p>Graduates Rising in Data Science · USC</p><div class="buttons"><a href="{REPO}/blob/main/paper/manuscript.pdf">Read the paper ↗</a><a href="{REPO}">Code ↗</a><a href="{DATASET}">Dataset ↗</a><a href="#results">Explore results ↓</a></div><small>Research manuscript · Experimental implementation · Apache 2.0 code</small></header>
<main><section class="abstract"><p class="eyebrow">ABSTRACT</p><p>Tool access does not imply authority to perform every action. We study an external authorization pipeline that separates fixed permission enforcement, contextual action judgment, and adaptation from user feedback. A deterministic Wall constrains tool capabilities and verified resources; Laya evaluates the authentic request and proposed action; explicit scoped grants bound when a per-user learner may avoid an optional confirmation. The controller rechecks exact action identity and current authorization before execution.</p><p>Our experiments examine authorization agreement, permission creep, interruptions and computational cost. The results below distinguish constructed security checks, provisional-label model comparisons and real inference smoke tests.</p></section>
<section id="architecture"><p class="eyebrow">01 / THE CORE CONTRIBUTION</p><h2>One authorization pipeline.</h2><p>The same enforcement path serves Workspace, Slack and Banking. Actors propose; trusted state supplies evidence; authorization precedes dispatch. Application adapters and the separately developed plugin sit around this core.</p><div class="flow"><span>Actor proposal</span><i>→</i><span>Exact action binding</span><i>→</i><span>Deterministic Wall</span><i>→</i><span>Laya: ALLOW / ASK / BLOCK</span><i>→</i><span>Approval / valid grant</span><i>→</i><span>Recheck & dispatch</span></div><p class="note">Wall denials, mandatory confirmations, missing evidence, model errors and Laya BLOCK cannot be overridden by learning. Approval of one action never creates a reusable grant.</p><details><summary>Full architecture diagram</summary><img class="diagram" src="architecture/system/pipeline.png" alt="Controller, Wall, Gatekeeper, approval and AgentDojo evaluation architecture"></details>
<div class="cards"><article><h3>Fixed boundary</h3><p>Capabilities, recipients, resources, policy and state are checked independently of the acting model.</p><code>src/grids/wall/</code></article><article><h3>Contextual judgment</h3><p>Preserve authentic intent and exact action evidence. Oversized or incomplete contexts produce classified conservative outcomes.</p><code>src/grids/gatekeeper/</code></article><article><h3>Bounded adaptation</h3><p>Persistent per-user grants, expiry, revocation, use reservations and reviewed feedback constrain learning.</p><code>src/grids/core/permissions/</code></article></div></section>
<section id="dataset"><p class="eyebrow">02 / THE EVALUATION MATERIAL</p><h2>Prompt–action pairs for Laya.</h2><p>Our <a href="{DATASET}">grids-laya-permission-v1 dataset</a> contains a 150-pair compact release: user requests and proposed model/tool responses with ALLOW, ASK and BLOCK reference labels (50 each). Workspace, Slack and Banking are represented. Access is gated on Hugging Face.</p><p>Reference revision: <code>9659e4519fb3c9d96f899c777dfc55bdf299d563</code>. These curated, constructed examples use provisional labels. They are not an independently human-reviewed authorization benchmark. New actor proposals need new labels. Earlier 300/150 training/test material is retained separately as reference data.</p></section>
<section id="results"><p class="eyebrow">03 / RECORDED EVIDENCE</p><h2>Authorization quality and cost.</h2><p>All screening configurations are included below. Configuration selection reused evaluated examples; improvements are exploratory. Accuracy here means agreement with supplied labels. Timing repetitions do not increase the number of independent samples.</p><h3>Selected and historical full-cohort comparisons</h3><div class="bars">{bars}</div><p class="note">All bars use a 0–100% agreement scale. Higher agreement alone does not establish safety: Cybersec rotated agrees on 70/150 but falsely approves 52 supplied ASK/BLOCK examples. The historical Cybersec baseline falsely approves 38. These configurations should not be promoted on agreement alone.</p><details open><summary>Complete configuration and compute table</summary>{ctable}</details><p><a href="results/research-release/laya-comparison.csv">Download comparison CSV</a> · <a href="results/research-release/provenance.json">Source provenance</a></p>
<h3>Scoped-permission enforcement</h3>{ptable}<p>36 constructed sequences per strategy, across three suites. The 504 steps include repeated learning interactions. Zero forbidden dispatches in these fixtures does not establish universal safety. Explicit grants saved more questions than the contextual learner in this run.</p><h3>Real-model smoke evidence</h3><p>Pinned base Laya completed 12/12 CPU inputs; final controller decisions matched 10/12 constructed expectations. Three mandatory-confirmation cases withheld dispatch despite raw Laya ALLOW. A separate 21-input Cybersec smoke completed without errors (8 ALLOW, 13 BLOCK, 0 ASK). These are functionality checks.</p><details><summary>All available local compute summaries ({len(local)} runs)</summary><p>Includes repeated runs and failures; do not pool these as independent samples or compare timings across different pass counts. Missing values remain unavailable.</p>{ltable}</details><p><a href="results/research-release/local-runs.json">Download local-run catalog</a> · <a href="results/research-release/permission-summary.json">Permission metrics</a> · <a href="results/research-release/laya-smoke-summary.json">Base Laya smoke</a></p></section>
<section id="reproduce"><p class="eyebrow">04 / REPRODUCIBILITY</p><h2>Run the shared pipeline.</h2><p>The demo benchmark calls the existing controller and evaluation components. Its default mode uses constructed Gatekeeper fixtures and simulated tools. Activate the documented environment first.</p><pre>python scripts/benchmark.py --output results/demo-01
# In the Laya environment, with cached weights:
python scripts/benchmark.py --output results/demo-laya-01 --real-laya --cache workspace/cache</pre><p>Open the generated <code>report.html</code> for action-level evidence. Output paths must be new. <a href="{REPO}/blob/main/docs/guides/reproduce.md">Reproduction guide ↗</a></p><p>The plugin is under separate development. This page does not claim a hosted interactive plugin demo. <a href="{REPO}/tree/main/plugin">Plugin source ↗</a></p></section>
<section><p class="eyebrow">05 / LIMITATIONS & NEXT STEPS</p><h2>Evidence before claims.</h2><p>Independent human review, Laya weight fine-tuning, calibration and checkpoint-promotion gates remain open. Historical sweep source is absent from this checkout; saved outputs are preserved with provenance. CPU checks do not establish GPU compatibility, real-user effectiveness or native full-benchmark performance. The manuscript and released measurements require author review before submission.</p></section></main>
<footer>Permissions That Learn · Graduates Rising in Data Science at USC<br><a href="{REPO}/blob/main/CONTRIBUTING.md">Contribute</a> · <a href="{REPO}/blob/main/LICENSE">Apache 2.0</a> · <a href="{REPO}/blob/main/docs/README.md">Documentation</a></footer></body></html>'''
    (DOCS / 'index.html').write_text(page, encoding='utf-8')
    (DOCS / '.nojekyll').touch()
    print('Built docs/index.html from committed evidence; no inference performed.')


if __name__ == '__main__':
    build()
