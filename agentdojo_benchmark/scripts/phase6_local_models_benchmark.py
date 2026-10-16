"""Phase 6: benchmark local Hugging Face models with AgentDojo, tests running in parallel.

The logic lives in src/agentdojo_benchmark/local_benchmark.py; this script is the entry point.
Normally run from notebooks/local_models_benchmark.ipynb on a Colab T4 GPU.

  python scripts/phase6_local_models_benchmark.py --plan-only     # list the tests, no GPU needed
  python scripts/phase6_local_models_benchmark.py --help          # all options
"""

from agentdojo_benchmark.local_benchmark import main

if __name__ == "__main__":
    main()
