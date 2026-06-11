"""Baseline BoardgameQA runner — raw LLM call, no DSPy, no ASPIC+ solver.

Called from main.py when --boardgame --baseline is used.
The LLM receives the same inputs as the DSPy pipeline (facts, rules,
preferences, goal) and returns a label directly — no KB extraction,
no rule extraction, no solver.

This allows a direct comparison:
    uv run main.py -b -d Main-depth2            ← DSPy + ASPIC+
    uv run main.py -b -d Main-depth2 --baseline ← raw LLM
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai

from src.dataset import load_boardgame_dataset, parse_boardgame_case
from src.pipeline import _calculate_metrics, _analyze_unknowns

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_BLOCK = """You are a logical reasoning assistant that evaluates boardgame scenarios.

Your task: given a set of FACTS and RULES about a game state, determine whether a
GOAL statement is proved, disproved, or unknown.

DEFINITIONS
  "proved"    — the goal CAN be logically derived from the facts using the rules.
  "disproved" — the NEGATION of the goal can be derived from the facts using the rules.
  "unknown"   — neither the goal nor its negation can be derived from the given
                facts and rules.

REASONING RULES
  1. Base your reasoning ONLY on the provided facts and rules. No external knowledge.
  2. A rule fires ONLY if ALL its stated conditions are satisfied by the given facts.
     If any condition is missing from the facts, the rule does NOT fire.
  3. When two rules yield conflicting conclusions, use any stated Preferences to decide
     which rule's conclusion wins.  If there are no applicable preferences to resolve
     the conflict, classify as "unknown".
  4. Evaluate numerical comparisons explicitly (e.g., 86 > 5 + 15 = 20 → condition met).

