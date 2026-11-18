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
    ms = measured['summary']
    def question_reduction(strategy):
        saved = ms[strategy]['questions_saved']
        baseline = ms['off']['questions']
        return f'{saved / baseline * 100:.1f}%'
    def per_action_ms(strategy):
        return ms[strategy]['permission_seconds'] * 1000 / ms[strategy]['actions']
    real_ask = {}
    real_ask_path = ROOT / 'results/real-ask-learning-cybersec-20261112/summary.json'
    if real_ask_path.exists():
        real_ask = json.loads(real_ask_path.read_text())
    intro = f'''<header><p class="eyebrow">RESEARCH EVIDENCE</p><h1>Permission behavior.<br><em>Learning, efficiency and scope.</em></h1><p>A concise view of measured permission learning, enforcement, and CPU cost.</p></header><main>
<section id="latest"><p class="eyebrow">01 / CORE RESULT</p><h2>Small learning loop, measurable question reduction.</h2>
<div class="kpis">
  <article><strong>504</strong><span>permission actions per arm</span></article>
  <article><strong>29</strong><span>questions avoided by explicit grants</span></article>
  <article><strong>9</strong><span>questions avoided by active learning</span></article>
  <article><strong>0</strong><span>forbidden dispatches</span></article>
</div>
<p class="result-lead">Across 36 constructed sequences, explicit grants removed <b>17.3%</b> of repeated questions, while contextual learning removed <b>5.4%</b>. Every arm preserved the 36 holdout ALLOW/ASK/BLOCK expectations. The active learner is therefore a credible reduction mechanism, but it did not outperform explicit grants in this test.</p>
<h3>How the strategies compare</h3>{permission_table}
<div class="comparison-grid">
  <article><h3>Explicit grants</h3><p><b>139 questions</b> from a 168-question baseline</p><p><b>{question_reduction("grants")}</b> question reduction</p><p>197 tool dispatches and zero forbidden dispatches</p></article>
  <article><h3>Active learning</h3><p><b>159 questions</b> from a 168-question baseline</p><p><b>{question_reduction("active")}</b> question reduction</p><p>177 tool dispatches and zero forbidden dispatches</p></article>
  <article><h3>Protection unchanged</h3><p>All 36 holdout expectations passed in each arm</p><p>12 ALLOW, 12 ASK and 12 BLOCK cases remained correct</p><p>No forbidden dispatches in the constructed run</p></article>
</div>
<p class="note"><b>Read carefully:</b> 504 actions are repeated steps from 36 sequences, not 504 independent scenarios. This demonstrates controller and memory behavior; it is not live-user or real-agent utility evidence.</p>
<p><a href="results/research-release/latest-permission-check.json">Full summary and source hash</a></p>
</section>
<section><p class="eyebrow">02 / COMPUTATIONAL COST</p><h2>Permission overhead remains small.</h2>
<div class="kpis kpis-four">
  <article><strong>{number(ms["off"]["permission_seconds"],3)} s</strong><span>no-memory permission time</span></article>
  <article><strong>{number(ms["grants"]["permission_seconds"],3)} s</strong><span>explicit-grant time</span></article>
  <article><strong>{number(ms["active"]["permission_seconds"],3)} s</strong><span>active-learning time</span></article>
  <article><strong>{number(measured["runtime"]["elapsed_seconds"],2)} s</strong><span>complete local demo</span></article>
</div>
<div class="comparison-grid">
  <article><h3>No memory</h3><p>{per_action_ms("off"):.3f} ms average permission time per action</p></article>
  <article><h3>Explicit grants</h3><p>{per_action_ms("grants"):.3f} ms average permission time per action</p></article>
  <article><h3>Active learning</h3><p>{per_action_ms("active"):.3f} ms average permission time per action</p></article>
</div>
<p>The complete local run used {number(measured["runtime"]["cpu_seconds"],2)} process CPU seconds. Peak memory was unavailable. These are lightweight CPU measurements of permission logic and in-process stores, not GPU serving or LLM inference benchmarks.</p>
<p class="note"><b>PPT-safe framing:</b> “The full 504-action demo completed in a 4.57-second local process, with sub-millisecond permission decisions and no forbidden dispatches.” Do not describe it as faster wall-clock inference or a universal cost reduction.</p>
</section>
<section><p class="eyebrow">03 / LEARNING BEHAVIOR</p><h2>Learning is scoped, reviewable and revocable.</h2>
<div class="state-flow">
  <div><b>1</b><span>Observe</span><small>same task, effect and scope</small></div><i>→</i>
  <div><b>2</b><span>Learn</span><small>update only eligible permissions</small></div><i>→</i>
  <div><b>3</b><span>Reuse</span><small>skip eligible repeated prompts</small></div><i>→</i>
  <div><b>4</b><span>Invalidate</span><small>changed scope, policy or explicit revoke</small></div>
</div>
<div class="comparison-grid">
  <article><h3>Constructed learning run</h3><p>504 actions across 36 sequences</p><p>9 fewer questions than no-memory mode</p><p>Zero forbidden dispatches</p></article>
  <article><h3>Cybersec ASK check</h3><p>{real_ask.get("actions","—")} ASK actions</p><p>{real_ask.get("explicit_approvals","—")} explicit approvals</p><p>{real_ask.get("grant_reuse_dispatches","—")} grant-reuse dispatches</p></article>
  <article><h3>Safety check</h3><p>{real_ask.get("revocation_withheld","—")} revocation-withheld actions</p><p>{real_ask.get("errors","—")} recorded errors</p><p>Synthetic ASKs; not real-user evidence</p></article>
</div>
</section>
<section><p class="eyebrow">04 / COMPATIBILITY CHECK</p><h2>One compact CPU check.</h2>
<p>Run {latest["run_id"]}: 12/12 supported inputs completed with zero recorded errors. The controller reached 10/12 final constructed outcomes. This is included as an implementation and compatibility check, not as the main learning result.</p>
{class_table}{latest_table}
<p><a href="results/research-release/latest-laya-check.csv">Per-example CSV</a> · <a href="results/research-release/latest-laya-check.json">Diagnostics and context limits</a></p>
</section>
<section><p class="eyebrow">05 / ARCHIVE</p><h2>Detailed evidence remains available.</h2>
<p><a href="https://github.com/AtharvaThorat/permission-that-learn/tree/main/docs/results/permission-experiments">Experiment archive</a> · <a href="results/research-release/laya-comparison.csv">Historical authorization comparison CSV</a> · <a href="results/research-release/local-runs.json">Local run catalog</a></p>
<details><summary>How to read historical comparisons</summary><p>Some Laya configurations used multiple presentations or repeated timing runs. Accuracy is agreement with supplied labels, not established real-world safety. Full historical detail is available for reviewer traceability, but it is not the headline learning result.</p></details>
<details><summary>Selected full-cohort Laya values</summary><div class="bars">{bars}</div><p class="note">Higher label agreement alone does not establish safety. These archived sweeps are exploratory and should not be promoted from accuracy alone.</p><details open><summary>Configuration and compute table</summary>{ctable}</details></details>
</section>
<section id="reproduce"><p class="eyebrow">06 / REPRODUCIBILITY</p><h2>Reproduce the learning demo.</h2>
<pre>python scripts/benchmark.py --output results/demo-01
python scripts/benchmark.py --output results/demo-pages-02</pre>
<p><a href="https://github.com/AtharvaThorat/permission-that-learn/blob/main/docs/guides/reproduce.md">Reproduction guide ↗</a> · <a href="https://github.com/AtharvaThorat/permission-that-learn/tree/main/plugin">Plugin source ↗</a></p>
</section>
<section><p class="eyebrow">07 / LIMITATIONS</p><h2>What this evidence does—and does not—show.</h2>
<div class="limitation-grid">
<article><h3>Shown</h3><p>Scoped grant and contextual-learning behavior, holdout consistency, question reduction, revocation, and bounded CPU overhead in a deterministic construction.</p></article>
<article><h3>Not shown</h3><p>Real user utility, native AgentDojo attack success, GPU latency, independent human labels, or broad generalization.</p></article>
<article><h3>Next validation</h3><p>Frozen real-action pilots, independent human review, recurring-action studies, and matched repeated experiments on production hardware.</p></article>
</div>
</section></main>'''
    (DOCS / 'results.html').write_text(shell + intro + footer, encoding='utf-8')
    (DOCS / '.nojekyll').touch()
    print('Built homepage and results page from committed evidence; no inference performed.')


if __name__ == '__main__':
    build()
