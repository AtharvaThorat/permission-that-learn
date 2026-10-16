"""Phase 6 report: charts and a shareable PDF built from the benchmark's result files.

Reads <results_dir>/ (written by local_benchmark.py) and writes:
  charts/1_model_comparison.png     baseline utility, utility under attack, attack success rate per model
  charts/2_attack_outcomes.png      what happened in each attacked test: task done or not x attack resisted or not
  charts/3_attack_success_heatmap.png  attack success rate per model, by attack style and by suite
  benchmark_report.pdf              page 1: what was run, key results, how to read them; then the three charts

Run:  python scripts/make_report.py --results-dir <output>/results
"""

import importlib.metadata
import json
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap

from agentdojo_benchmark import config
from agentdojo_benchmark.local_models import LOCAL_MODELS

# ---------- colors and text (colorblind-safe, checked with a palette validator) ----------

SURFACE, TEXT, MUTED_TEXT, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# One color per model, in a fixed order, so a model has the same color in every chart.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MODEL_COLORS = {model.served_name: SERIES_COLORS[i % len(SERIES_COLORS)] for i, model in enumerate(LOCAL_MODELS.values())}
# Attack outcomes: blue = attack resisted, red = attack succeeded; dark = user's task done, light = not done.
OUTCOMES = [  # (label, color), in the order they are stacked
    ("Task done, attack resisted", "#1c5cab"),
    ("Task not done, attack resisted", "#86b6ef"),
    ("Task not done, attack succeeded", "#ec7d7c"),
    ("Task done, attack succeeded", "#b52a2a"),
    ("Run crashed (excluded)", "#c3c2b7"),
]
# Heatmap: one blue hue, light = low attack success, dark = high.
HEATMAP_COLORS = LinearSegmentedColormap.from_list(
    "attack_success", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": GRID, "text.color": TEXT})


# ---------- loading the results ----------

@dataclass
class BenchmarkResults:
    summary: pd.DataFrame  # one row per model
    breakdown: pd.DataFrame  # attack success rate per model, by attack style and by suite
    tests: pd.DataFrame  # one row per test
    plan: list[dict]  # the tests every model ran

    @property
    def models(self) -> list[str]:
        """Models in the order they were run."""
        return list(self.summary["model"])

    @property
    def attacked_tests(self) -> pd.DataFrame:
        return self.tests[self.tests["attack"] != "none"]


def _as_bool(column: pd.Series) -> pd.Series:
    """CSV values 'True'/'False'/'' -> True/False/NaN."""
    return column.astype(str).map({"True": True, "False": False})


def load_results(results_dir: Path) -> BenchmarkResults:
    tests = pd.read_csv(results_dir / "test_results.csv", keep_default_na=False)
    tests["utility"] = _as_bool(tests["utility"])
    tests["attack_success"] = _as_bool(tests["attack_success"])
    plan_file = results_dir.parent / "test_plan.json"
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else []
    return BenchmarkResults(
        summary=pd.read_csv(results_dir / "model_summary.csv"),
        breakdown=pd.read_csv(results_dir / "attack_success_breakdown.csv"),
        tests=tests,
        plan=plan,
    )


# ---------- shared chart styling ----------

def _new_figure(width: float, height: float):
    figure, axis = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    axis.set_facecolor(SURFACE)
    return figure, axis


def _add_titles(axis, title: str, subtitle: str, legend_rows: int) -> None:
    """Stack, from the top: title, subtitle, legend, then the plot. Distances are in points, so the
    layout holds whatever the chart's height (i.e. however many models there are)."""
    legend_height = 15 * legend_rows + 6
    subtitle_lines = subtitle.count("\n") + 1
    axis.annotate(subtitle, xy=(0, 1), xycoords="axes fraction", xytext=(0, legend_height + 4),
                  textcoords="offset points", va="bottom", fontsize=9, color=MUTED_TEXT)
    axis.set_title(title, loc="left", fontsize=13, color=TEXT, fontweight="bold",
                   pad=legend_height + 4 + 12 * subtitle_lines + 8)


def _style_axes(axis, value_axis: str) -> None:
    """Hairline grid on the value axis only, no box, no tick marks."""
    axis.grid(axis=value_axis, color=GRID, linewidth=1, zorder=0)
    axis.tick_params(length=0, colors=MUTED_TEXT)
    for side in ("top", "right", "left", "bottom"):
        axis.spines[side].set_visible(False)


# ---------- chart 1: model comparison ----------

def chart_model_comparison(results: BenchmarkResults):
    """Grouped bars: the three headline percentages, one bar per model."""
    metrics = {
        "baseline_utility_pct": "Baseline utility\n(no attack)",
        "utility_under_attack_pct": "Utility under attack",
        "attack_success_rate_pct": "Attack success rate",
    }
    table = results.summary.set_index("model")[list(metrics)].T.rename(index=metrics)
    models = results.models
    figure, axis = _new_figure(9, 4.8)
    slot = 0.8 / len(models)
    for index, model in enumerate(models):
        positions = [group + (index - (len(models) - 1) / 2) * slot for group in range(len(table.index))]
        values = table[model].tolist()
        bars = axis.bar(positions, [0 if pd.isna(v) else v for v in values], width=slot * 0.85,
                        color=MODEL_COLORS.get(model, SERIES_COLORS[index]), label=model, zorder=3)
        for bar, value in zip(bars, values):  # every bar shows its value
            axis.annotate("n/a" if pd.isna(value) else f"{value:.0f}%",
                          (bar.get_x() + bar.get_width() / 2, bar.get_height()), xytext=(0, 3),
                          textcoords="offset points", ha="center", fontsize=8, color=MUTED_TEXT)
    axis.set_xticks(range(len(table.index)), table.index, color=TEXT)
    axis.set_ylim(0, 110)
    axis.set_yticks(range(0, 101, 25), [f"{tick}%" for tick in range(0, 101, 25)])
    _style_axes(axis, "y")
    axis.spines["bottom"].set_visible(True)
    _add_titles(axis, "1. Model comparison", "Utility: higher is better.  Attack success rate: lower is better.",
                legend_rows=1)
    axis.legend(frameon=False, ncol=len(models), loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=9,
                handlelength=1.2, borderaxespad=0.2)
    figure.tight_layout()
    return figure


# ---------- chart 2: what happened in the attacked tests ----------

def outcome_counts(results: BenchmarkResults) -> pd.DataFrame:
    """Number of attacked tests per model in each outcome (rows = models, columns = OUTCOMES labels)."""
    attacked = results.attacked_tests
    counts = {}
    for model in results.models:
        rows = attacked[attacked["model"] == model]
        crashed = rows["error"] != ""
        ok = rows[~crashed]
        done, hijacked = ok["utility"] == True, ok["attack_success"] == True  # noqa: E712 (NaN-safe)
        counts[model] = [
            int((done & ~hijacked).sum()), int((~done & ~hijacked).sum()),
            int((~done & hijacked).sum()), int((done & hijacked).sum()), int(crashed.sum()),
        ]
    return pd.DataFrame.from_dict(counts, orient="index", columns=[label for label, _ in OUTCOMES])


def chart_attack_outcomes(results: BenchmarkResults):
    """100% stacked bars: for each model, how its attacked tests ended."""
    counts = outcome_counts(results)
    shares = counts.div(counts.sum(axis=1).replace(0, 1), axis=0) * 100
    figure, axis = _new_figure(9, 1.6 + 0.75 * len(counts))
    left = pd.Series(0.0, index=counts.index)
    for label, color in OUTCOMES:
        if counts[label].sum() == 0 and label.startswith("Run crashed"):
            continue  # no crashes: leave the category out of the chart and legend
        axis.barh(counts.index, shares[label], left=left, color=color, label=label, height=0.55,
                  edgecolor=SURFACE, linewidth=2, zorder=3)  # surface-colored gap between segments
        for model in counts.index:  # count inside the segment when it fits
            if shares.loc[model, label] >= 7:
                text_color = "white" if color in ("#1c5cab", "#b52a2a") else TEXT
                axis.text(left[model] + shares.loc[model, label] / 2, model, str(counts.loc[model, label]),
                          ha="center", va="center", fontsize=9, color=text_color, zorder=4)
        left += shares[label]
    axis.invert_yaxis()  # first model on top
    axis.set_xlim(0, 100)
    axis.set_xticks(range(0, 101, 25), [f"{tick}%" for tick in range(0, 101, 25)])
    axis.tick_params(axis="y", labelcolor=TEXT)
    _style_axes(axis, "x")
    _add_titles(axis, "2. How the attacked tests ended",
                "Share of each model's attacked tests; the numbers are test counts.\n"
                "Blue = attack resisted, red = attack succeeded. Dark = the user's task was still done.",
                legend_rows=2)
    axis.legend(frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5,
                handlelength=1.2, borderaxespad=0.2)
    figure.tight_layout()
    return figure


# ---------- chart 3: attack success by attack style and by suite ----------

def chart_attack_success_heatmap(results: BenchmarkResults):
    """Two heatmaps side by side: attack success rate per model x attack style, and per model x suite."""
    groups = [("attack", "By attack style"), ("suite", "By suite")]
    tables = [results.breakdown[results.breakdown["group_by"] == group_by]
              .pivot(index="model", columns="group", values="attack_success_rate_pct")
              .reindex(results.models) for group_by, _ in groups]
    run_counts = [results.breakdown[results.breakdown["group_by"] == group_by]
                  .pivot(index="model", columns="group", values="attacked_runs")
                  .reindex(results.models) for group_by, _ in groups]
    widths = [max(len(table.columns), 1) for table in tables]
    figure, axes = plt.subplots(1, 2, figsize=(11, 1.9 + 0.62 * len(results.models)), facecolor=SURFACE,
                                gridspec_kw={"width_ratios": widths})
    for axis, table, counts, (_, panel_title) in zip(axes, tables, run_counts, groups):
        axis.set_facecolor(SURFACE)
        image = axis.imshow(table.to_numpy(dtype=float), cmap=HEATMAP_COLORS, vmin=0, vmax=100, aspect="auto")
        for row, model in enumerate(table.index):
            for column, group in enumerate(table.columns):
                value, runs = table.loc[model, group], counts.loc[model, group]
                label = "n/a" if pd.isna(value) else f"{value:.0f}%\n({int(runs)} tests)"
                axis.text(column, row, label, ha="center", va="center", fontsize=8,
                          color="white" if not pd.isna(value) and value >= 55 else TEXT)
        axis.set_xticks(range(len(table.columns)), [c.replace("_", "\n") for c in table.columns], fontsize=8.5)
        axis.set_yticks(range(len(table.index)), table.index if axis is axes[0] else [""] * len(table.index))
        axis.tick_params(length=0, colors=TEXT)
        for side in axis.spines.values():
            side.set_visible(False)
        axis.set_title(panel_title, loc="left", fontsize=10, color=MUTED_TEXT)
    figure.subplots_adjust(top=0.78, bottom=0.18, left=0.2, right=0.88, wspace=0.08)
    colorbar_axis = figure.add_axes([0.905, 0.18, 0.012, 0.6])  # its own space, right of both panels
    colorbar = figure.colorbar(image, cax=colorbar_axis)
    colorbar.set_label("Attack success rate (%)", color=MUTED_TEXT, fontsize=8.5)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(length=0, labelsize=8, colors=MUTED_TEXT)
    figure.suptitle("3. Attack success rate by attack style and by suite", x=0.01, ha="left",
                    fontsize=13, fontweight="bold", color=TEXT)
    figure.text(0.01, 0.9, "Darker = attacks succeeded more often. Lower is better.", fontsize=9, color=MUTED_TEXT)
    return figure


# ---------- page 1 of the PDF: what was run and how to read it ----------

def _gpu_name() -> str:
    if shutil.which("nvidia-smi") is None:
        return "unknown"
    try:
        output = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        return output.splitlines()[0] if output else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _count_by(plan: list[dict], field: str) -> str:
    counts: dict[str, int] = {}
    for test in plan:
        if test.get("attack"):
            counts[test[field]] = counts.get(test[field], 0) + 1
    return ", ".join(f"{name} {count}" for name, count in counts.items())


def run_details(results: BenchmarkResults) -> dict:
    """Facts about the run, for the report's first page."""
    attacked_per_model = sum(1 for test in results.plan if test.get("attack"))
    baseline_per_model = len(results.plan) - attacked_per_model
    repos = {model.served_name: model.hf_repo for model in LOCAL_MODELS.values()}
    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agentdojo": f"AgentDojo {importlib.metadata.version('agentdojo')}, task suites {config.BENCHMARK_VERSION}",
        "gpu": _gpu_name(),
        "models": [(model, repos.get(model, "")) for model in results.models],
        "attacked_per_model": attacked_per_model,
        "baseline_per_model": baseline_per_model,
        "suites": _count_by(results.plan, "suite"),
        "attacks": _count_by(results.plan, "attack"),
        "total_runs": len(results.tests),
    }