OUTPUT FORMAT
Return ONLY a valid JSON object — no markdown fences, no extra text:
{
  "label": "proved" | "disproved" | "unknown",
  "reasoning": "<concise step-by-step reasoning>"
}"""


def _build_prompt(facts: str, rules: str, preferences: str, goal_str: str) -> str:
    parts = [
        _SYSTEM_BLOCK,
        "---",
        f"Facts:\n{facts}",
        f"Rules:\n{rules}",
    ]
    if preferences and preferences.strip():
        parts.append(f"Preferences:\n{preferences}")
    parts.append(f"Goal to evaluate: {goal_str}")
    parts.append(
        "\nAnswer with ONLY the JSON object defined above. "
        "Do NOT include any text before or after it."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(
    model: genai.GenerativeModel,
    facts: str,
    rules: str,
    preferences: str,
    goal_str: str,
) -> Tuple[str, str, str]:
    """
    Issue a single raw Gemini API call for one boardgame case.

    Data flow: facts + rules + preferences + goal_str → LLM → (label, reasoning).
    expected_label is NEVER passed here; it is only used after this call returns.

    Returns:
        (label, reasoning, raw_response)
    """
    prompt = _build_prompt(facts, rules, preferences, goal_str)
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as exc:
        logger.warning("LLM API error: %s", exc)
        return "unknown", f"API error: {exc}", ""

    label, reasoning = _parse_response(raw)
    return label, reasoning, raw


def _parse_response(raw: str) -> Tuple[str, str]:
    """Extract (label, reasoning) from the raw LLM text."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE).strip()

    # Strategy 1: direct JSON parse
    try:
        parsed = json.loads(text)
        label = str(parsed.get("label", "unknown")).lower().strip()
        reasoning = str(parsed.get("reasoning", ""))
        if label not in ("proved", "disproved", "unknown"):
            label = "unknown"
        return label, reasoning
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: find first {...} block containing "label"
    match = re.search(r'\{[^{}]*"label"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            label = str(parsed.get("label", "unknown")).lower().strip()
            reasoning = str(parsed.get("reasoning", ""))
            if label not in ("proved", "disproved", "unknown"):
                label = "unknown"
            return label, reasoning
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: keyword scan
    lower = raw.lower()
    for candidate in ("proved", "disproved", "unknown"):
        if f'"label": "{candidate}"' in lower or f'"label":"{candidate}"' in lower:
            return candidate, raw

    logger.warning("Could not parse label from response: %r", raw[:300])
    return "unknown", raw


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_baseline_tests(
    model: genai.GenerativeModel,
    variant: str,
    split: str,
    limit: Optional[int],
    output_dir: str,
) -> Dict[str, Any]:
    """
    Run the baseline test over a BoardgameQA split.

    For each case the LLM receives: facts, rules, preferences, goal.
    The expected label is retrieved AFTER the LLM call and used ONLY for metrics.

    Output files:
      <output_dir>/<variant>_<split>_results.json
      <output_dir>/<variant>_<split>_trace.jsonl
    """
    logger.info("Loading BoardgameQA: %s (%s split)", variant, split)
    cases = load_boardgame_dataset(variant, split)
    if limit:
        cases = cases[:limit]
    logger.info("Loaded %d cases (limit=%s)", len(cases), limit or "none")

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{variant}_{split}_results.json")
    trace_file = os.path.join(output_dir, f"{variant}_{split}_trace.jsonl")

    # Resume: skip already-processed indices
    done_indices: set = set()
    results: List[Dict[str, Any]] = []
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                prev = json.load(f)
            results = prev.get("results", [])
            done_indices = {r["index"] for r in results}
            if done_indices:
                logger.info(
                    "Resuming: %d already-processed cases (indices %d–%d)",
                    len(done_indices), min(done_indices), max(done_indices),
                )
        except Exception as exc:
            logger.warning("Could not load previous results for resume: %s", exc)
            results, done_indices = [], set()

    start_time = time.time()
    trace_mode = "a" if done_indices else "w"

    with open(trace_file, trace_mode, encoding="utf-8") as tf:
        for idx, case in enumerate(cases):
            if idx in done_indices:
                continue

            parsed = parse_boardgame_case(case)

            # expected_label is held here; NEVER passed to the LLM call below
            expected_label: str = parsed["label"]
            goal_str: str = parsed["goal_str"]
            facts: str = parsed["facts"]
            rules: str = parsed["rules"]
            preferences: str = parsed["preferences"]

            logger.debug(
                "Case %d/%d: goal=%s | expected=%s",
                idx + 1, len(cases), goal_str, expected_label,
            )

            predicted_label, reasoning, raw_response = _call_llm(
                model, facts, rules, preferences, goal_str,
            )

            correct = predicted_label == expected_label

            result_entry: Dict[str, Any] = {
                "index": idx,
                "goal": goal_str,
                "expected": expected_label,
                "predicted": predicted_label,
                "correct": correct,
            }
            results.append(result_entry)

            trace_entry: Dict[str, Any] = {
                **result_entry,
                "facts_raw": facts,
                "rules_raw": rules,
                "preferences_raw": preferences,
                "proof_reference": parsed.get("proof", ""),
                "llm_reasoning": reasoning,
                "llm_raw_response": raw_response,
            }
            tf.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
            tf.flush()

            if (idx + 1) % 10 == 0:
                elapsed = time.time() - start_time
                new_count = idx + 1 - len(done_indices)
                rate = new_count / elapsed if elapsed > 0 else 0
                logger.info("Progress: %d/%d (%.1f cases/sec)", idx + 1, len(cases), rate)

    total_time = time.time() - start_time
    new_count = len(cases) - len(done_indices)

    metrics = _calculate_metrics(results)
    metrics["total_time"] = total_time
    metrics["cases_per_second"] = new_count / total_time if total_time > 0 else 0
    metrics["unknown_analysis"] = _analyze_unknowns(results)

    summary = {
        "variant": variant,
        "split": split,
        "mode": "baseline_llm",
        "total_cases": len(results),
        "metrics": metrics,
        "results": results,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Results → %s", output_file)
    logger.info("Trace   → %s", trace_file)
    _print_summary(metrics, variant, split, len(results))

    return summary


def _print_summary(
    metrics: Dict[str, Any],
    variant: str,
    split: str,
    total: int,
) -> None:
    logger.info("=" * 50)
    logger.info("Baseline LLM Results: %s (%s)", variant, split)
    logger.info("=" * 50)
    logger.info(
        "Total: %d | Correct: %d | Accuracy: %.2f%%",
        total, metrics["correct"], metrics["accuracy"] * 100,
    )
    for lbl, data in metrics.get("per_label", {}).items():
        logger.info(
            "  %s: %d/%d (%.2f%%)",
            lbl, data["correct"], data["total"], data["accuracy"] * 100,
        )
    logger.info(
        "Time: %.2fs (%.2f cases/sec)",
        metrics["total_time"], metrics["cases_per_second"],
    )
    logger.info("=" * 50)
