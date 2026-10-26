"""Offline, self-contained HTML inspection of every saved attempt."""
import html
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from .artifacts import lines


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def pretty(value):
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False))


def report(run_dir):
    directory = Path(run_dir).resolve()
    plan = read(directory / 'plan.json')
    if not plan.get('jobs'):
        raise ValueError('A saved experiment plan is required')
    sections, summary, seen = [], [], set()
    for manifest in sorted(directory.glob('episodes/*/*/manifest.json')):
        attempt = read(manifest)
        job = attempt['job']
        seen.add(job['episode_spec_id'])
        folder = manifest.parent
        result = read(folder / 'result.json')
        failure = read(folder / 'failure.json')
        status = result.get('lifecycle', failure.get('lifecycle', 'interrupted / incomplete'))
        if status == 'completed':
            status += (' / task success' if result.get('utility') is True else
                       ' / task failure' if result.get('utility') is False else ' / scoring missing')
        key = attempt['attempt_id']
        summary.append(f'<tr><td><a href="#{html.escape(key, quote=True)}">{html.escape(key[:12])}</a></td>'
                       f'<td>{html.escape(job["task"])}</td><td>{html.escape(job["mode"])}</td>'
                       f'<td>{html.escape(status)}</td></tr>')
        links = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in ('.json', '.jsonl') and path.resolve().is_relative_to(directory):
                relative = path.relative_to(directory).as_posix()
                links.append(f'<a href="{quote(relative)}">{html.escape(path.name)}</a>')
        trace = []
        for filename in ('events.jsonl', 'actor.jsonl', 'decisions.jsonl'):
            for number, event in enumerate(lines(folder / filename)):
                trace.append((event.get('timestamp', ''), filename, number, event))
        trace.sort(key=lambda row: row[:3])
        entries = []
        for timestamp, filename, number, event in trace:
            title = ' | '.join(str(v) for v in (timestamp or 'time unavailable', event.get('event'),
                                event.get('tool'), event.get('decision'), event.get('reason_code')) if v)
            entries.append(f'<details><summary>{html.escape(title)}</summary>'
                           f'<small>{filename}:{number + 1}</small><pre>{pretty(event)}</pre></details>')
        conversation = read(folder / 'conversation.json')
        final = next((m.get('content') for m in reversed(conversation)
                      if isinstance(m, dict) and m.get('role') == 'assistant' and m.get('content')), None) if isinstance(conversation, list) else None
        if isinstance(final, list):
            final = '\n'.join(str(block.get('content', block.get('text', '')))
                              if isinstance(block, dict) else str(block) for block in final)
        if isinstance(final, list):
            final = '\n'.join(str(block.get('content', block.get('text', '')))
                              if isinstance(block, dict) else str(block) for block in final)
        measures = {'native_utility': result.get('utility'), 'evaluated': result.get('evaluated'),
                    'dispatches': result.get('counts', {}).get('dispatches'),
                    'errors': result.get('backend_errors', failure.get('error_kind'))}
        sections.append(f'<section id="{html.escape(key, quote=True)}"><h2>{html.escape(job["task"])} / '
                        f'{html.escape(job["mode"])} / {html.escape(key[:12])}</h2>'
                        f'<p>{html.escape(status)}</p><p>{" · ".join(links)}</p>'
                        f'<pre>{pretty(measures)}</pre><h3>Final response</h3><pre>{html.escape(str(final)) if final is not None else "Unavailable"}</pre>'
                        f'<details><summary>Outcome and measurements (null = unavailable)</summary>'
                        f'<pre>{pretty(result or failure or {"status": status})}</pre></details>'
                        f'<details><summary>Final conversation and tool outcomes</summary>'
                        f'<pre>{pretty(conversation)}</pre></details>'
                        f'<h3>Chronological trace</h3>{"".join(entries) or "<p>No trace saved.</p>"}</section>')
    for job in plan['jobs']:
        if job['episode_spec_id'] not in seen:
            summary.append(f'<tr><td>not attempted</td><td>{html.escape(job["task"])}</td>'
                           f'<td>{html.escape(job["mode"])}</td><td>missing</td></tr>')
    provenance = ' | '.join(f'<a href="{quote(p.name)}">{html.escape(p.name)}</a>'
        for p in sorted(directory.iterdir()) if p.is_file() and p.suffix in ('.json', '.csv'))
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
                '<title>GRIDS episode report</title><style>'
                'body{font:16px system-ui;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#17202a}'
                'table{border-collapse:collapse;width:100%}td,th{padding:.7rem;border:1px solid #ccc;text-align:left}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:1rem}'
                'section{border-top:2px solid #ccc;margin-top:2rem}details{margin:.7rem 0}summary{cursor:pointer}'
                '</style><h1>GRIDS episode report</h1>'
                f'<p>Run: {html.escape(directory.name)}. All attempts are shown; no best-retry selection.</p>'
                f'<p>Configuration, provenance and summaries: {provenance}</p>'
                '<p>Model errors are operational failures, not semantic ASK decisions. '
                'Legacy entries without timestamps appear first in file order. Raw artifacts may contain task data.</p>'
                '<table><thead><tr><th>Attempt</th><th>Task</th><th>Mode</th><th>Status</th></tr></thead><tbody>'
                + ''.join(summary) + '</tbody></table>' + ''.join(sections) + '</html>')
    path = directory / ('report-' + uuid4().hex[:12] + '.html')
    with path.open('x', encoding='utf-8') as stream:
        stream.write(document)
    return str(path)
