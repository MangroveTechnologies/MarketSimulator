"""
LLM Model Benchmark for MangroveAI Copilot (v2.0).

Three-agent benchmarking system:
  - User agent (cheap LLM) generates user messages following a scenario goal
  - Copilot under test processes messages through the state machine
  - Judge agent(s) score completed transcripts against a 7-criterion rubric

Entry point: ``run_benchmark.py`` (CLI orchestrator).

See README.md for full documentation and usage guide.
"""
