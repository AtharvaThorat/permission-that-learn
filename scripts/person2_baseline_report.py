"""Build the Person 2 unprotected-baseline report from experiment run folders.

Reads a registry written by `person2_unprotected_baseline.ipynb` (one entry per model, with its run folder
and validation report, or the reason it has none) and writes, without modifying any run folder:

  unprotected_baseline_results.xlsx   sheets: Summary, Episodes, Validation, Run info
  summary.csv, episodes.csv           the same tables as CSV
  charts/1_headline_results.png       task utility (clean and attacked) and attack success rate
  charts/2_results_per_case.png       per test case: task done, attacker goal achieved, injection reached
  charts/3_cost_per_episode.png       tokens and duration of every episode

Metrics that a run did not produce stay empty; they are never replaced with zero.
Needs only the standard library, openpyxl and matplotlib (both preinstalled on Colab).

  python scripts/person2_baseline_report.py --registry <dir>/registry.json --output <dir>/report
"""

import argparse
import csv
import json
from pathlib import Path

# Colorblind-safe palette (validated); categorical slots in fixed order.
BLUE, ORANGE = "#2a78d6", "#eb6834"
SERIES_COLORS = [BLUE, ORANGE, "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, TEXT, MUTED_TEXT, GRID, NEUTRAL = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#f0efec"
GOOD, BAD = "#cde2fb", "#f6c1c0"   # light fills behind Yes/No text; meaning is always also written


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def text_of(content) -> str:
    """AgentDojo message content is a list of {'type': 'text', 'content': ...} blocks, or null."""
    if not content:
        return ""
    return "".join(block.get("content") or "" for block in content)


def percent(value):
    return None if value is None else round(100 * value, 1)


def episode_rows(entry: dict) -> list[dict]:
    """One row per finished episode attempt in the entry's run folder."""
    rows = []
    run_dir = Path(entry["run_dir"])
    for result_path in sorted(run_dir.glob("episodes/*/*/result.json")):
        result = read_json(result_path)
        conversation_path = result_path.parent / result["artifacts"]["conversation"]
        messages = read_json(conversation_path) if conversation_path.exists() else []
        tool_calls = [f"{call['function']}({json.dumps(call['args'], ensure_ascii=False)})"
                      for message in messages if message.get("role") == "assistant"
                      for call in (message.get("tool_calls") or [])]
        final_answers = [text_of(m.get("content")) for m in messages
                         if m.get("role") == "assistant" and not m.get("tool_calls")]
        usage = result.get("actor_usage") or {}
        counts = result.get("counts") or {}
        attack = result.get("attack")
        rows.append({
            "Model": entry["label"],
            "Task": result["task"],
            "Attack": attack["id"] if attack else "none (clean)",
            "Attacker goal": attack["objective"] if attack else "",
            "Lifecycle": result["lifecycle"],
            "Task done (utility)": result["utility"],
            "Attacker goal achieved": result["attack_success"] if attack else None,
            "Injection reached model": result["attack_exposed"] if attack else None,
            "Actor requests": counts.get("actor_requests"),
            "Tool calls proposed": counts.get("tool_proposals"),
            "Tool calls executed": counts.get("dispatches"),
            "Total tokens": usage.get("total_tokens"),
            "Episode seconds": (result.get("timings_seconds") or {}).get("episode_total"),
            "Tool calls made": "\n".join(tool_calls),
            "Final answer": final_answers[-1] if final_answers else "",
            "Backend errors": ", ".join(result.get("backend_errors") or []),
            "Pair ID": result["pair_id"][:12],
            "Attempt ID": result["attempt_id"],
            "Run folder": run_dir.name,
        })
    return sorted(rows, key=lambda row: (row["Attack"] != "none (clean)", row["Task"]))


def summary_row(entry: dict, episodes: list[dict], validation: dict | None) -> dict:
    """One row per model. Models without a run keep every metric empty."""
    attacked = [e for e in episodes if e["Attack"] != "none (clean)"]
    row = {
        "Model": entry["label"],
        "Hugging Face repo": entry["model_id"],
        "Quantization": entry.get("quantization") or "",
        "vLLM version": entry.get("vllm_version") or "",
        "Tool-call check": entry.get("tool_call_check") or "",
        "Status": entry["status"],
        "Validation": validation["overall"] if validation else "not run",
        "Episodes planned": None, "Completed": None,
        "Clean utility (%)": None, "Utility under attack (%)": None, "Attack success rate (%)": None,
        "Attacked episodes where injection reached model": None,
        "Total tokens": None, "Mean episode seconds": None,
        "Code identity": "", "Problem": entry.get("error") or "",
    }
    if not entry.get("run_dir"):
        return row
    run_dir = Path(entry["run_dir"])
    metrics = read_json(run_dir / "aggregates" / "summary.json")["metrics"]
    if len(metrics) != 1:
        raise ValueError(f"Expected one actor/mode group in {run_dir}, found {len(metrics)}")
    metric = metrics[0]
    row.update({
        "Episodes planned": metric["planned"],
        "Completed": metric["completed"],
        "Clean utility (%)": percent(metric["clean_utility_value"]),
        "Utility under attack (%)": percent(metric["attacked_utility_value"]),
        "Attack success rate (%)": percent(metric["attack_success_value"]),
        "Attacked episodes where injection reached model":
            f"{sum(e['Injection reached model'] is True for e in attacked)} of {len(attacked)}" if attacked else None,
        "Total tokens": metric["reported_total_tokens"],
        "Mean episode seconds": None if metric["mean_episode_seconds"] is None
        else round(metric["mean_episode_seconds"], 1),
        "Code identity": read_json(run_dir / "plan.json")["identity"]["implementation"][:12],
    })
    return row


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_workbook(path: Path, sheets: dict[str, list[dict]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        headers = list(rows[0])
        sheet.append(headers)
        for row in rows:
            sheet.append([row[h] for h in headers])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for column, header in enumerate(headers, start=1):
            longest = max(len(str(header)), *(len(str(r[header] or "")) for r in rows))
            sheet.column_dimensions[get_column_letter(column)].width = min(longest + 2, 70)
        for row_cells in sheet.iter_rows(min_row=2):
            for cell in row_cells:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(path)


def style_axis(axis, value_axis="y"):
    axis.set_facecolor(SURFACE)
    axis.grid(axis=value_axis, color=GRID, linewidth=1, zorder=0)
    axis.tick_params(length=0, colors=MUTED_TEXT)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(GRID)


def label_bars(axis, bars, values, value_format):
    """Print each value on its bar; a missing value is labeled n/a, never drawn as zero."""
    for bar, value in zip(bars, values):
        axis.annotate("n/a" if value is None else value_format(value),
                      (bar.get_x() + bar.get_width() / 2, bar.get_height()), xytext=(0, 3),
                      textcoords="offset points", ha="center", fontsize=8.5, color=MUTED_TEXT)


def new_figure(width, height, title, subtitle, columns=1):
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, columns, figsize=(width, height), facecolor=SURFACE, squeeze=False)
    figure.suptitle(title, x=0.02, ha="left", fontsize=13, fontweight="bold", color=TEXT)
    figure.text(0.02, 0.885, subtitle, fontsize=9, color=MUTED_TEXT)
    return figure, axes[0]


def chart_headline(summary):
    metrics = ["Clean utility (%)", "Utility under attack (%)", "Attack success rate (%)"]
    names = ["Task done\n(clean)", "Task done\n(under attack)", "Attacker goal\nachieved"]
    figure, (axis,) = new_figure(8, 4.6, "1. Headline results without protection",
                                 "Utility: higher is better. Attack success rate: lower is better. "
                                 "Percent of scored episodes.")
    style_axis(axis)
    slot = 0.8 / len(summary)
    for index, row in enumerate(summary):
        positions = [group + (index - (len(summary) - 1) / 2) * slot for group in range(len(metrics))]
        values = [row[m] for m in metrics]
        bars = axis.bar(positions, [0 if v is None else v for v in values], width=slot * 0.85,
                        color=SERIES_COLORS[index % len(SERIES_COLORS)], label=row["Model"], zorder=3)
        label_bars(axis, bars, values, lambda v: f"{v:.0f}%")
    axis.set_xticks(range(len(metrics)), names, color=TEXT)
    axis.set_ylim(0, 110)
    axis.set_yticks(range(0, 101, 25), [f"{tick}%" for tick in range(0, 101, 25)])
    if len(summary) > 1:
        axis.legend(frameon=False, ncol=len(summary), loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=9)
    figure.subplots_adjust(top=0.8, bottom=0.16)
    return figure


def chart_cases(episodes):
    """A table-like grid: one row per test case, Yes/No written in every cell."""
    from matplotlib.patches import Rectangle

    models = list(dict.fromkeys(e["Model"] for e in episodes))
    cases = list(dict.fromkeys((e["Model"], e["Task"]) for e in episodes))
    columns = ["Task done\n(clean)", "Task done\n(under attack)", "Attacker goal\nachieved", "Injection\nreached model"]

    def cell(model, task, attacked, field):
        match = [e for e in episodes if e["Model"] == model and e["Task"] == task
                 and (e["Attack"] != "none (clean)") == attacked]
        return match[0][field] if match else None

    figure, (axis,) = new_figure(9, 1.9 + 0.55 * len(cases), "2. Results per test case",
                                 "Each case is one user task, run clean and with the team's injection. "
                                 "Blue = good for the user, red = bad, grey = not applicable.")
    axis.set_facecolor(SURFACE)
    for row_index, (model, task) in enumerate(cases):
        attack = cell(model, task, True, "Attack")
        values = [cell(model, task, False, "Task done (utility)"), cell(model, task, True, "Task done (utility)"),
                  cell(model, task, True, "Attacker goal achieved"), cell(model, task, True, "Injection reached model")]
        good_when_yes = [True, True, False, None]
        for column_index, (value, good) in enumerate(zip(values, good_when_yes)):
            if value is None:
                fill, text = NEUTRAL, "n/a"
            else:
                fill = NEUTRAL if good is None else (GOOD if bool(value) == good else BAD)
                text = "Yes" if value else "No"
            axis.add_patch(Rectangle((column_index, row_index), 0.96, 0.9, facecolor=fill, edgecolor=SURFACE))
            axis.text(column_index + 0.48, row_index + 0.45, text, ha="center", va="center", fontsize=9, color=TEXT)
        name = f"{task}  ({attack or 'no attack'})" + (f" — {model}" if len(models) > 1 else "")
        axis.text(-0.08, row_index + 0.45, name, ha="right", va="center", fontsize=9, color=TEXT)
    axis.set_xlim(0, len(columns))
    axis.set_ylim(len(cases), -0.6)
    for column_index, column in enumerate(columns):
        axis.text(column_index + 0.48, -0.15, column, ha="center", va="bottom", fontsize=8.5, color=MUTED_TEXT)
    axis.axis("off")
    figure.subplots_adjust(left=0.36, right=0.98, top=0.78, bottom=0.04)
    return figure


def chart_cost(episodes):
    tasks = list(dict.fromkeys(e["Task"] for e in episodes))
    figure, axes = new_figure(11, 4.6, "3. Cost per episode",
                              "Tokens reported by the model server and episode duration; duration depends on "
                              "GPU and quantization.", columns=2)
    for axis, field, unit in ((axes[0], "Total tokens", lambda v: f"{v / 1000:.1f}k"),
                              (axes[1], "Episode seconds", lambda v: f"{v:.0f}s")):
        style_axis(axis)
        for offset, (attacked, color, name) in enumerate(((False, BLUE, "Clean"), (True, ORANGE, "Attacked"))):
            values = []
            for task in tasks:
                match = [e[field] for e in episodes if e["Task"] == task and (e["Attack"] != "none (clean)") == attacked]
                values.append(match[0] if match else None)
            positions = [i + (offset - 0.5) * 0.4 for i in range(len(tasks))]
            bars = axis.bar(positions, [0 if v is None else v for v in values], width=0.36, color=color,
                            label=name, zorder=3)
            label_bars(axis, bars, values, unit)
        axis.set_xticks(range(len(tasks)), tasks, rotation=20, ha="right", fontsize=8.5, color=TEXT)
        axis.set_title(field, loc="left", fontsize=10, color=MUTED_TEXT)
    axes[0].legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.08), fontsize=9)
    figure.subplots_adjust(top=0.7, bottom=0.2, wspace=0.2)
    return figure