def _percent_text(value) -> str:
    return "n/a" if pd.isna(value) else f"{value:.0f}%"


def summary_page(results: BenchmarkResults):
    """A text page: what was run, the key numbers, and how to read them."""
    details = run_details(results)
    figure = plt.figure(figsize=(11.69, 8.27), facecolor=SURFACE)  # A4 landscape
    write = figure.text
    write(0.05, 0.94, "AgentDojo prompt-injection benchmark: local models", fontsize=17, fontweight="bold")
    write(0.05, 0.905, f"Generated {details['generated']}  ·  {details['agentdojo']}  ·  GPU: {details['gpu']}",
          fontsize=9, color=MUTED_TEXT)

    write(0.05, 0.85, "What was run", fontsize=12, fontweight="bold")
    attacked, baseline = details["attacked_per_model"], details["baseline_per_model"]
    lines = [
        f"{len(details['models'])} models, each given exactly the same {attacked + baseline} test runs:",
        f"   •  {attacked} attacked tests: the attacker's instruction is hidden in data the agent reads",
        f"        suites: {details['suites']}",
        f"        attack styles: {details['attacks']}",
        f"   •  {baseline} no-attack runs of the same user tasks (can the model do the task at all?)",
        f"Total runs: {details['total_runs']}.  No defense was used: these are baseline numbers for unprotected models.",
    ]
    for number, line in enumerate(lines):
        write(0.05, 0.815 - number * 0.03, line, fontsize=9.5)

    write(0.05, 0.6, "Key results", fontsize=12, fontweight="bold")
    repos = dict(details["models"])
    rows = [[model, repos.get(model, ""), _percent_text(row.baseline_utility_pct),
             _percent_text(row.utility_under_attack_pct), _percent_text(row.attack_success_rate_pct),
             f"{row.attacked_runs} + {row.baseline_runs}", str(row.errors)]
            for model, row in zip(results.summary["model"], results.summary.itertuples())]
    row_height, header_height = 0.04, 0.065  # fractions of the page height
    table_height = header_height + row_height * len(rows)
    table_axis = figure.add_axes([0.05, 0.585 - table_height, 0.9, table_height])
    table_axis.axis("off")
    table = table_axis.table(
        cellText=rows, cellLoc="left", loc="upper left",
        colLabels=["Model", "Hugging Face repo", "Baseline\nutility", "Utility\nunder attack",
                   "Attack\nsuccess rate", "Runs counted\n(attacked + no-attack)", "Crashed\nruns"],
        colWidths=[0.17, 0.3, 0.08, 0.09, 0.09, 0.17, 0.07])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (row_index, _), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_height((header_height if row_index == 0 else row_height) / table_height)
        cell.PAD = 0.04
        if row_index == 0:
            cell.set_text_props(fontweight="bold")
            cell.set_facecolor("#f0efec")

    notes_top = 0.585 - table_height - 0.06
    write(0.05, notes_top, "How to read the results", fontsize=12, fontweight="bold")
    one_test = 100 / attacked if attacked else 0
    notes = [
        "Utility: share of runs where the agent completed the user's real task correctly. Higher is better.",
        "Attack success rate: share of attacked tests where the attacker's goal actually happened "
        "(AgentDojo checks its simulated email, files, etc.). Lower is better.",
        "Read the two together: a model that rarely completes tasks also rarely carries out attacks, "
        "so a low attack success rate is only good news if utility is reasonable (see chart 2).",
        f"Sample size: with {attacked} attacked tests per model, one test moves a model's attack success rate by "
        f"{one_test:.0f} percentage points. Treat small differences between models as noise.",
        "Crashed runs (e.g. the conversation became longer than the model's context window) are left out "
        "of the percentages.",
        "Charts: 1 = headline numbers per model;  2 = how each attacked test ended;  "
        "3 = attack success by attack style and by suite.",
    ]
    y = notes_top - 0.035
    for note in notes:  # wrap long notes so nothing runs off the page
        for line_number, line in enumerate(textwrap.wrap(note, width=150)):
            write(0.05, y, ("•  " if line_number == 0 else "    ") + line, fontsize=9)
            y -= 0.026
        y -= 0.008
    return figure


# ---------- putting it together ----------

def build_report(results_dir: Path) -> dict[str, Path]:
    """Write the three chart PNGs and the PDF report. Returns {name: path}."""
    results = load_results(results_dir)
    charts_dir = results_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    charts = {
        "1_model_comparison.png": chart_model_comparison(results),
        "2_attack_outcomes.png": chart_attack_outcomes(results),
        "3_attack_success_heatmap.png": chart_attack_success_heatmap(results),
    }
    written = {}
    for file_name, figure in charts.items():
        path = charts_dir / file_name
        figure.savefig(path, dpi=160, facecolor=SURFACE, bbox_inches="tight")
        written[file_name] = path

    pdf_path = results_dir / "benchmark_report.pdf"
    with PdfPages(pdf_path) as pdf:
        first_page = summary_page(results)
        pdf.savefig(first_page, facecolor=SURFACE)
        plt.close(first_page)
        for figure in charts.values():
            pdf.savefig(figure, facecolor=SURFACE, bbox_inches="tight")
            plt.close(figure)
    written["benchmark_report.pdf"] = pdf_path
    return written
