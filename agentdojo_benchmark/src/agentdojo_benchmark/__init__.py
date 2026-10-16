"""Prompt-injection benchmark of LLM agents with AgentDojo.

Modules:
  config           shared settings (paths, NVIDIA NIM endpoint and models)
  nim_pipeline     the AgentDojo agent and API-compatibility fixes (used by every phase)
  custom_attacks   two extra attacker goals for the workspace suite
  tracker          the Excel tracker for the NIM phases 2-5
  local_models     local Hugging Face models: download, vLLM server, agent (phase 6)
  local_test_plan  the fixed list of tests every local model runs (phase 6)
  local_benchmark  runs the phase 6 benchmark in parallel and writes the results

The runnable entry points are in ../../scripts/.
"""
