"""Phase 6 report: three comparison charts (PNG) and a shareable PDF from the benchmark results.

  python scripts/make_report.py --results-dir /content/drive/MyDrive/agentdojo_local_benchmark/output/results

The logic lives in src/agentdojo_benchmark/report.py.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only; no screen needed

from agentdojo_benchmark.report import build_report  # noqa: E402  (must come after choosing the backend)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the phase 6 charts and PDF report")
    parser.add_argument("--results-dir", type=Path, required=True,
                        help="the results/ folder written by phase6_local_models_benchmark.py")
    args = parser.parse_args()
    for name, path in build_report(args.results_dir).items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()