def write_charts(directory: Path, summary: list[dict], episodes: list[dict]) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory.mkdir(parents=True, exist_ok=True)
    charts = [("1_headline_results.png", chart_headline(summary))]
    if episodes:
        charts += [("2_results_per_case.png", chart_cases(episodes)),
                   ("3_cost_per_episode.png", chart_cost(episodes))]
    paths = []
    for name, figure in charts:
        figure.savefig(directory / name, dpi=160, facecolor=SURFACE)
        plt.close(figure)
        paths.append(directory / name)
    return paths


def build_report(registry_path: Path, output: Path) -> dict[str, Path]:
    registry = read_json(registry_path)
    if not registry["models"]:
        raise ValueError("The registry lists no models")
    output.mkdir(parents=True, exist_ok=True)
    episodes, summary, validation_rows = [], [], []
    for entry in registry["models"]:
        rows = episode_rows(entry) if entry.get("run_dir") else []
        validation = read_json(Path(entry["validation_file"])) if entry.get("validation_file") else None
        episodes.extend(rows)
        summary.append(summary_row(entry, rows, validation))
        for check in (validation or {}).get("checks", []):
            validation_rows.append({"Model": entry["label"], "Status": check["status"], "Check": check["check"],
                                    "Detail": check["detail"]})
    run_info = [{"Field": key, "Value": json.dumps(value) if isinstance(value, (list, dict)) else value}
                for key, value in registry["run_info"].items()]
    written = {"summary.csv": output / "summary.csv",
               "unprotected_baseline_results.xlsx": output / "unprotected_baseline_results.xlsx"}
    write_csv(written["summary.csv"], summary)
    sheets = {"Summary": summary}
    if episodes:
        written["episodes.csv"] = output / "episodes.csv"
        write_csv(written["episodes.csv"], episodes)
        sheets["Episodes"] = episodes
    if validation_rows:
        sheets["Validation"] = validation_rows
    sheets["Run info"] = run_info
    write_workbook(written["unprotected_baseline_results.xlsx"], sheets)
    for path in write_charts(output / "charts", summary, episodes):
        written[path.name] = path
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Person 2 unprotected-baseline report")
    parser.add_argument("--registry", type=Path, required=True, help="registry.json written by the notebook")
    parser.add_argument("--output", type=Path, required=True, help="folder for the workbook, CSVs and charts")
    args = parser.parse_args()
    for name, path in build_report(args.registry, args.output).items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()
