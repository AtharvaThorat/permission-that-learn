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
    shell = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Permissions That Learn</title><link rel="stylesheet" href="assets/research.css"></head><body><nav><a href="index.html">Permissions That Learn</a><div><a href="index.html#architecture">Architecture</a><a href="index.html#walkthrough">Walkthrough</a><a href="index.html#dataset">Dataset</a><a href="results.html">Results</a></div></nav>'
    footer = f'<footer>Permissions That Learn · Graduates Rising in Data Science at USC<br><a href="{REPO}">Code</a> · <a href="{REPO}/blob/main/CONTRIBUTING.md">Contribute</a> · Apache 2.0</footer></body></html>'
    examples = json.loads((EVIDENCE / 'dataset-preview.json').read_text())['examples']
    preview = ''.join('<details class="dataset-example"><summary>'+html.escape(r['id']+' · '+r['suite']+' · supplied '+r['source_label'])+'</summary><h3>User request</h3><p>'+html.escape(r['user_prompt'])+'</p><h3>Proposed model response</h3><pre>'+html.escape(r['model_response'])+'</pre><small>'+html.escape(r['source_id']+' · '+r['label_status'])+'</small></details>' for r in examples)
    preview += '<p><a href="results/research-release/dataset-preview.json">Preview source and review status</a></p>'
    home = (ROOT / 'scripts/templates/research-home.html').read_text(encoding='utf-8-sig').replace('@@EXAMPLES@@', preview)
    (DOCS / 'index.html').write_text(shell + home + footer, encoding='utf-8')
    latest = json.loads((EVIDENCE / 'latest-laya-check.json').read_text())
    measured = json.loads((EVIDENCE / 'latest-permission-check.json').read_text())
    latest_table = table(['Suite / case', 'Expected final', 'Raw Laya', 'Controller final', 'Dispatched', 'Latency (s)'], [[r['suite']+' / '+r['kind'],r['expected'],r['raw_decision'],r['controller_outcome']['decision'],r['controller_outcome']['executed'],number(r['elapsed_seconds'],3)] for r in latest['rows']])
    class_table = table(['Expected class','Correct final / total'],[[k,str(v['controller_correct'])+' / '+str(v['total'])] for k,v in latest['summary']['by_class'].items()])
    permission_table = table(['Strategy','Actions','Questions','Saved','Forbidden','Errors','Permission time (s)'],[[k,v['actions'],v['questions'],v['questions_saved'],v['forbidden_dispatches'],v['errors'],number(v['permission_seconds'],3)] for k,v in measured['summary'].items()])
    intro = f'<header><p class="eyebrow">RESEARCH EVIDENCE</p><h1>Permission behavior.<br><em>Quality, safety and cost.</em></h1><p>Constructed enforcement checks, real inference, and exploratory model comparisons.</p></header><main><section id="latest"><h2>Latest local verification</h2><h3>1. Automated permission-learning check</h3><p>Run {measured["run_id"]}: 36 constructed sequences, 504 actions per arm. The Wall/controller/store are real; tools and Gatekeeper decisions are fixtures. Runtime {number(measured["runtime"]["elapsed_seconds"])} s; process CPU {number(measured["runtime"]["cpu_seconds"])} s. Peak memory was unavailable.</p>{permission_table}<p>All 36 holdout expectations passed per arm. Grants saved 29/168 questions (17.3%); learning saved 9/168 (5.4%). The learner did not outperform grants alone. These repeated steps are not 504 independent scenarios.</p><a href="results/research-release/latest-permission-check.json">Full summary and source hash</a><h3>2. Real base-Laya CPU smoke</h3><p>Run {latest["run_id"]}: 12/12 supported, zero errors. Final controller agreement: 10/12 (83.3%). Raw intent agreement: 10/12 against a different target. Three confirmation cases have raw ALLOW but final ASK. Two optional ASK cases became BLOCK. The 512-token checkpoint limit includes question overhead; these short cases do not validate arbitrary long contexts.</p>{class_table}{latest_table}<p>CPU, four threads, Python {latest["python"]}, {latest["platform"]}. Initialization {number(latest["initialization_seconds"])} s. Checkpoint {latest["checkpoint"]}@{latest["revision"]}. Per-input latency excludes initialization. No new inference was run to create this page.</p><p><a href="results/research-release/latest-laya-check.csv">Per-example CSV</a> · <a href="results/research-release/latest-laya-check.json">Inputs, probabilities, context limits and diagnostics</a></p></section><section><h2>How to read the comparisons</h2><p>Baseline uses the existing decision question. Rotated averages probabilities across three option orders; that is three presentations for one prediction. Concise shortens the instructions. Decomposed separates task relation from authorization details. Each screening cohort has 30 examples, ten per supplied class; full runs have 150.</p><p>Accuracy means correct predictions divided by scored examples. Coverage and failures must be read alongside it. False approvals predict ALLOW for supplied ASK/BLOCK labels. Historical timings have different pass counts: timing repetitions never increase accuracy sample size. Configuration selection reused these examples, so results are exploratory and require fresh human-reviewed evaluation.</p></section>'
    results = f'''<section id="results"><p class="eyebrow">03 / RECORDED EVIDENCE</p><h2>Authorization quality and cost.</h2><p>All screening configurations are included below. Configuration selection reused evaluated examples; improvements are exploratory. Accuracy here means agreement with supplied labels. Timing repetitions do not increase the number of independent samples.</p><h3>Selected and historical full-cohort comparisons</h3><div class="bars">{bars}</div><p class="note">All bars use a 0–100% agreement scale. Higher agreement alone does not establish safety: Cybersec rotated agrees on 70/150 but falsely approves 52 supplied ASK/BLOCK examples. The historical Cybersec baseline falsely approves 38. These configurations should not be promoted on agreement alone.</p><details open><summary>Complete configuration and compute table</summary>{ctable}</details><p><a href="results/research-release/laya-comparison.csv">Download comparison CSV</a> · <a href="results/research-release/provenance.json">Source provenance</a></p>
<h3>Scoped-permission enforcement</h3>{ptable}<p>36 constructed sequences per strategy, across three suites. The 504 steps include repeated learning interactions. Zero forbidden dispatches in these fixtures does not establish universal safety. Explicit grants saved more questions than the contextual learner in this run.</p><h3>Real-model smoke evidence</h3><p>Pinned base Laya completed 12/12 CPU inputs; final controller decisions matched 10/12 constructed expectations. Three mandatory-confirmation cases withheld dispatch despite raw Laya ALLOW. A separate 21-input Cybersec smoke completed without errors (8 ALLOW, 13 BLOCK, 0 ASK). These are functionality checks.</p><details><summary>All available local compute summaries ({len(local)} runs)</summary><p>Includes repeated runs and failures; do not pool these as independent samples or compare timings across different pass counts. Missing values remain unavailable.</p>{ltable}</details><p><a href="results/research-release/local-runs.json">Download local-run catalog</a> · <a href="results/research-release/permission-summary.json">Permission metrics</a> · <a href="results/research-release/laya-smoke-summary.json">Base Laya smoke</a></p></section>
<section id="reproduce"><p class="eyebrow">04 / REPRODUCIBILITY</p><h2>Run the shared pipeline.</h2><p>The demo benchmark calls the existing controller and evaluation components. Its default mode uses constructed Gatekeeper fixtures and simulated tools. Activate the documented environment first.</p><pre>python scripts/benchmark.py --output results/demo-01
# In the Laya environment, with cached weights:
python scripts/benchmark.py --output results/demo-laya-01 --real-laya --cache workspace/cache</pre><p>Open the generated <code>report.html</code> for action-level evidence. Output paths must be new. <a href="{REPO}/blob/main/docs/guides/reproduce.md">Reproduction guide ↗</a></p><p>The plugin is under separate development. This page does not claim a hosted interactive plugin demo. <a href="{REPO}/tree/main/plugin">Plugin source ↗</a></p></section>
<section><p class="eyebrow">05 / LIMITATIONS & NEXT STEPS</p><h2>Evidence before claims.</h2><p>Independent human review, Laya weight fine-tuning, calibration and checkpoint-promotion gates remain open. Historical sweep source is absent from this checkout; saved outputs are preserved with provenance. CPU checks do not establish GPU compatibility, real-user effectiveness or native full-benchmark performance. The manuscript and released measurements require author review before submission.</p></section>'''
    (DOCS / 'results.html').write_text(shell + intro + results + '</main>' + footer, encoding='utf-8')
    (DOCS / '.nojekyll').touch()
    print('Built homepage and results page from committed evidence; no inference performed.')


if __name__ == '__main__':
    build()
