#!/usr/bin/env bash
# =============================================================================
# Run 5 cases for each strategy on Main-depth2, saving to outputs-observability/
# Each strategy gets a distinct Langfuse session for clean prompt comparison.
#
# Strategies:
#   1. baseline       — raw LLM, no solver
#   2. zero-shot      — DSPy + ASPIC+, no compiled program
#   3. few-shot       — DSPy + ASPIC+, BootstrapFewShot compiled program
#   4. mipro          — DSPy + ASPIC+, MIPROv2 compiled program
#
# Usage:
#   chmod +x scripts/run_observability_samples.sh
#   ./scripts/run_observability_samples.sh
# =============================================================================

set -euo pipefail

LIMIT=5
DATASET="Main-depth2"
SPLIT="test"
OUT_BASE="outputs-observability"

echo "=============================================="
echo " Observability: 4 strategies × $LIMIT cases"
echo " Dataset: $DATASET ($SPLIT split)"
echo " Output base: $OUT_BASE/"
echo "=============================================="
echo ""

echo ">>> [1/4] baseline"
uv run main.py -b -d "$DATASET" -s "$SPLIT" -n "$LIMIT" \
    --baseline \
    -o "$OUT_BASE/baseline" \
    --session-suffix "observability"
echo ""

echo ">>> [2/4] zero-shot"
uv run main.py -b -d "$DATASET" -s "$SPLIT" -n "$LIMIT" \
    --no-compiled \
    -o "$OUT_BASE/zero-shot" \
    --session-suffix "observability"
echo ""

echo ">>> [3/4] few-shot"
uv run main.py -b -d "$DATASET" -s "$SPLIT" -n "$LIMIT" \
    --optimizer few-shot \
    -o "$OUT_BASE/few-shot" \
    --session-suffix "observability"
echo ""

echo ">>> [4/4] mipro"
uv run main.py -b -d "$DATASET" -s "$SPLIT" -n "$LIMIT" \
    --optimizer mipro \
    -o "$OUT_BASE/mipro" \
    --session-suffix "observability"
echo ""

echo "=============================================="
echo " All 4 strategies completed!"
echo " Results in: $OUT_BASE/"
echo " Check Langfuse for traces."
echo "=============================================="
