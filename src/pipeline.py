"""Runners para os dois modos de execução do pipeline.

Este módulo expõe duas funções principais:
  - run_legal_analysis   : análise de casos do GOLDEN_DATASET
  - run_boardgame_tests  : benchmark BoardgameQA

O ponto de entrada é main.py (uv run main.py).
"""
import json
import os
import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from collections import Counter

from src.modules import CausalReasoningPipeline
from src.observability import (
    get_langfuse,
    flush_langfuse,
    register_dspy_callback,
    begin_boardgame_trace,
    end_boardgame_trace,
)
from src.dataset import (
    GOLDEN_DATASET, 
    BOARDGAME_VARIANTS,
    load_boardgame_dataset,
    parse_boardgame_case
)

# Module logger
logger = logging.getLogger(__name__)


def analyze_case(pipeline: CausalReasoningPipeline, 
                case_data: Dict[str, Any],
                output_dir: str = "outputs") -> Dict[str, Any]:
    """
    Analyze a single case and compare with expected results.
    
    Args:
        pipeline: Configured CausalReasoningPipeline instance
        case_data: Case data from GOLDEN_DATASET
        output_dir: Directory to save results
    
    Returns:
        Dictionary with analysis results and validation
    """
    logger.info(f"📋 Analyzing case {case_data['id']}: {case_data['name']}...")

    # Run analysis (use module(...) instead of .forward(...) per dspy recommendation)
    logger.debug("Starting pipeline for case %s (text preview): %s",
                 case_data['id'],
                 (case_data['case_text'][:200] + '...') if len(case_data['case_text']) > 200 else case_data['case_text'])
    result = pipeline(case_data['case_text'])
    
    # Validate against expected results
    validation = {
        "knowledge_base": {
            "matches": result["knowledge_base"] == case_data["expected_knowledge_base"],
            "expected": case_data["expected_knowledge_base"],
            "got": result["knowledge_base"]
        },
        "causal_model": {
            "matches": result["causal_model"] == case_data["expected_causal_model"],
            "expected": case_data["expected_causal_model"],
            "got": result["causal_model"]
        },
            "causal_results": {
                # expected entries can be booleans or dicts like {"is_cause": bool}
                "matches": all(
                    result["causal_results"].get(cause, {}).get("is_cause") == (
                        expected["is_cause"] if isinstance(expected, dict) else expected
                    )
                    for cause, expected in case_data["expected_causal_result"].items()
                ),
                "expected": case_data["expected_causal_result"],
                "got": result["causal_results"]
            }
    }
    
    # Save detailed results
    output_path = os.path.join(output_dir, f"case_{case_data['id']}_results.json")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "case": case_data,
            "analysis": result,
            "validation": validation
        }, f, ensure_ascii=False, indent=2)
    
    # Print summary
    logger.info("🔍 Validation Results:")
    for aspect, check in validation.items():
        status = "✅" if check["matches"] else "❌"
        logger.info("%s %s", status, aspect)

    logger.info("💾 Detailed results saved to: %s", output_path)
    
    return {
        "case_id": case_data["id"],
        "name": case_data["name"],
        "validation": validation,
        "output_path": output_path
    }


def run_boardgame_tests(
    pipeline: CausalReasoningPipeline,
    variant: str = "Main-depth2",
    split: str = "test",
    limit: Optional[int] = None,
    output_dir: str = "outputs/boardgame",
    optimizer: str = "zero-shot",
    session_suffix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run BoardgameQA benchmark tests.
    
    Args:
        pipeline: Configured CausalReasoningPipeline instance
        variant: Dataset variant (e.g., "Main-depth2")
        split: Data split ("train", "test", "valid")
        limit: Maximum number of test cases (None for all)
        output_dir: Directory to save results
    
    Returns:
        Dictionary with test results and metrics
    """
    logger.info("🎲 Loading BoardgameQA dataset: %s (%s)", variant, split)

    cases = load_boardgame_dataset(variant, split)
    if limit:
        cases = cases[:limit]

    logger.info("📊 Loaded %d test cases (limit: %s)", len(cases), limit or "none")

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{variant}_{split}_results.json")
    trace_file = os.path.join(output_dir, f"{variant}_{split}_trace.jsonl")

    # --- Resume: load already-processed results ---
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
                    "Resuming: found %d already-processed cases (indices %d–%d), skipping them.",
                    len(done_indices), min(done_indices), max(done_indices),
                )
        except Exception as e:
            logger.warning("Could not load previous results for resuming: %s", e)
            results = []
            done_indices = set()

    label_predictions: Dict[str, List[str]] = {"proved": [], "disproved": [], "unknown": []}
    label_actuals: Dict[str, List[str]] = {"proved": [], "disproved": [], "unknown": []}

    lf = get_langfuse()
    register_dspy_callback(lf)
    lf_session_id = f"{variant}-{split}-{optimizer}"
    if session_suffix:
        lf_session_id += f"-{session_suffix}"

    start_time = time.time()

    trace_mode = "a" if done_indices else "w"
    with open(trace_file, trace_mode, encoding="utf-8") as tf:
        for idx, case in enumerate(cases):
            if idx in done_indices:
                continue

            parsed = parse_boardgame_case(case)

            # --- Isolate the expected answer BEFORE building LLM inputs ---
            # expected_label is used ONLY for post-hoc metric computation.
            # It is NEVER passed to pipeline.boardgame_forward or any LLM call.
            expected_label: str = parsed["label"]
            goal_str: str = parsed["goal_str"]

            # Build the text that will be sent to the LLM (facts + rules + preferences).
            # The expected label MUST NOT appear anywhere in this string.
            case_text = f"Facts: {parsed['facts']}\n\nRules: {parsed['rules']}"
            if parsed['preferences']:
                case_text += f"\n\nPreferences: {parsed['preferences']}"

            # Explicit pre-call data-flow integrity check:
            # Verifies that the expected answer label is not embedded in case_text.
            # This would only occur if the dataset itself leaked the label into the
            # facts/rules/preferences fields — which is a dataset-level issue, not a
            # pipeline issue.  The pipeline itself never injects expected_label.
            if expected_label.lower() in case_text.lower():
                logger.warning(
                    "DATA FLOW ALERT — Case %d: expected_label '%s' appears verbatim "
                    "in case_text BEFORE the pipeline call.  This indicates the dataset "
                    "field (facts/rules/preferences) contains the answer string directly.  "
                    "This is a dataset-level leakage, not a pipeline leak.",
                    idx + 1, expected_label,
                )

            logger.debug("Testing case %d/%d: goal=%s | expected=%s", idx + 1, len(cases), goal_str, expected_label)

            pipeline_trace: Dict[str, Any] = {}
            leakage_check: Dict[str, Any] = {}
            error_info: Optional[str] = None

            # Create trace BEFORE the pipeline so LM calls are linked as child generations
            lf_trace = begin_boardgame_trace(
                lf,
                session_id=lf_session_id,
                idx=idx,
                case_text=case_text,
                goal_str=goal_str,
                expected_label=expected_label,
                variant=variant,
                split=split,
                optimizer=optimizer,
            )

            try:
                # Only case_text and goal_str enter the pipeline.
                # expected_label is held here and used only after the call returns.
                result = pipeline.boardgame_forward(case_text, goal_str)
                base_grounded = result.get("base_grounded", [])
                causal_results = result.get("causal_results", {})
                grounded_conclusions = result.get("base_grounded_conclusions", {})
                target_conclusion = result.get("knowledge_base", {}).get("target_conclusion", "")
                kb = result.get("knowledge_base", {})
                pipeline_trace = result.get("_trace", {})

                # Bias / leakage check
                leakage_check = _check_answer_leakage(
                    case_text=case_text,
                    kb=kb,
                    rules=pipeline_trace.get("rules_parsed", {}),
                    goal_str=goal_str,
                    expected_label=expected_label,
                )
                if leakage_check["warnings"]:
                    logger.warning(
                        "Case %d leakage/bias warnings: %s",
                        idx + 1, leakage_check["warnings"],
                    )

                logger.debug(
                    "Case %d — target_conclusion='%s' | grounded_conclusions=%s",
                    idx + 1, target_conclusion, grounded_conclusions,
                )

                predicted_label, prediction_trace = _map_solver_to_label(
                    base_grounded, causal_results, goal_str,
                    grounded_conclusions=grounded_conclusions,
                    target_conclusion=target_conclusion,
                )

            except Exception as e:
                logger.warning("Error on case %d: %s", idx + 1, e)
                predicted_label = "error"
                prediction_trace = {"method": "error", "decision_reason": str(e)}
                error_info = str(e)

            correct = predicted_label == expected_label
            result_entry = {
                "index": idx,
                "goal": goal_str,
                "expected": expected_label,
                "predicted": predicted_label,
                "correct": correct,
                **({"error": True} if error_info else {}),
            }
            results.append(result_entry)

            if predicted_label != "error":
                label_predictions[predicted_label].append(expected_label)
                label_actuals[expected_label].append(predicted_label)

            end_boardgame_trace(
                lf_trace,
                idx=idx,
                expected_label=expected_label,
                predicted_label=predicted_label,
                correct=correct,
                pipeline_trace=pipeline_trace,
                prediction_trace=prediction_trace,
                error_info=error_info,
            )

            # --- Write full trace line to JSONL ---
            trace_entry: Dict[str, Any] = {
                **result_entry,
                "case_text": case_text,
                "facts_raw": parsed["facts"],
                "rules_raw": parsed["rules"],
                "preferences_raw": parsed["preferences"],
                "proof_reference": parsed.get("proof", ""),
                "pipeline_trace": pipeline_trace,
                "prediction_trace": prediction_trace,
                "leakage_check": leakage_check,
            }
            if error_info:
                trace_entry["error"] = error_info

            # Annotate unknown cases with reason
            if predicted_label == "unknown":
                num_grounded = len(pipeline_trace.get("grounded_ids", []))
                if num_grounded == 0:
                    trace_entry["unknown_reason"] = "empty_grounded_extension"
                else:
                    trace_entry["unknown_reason"] = "goal_not_in_grounded_conclusions"
            elif predicted_label == "error":
                trace_entry["unknown_reason"] = "api_error"
            if expected_label == "unknown":
                trace_entry["dataset_unknown"] = True  # ground-truth is unknown

            tf.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")

            if (idx + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed
                logger.info("Progress: %d/%d (%.1f cases/sec)", idx + 1, len(cases), rate)

    total_time = time.time() - start_time

    metrics = _calculate_metrics(results)
    metrics["total_time"] = total_time
    new_cases_count = len(cases) - len(done_indices)
    metrics["cases_per_second"] = new_cases_count / total_time if total_time > 0 else 0
    metrics["unknown_analysis"] = _analyze_unknowns(results)
    metrics["leakage_summary"] = _summarize_leakage(trace_file)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "variant": variant,
            "split": split,
            "total_cases": len(results),
            "metrics": metrics,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    logger.info("💾 Results saved to: %s", output_file)
    logger.info("🔍 Full trace saved to: %s", trace_file)
    flush_langfuse()
    _print_boardgame_summary(metrics, variant, split, len(results))

    return {
        "variant": variant,
        "split": split,
        "metrics": metrics,
        "results": results,
        "output_file": output_file,
        "trace_file": trace_file,
    }


def _check_answer_leakage(
    case_text: str,
    kb: Dict[str, Any],
    rules: Dict[str, Any],
    goal_str: str,
    expected_label: str,
) -> Dict[str, Any]:
    """
    Check for answer leakage or goal-directed bias in the LLM extraction.

    Potential bias vectors:
    1. Direct leakage: the expected label string appears in case_text (e.g., "proved").
    2. Goal-as-premise: the target_conclusion is encoded directly as a premise, making
       it trivially proved without needing any rule to fire.
    3. Negated-goal-as-premise: ¬target_conclusion as a premise trivially disproves.
    4. Empty premises: LLM extracted no premises at all (extraction failure).
    5. Rule count mismatch hint: significantly fewer rules than stated in the text
       (LLM may have selectively dropped rules that conflict with the expected answer).
    """
    warnings = []

    # Check 1: Direct label string in case_text
    if expected_label.lower() in case_text.lower():
        warnings.append(
            f"DIRECT_LEAKAGE: expected label '{expected_label}' found verbatim in case_text"
        )

    target = kb.get("target_conclusion", "").lower().strip()
    premises_lower = [p.lower().strip() for p in kb.get("premises", [])]

    # Check 2: target_conclusion is a direct premise (trivially proved)
    goal_as_premise = bool(target) and any(
        target == p or target in p or p in target for p in premises_lower if p
    )
    if goal_as_premise:
        warnings.append(
            f"GOAL_AS_PREMISE: target_conclusion '{target}' appears as a premise "
            f"(trivially {'proved' if expected_label == 'proved' else 'suspicious'})"
        )

    # Check 3: negation of goal as premise (trivially disproved)
    neg_target = target[1:] if target.startswith("¬") else f"¬{target}"
    neg_as_premise = bool(target) and any(
        neg_target == p or neg_target in p or p in neg_target for p in premises_lower if p
    )
    if neg_as_premise:
        warnings.append(
            f"NEG_GOAL_AS_PREMISE: negation '{neg_target}' appears as a premise "
            f"(trivially {'disproved' if expected_label == 'disproved' else 'suspicious'})"
        )

    # Check 4: empty premises
    if not premises_lower:
        warnings.append("EMPTY_PREMISES: no premises extracted — KB extraction likely failed")

    # Check 5: "proved"/"disproved"/"unknown" words inside extracted rule strings
    for rule in rules.get("defeasible_rules", []) + rules.get("undercutter_rules", []):
        for word in ("proved", "disproved", "unknown"):
            if word in rule.lower():
                warnings.append(
                    f"LABEL_IN_RULE: label word '{word}' found inside extracted rule: {rule!r}"
                )
                break

    return {
        "has_direct_leakage": expected_label.lower() in case_text.lower(),
        "goal_as_premise": goal_as_premise,
        "neg_goal_as_premise": neg_as_premise,
        "empty_premises": not premises_lower,
        "num_premises": len(kb.get("premises", [])),
        "num_defeasible_rules": len(rules.get("defeasible_rules", [])),
        "num_undercutter_rules": len(rules.get("undercutter_rules", [])),
        "warnings": warnings,
    }


def _map_solver_to_label(
    base_grounded: List[str],
    causal_results: Dict[str, Any],
    goal_str: str,
    grounded_conclusions: Optional[Dict[str, str]] = None,
    target_conclusion: str = "",
) -> tuple:
    """
    Map solver results to a BoardgameQA label.

    Strategy (in priority order):
    1. Check actual argument conclusions from the grounded extension against
       the goal / target_conclusion (most reliable — avoids ID string matching).
    2. Fallback: check argument IDs for the goal string (less reliable, kept
       for backward compatibility when conclusions are unavailable).

    - "proved"    : a grounded argument concludes the goal predicate
    - "disproved" : a grounded argument concludes the negation of the goal
    - "unknown"   : neither the goal nor its negation is grounded

    Args:
        base_grounded: List of grounded argument IDs from the solver.
        causal_results: Unused here, kept for signature compatibility.
        goal_str: Goal predicate string, e.g. "(swan, swear, woodpecker)".
        grounded_conclusions: Map of {arg_id: conclusion} for grounded arguments,
            as returned by ArgumentationSolver (3rd return value).
        target_conclusion: The target conclusion extracted by the LLM KB step.
            Often matches the goal but may be expressed differently.

    Returns:
        Tuple of (label, trace_dict) where label is one of "proved", "disproved",
        "unknown" and trace_dict captures the decision path for debugging.
    """
    # Normalise goal for fuzzy matching
    goal_clean = goal_str.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()
    target_clean = target_conclusion.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()

    neg_prefixes = ("not", "¬", "neg_", "neg")

    def _is_negation(literal: str) -> bool:
        return any(literal.startswith(p) for p in neg_prefixes)

    def _base(literal: str) -> str:
        """Strip leading negation prefix to get the base predicate."""
        for p in neg_prefixes:
            if literal.startswith(p):
                return literal[len(p):]
        return literal

    trace: Dict[str, Any] = {
        "method": None,
        "goal_clean": goal_clean,
        "target_clean": target_clean,
        "grounded_conclusions_list": list(grounded_conclusions.values()) if grounded_conclusions else [],
        "num_grounded_args": len(base_grounded),
        "conclusion_checks": [],
        "decision_reason": "",
    }

    # --- Primary check: use actual conclusions from the grounded extension ---
    if grounded_conclusions:
        trace["method"] = "conclusions"
        for arg_id, conclusion in grounded_conclusions.items():
            conc = conclusion.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()
            conc_base = _base(conc)
            conc_negated = _is_negation(conc)

            check_entry: Dict[str, Any] = {
                "arg_id": arg_id,
                "conclusion_raw": conclusion,
                "conc_normalised": conc,
                "conc_base": conc_base,
                "conc_negated": conc_negated,
                "matched": False,
                "matched_needle": None,
            }

            # Match against both goal_str and the LLM-extracted target_conclusion
            for needle in filter(None, [goal_clean, target_clean]):
                needle_base = _base(needle)
                if conc_base == needle_base or needle_base in conc_base or conc_base in needle_base:
                    check_entry["matched"] = True
                    check_entry["matched_needle"] = needle
                    trace["conclusion_checks"].append(check_entry)
                    label = "disproved" if conc_negated else "proved"
                    trace["decision_reason"] = (
                        f"Conclusion '{conclusion}' (arg {arg_id}) matched needle '{needle}'; "
                        f"negated={conc_negated} → {label}"
                    )
                    logger.debug(
                        "_map_solver_to_label: %s via conclusions match (arg=%s, conc=%s)",
                        label, arg_id, conclusion,
                    )
                    return label, trace

            trace["conclusion_checks"].append(check_entry)

        # No match found — check why
        if not grounded_conclusions:
            trace["decision_reason"] = "empty grounded extension (no arguments accepted)"
        else:
            trace["decision_reason"] = (
                f"No conclusion in grounded extension matched goal '{goal_str}' "
                f"or target '{target_conclusion}'. "
                f"Grounded conclusions: {list(grounded_conclusions.values())}"
            )
        logger.debug(
            "_map_solver_to_label: no match in conclusions %s for goal='%s' target='%s'",
            list(grounded_conclusions.values()), goal_str, target_conclusion,
        )
        return "unknown", trace

    # --- Fallback: string match against argument IDs (will rarely succeed) ---
    trace["method"] = "id_fallback"
    logger.debug("_map_solver_to_label: grounded_conclusions unavailable, falling back to ID matching")
    neg_goal_prefixes = (f"not{goal_clean}", f"¬{goal_clean}", f"neg_{goal_clean}", f"neg{goal_clean}")
    for arg in base_grounded:
        arg_lower = arg.lower()
        if any(arg_lower.startswith(pfx) or pfx in arg_lower for pfx in neg_goal_prefixes):
            trace["decision_reason"] = f"ID fallback: arg '{arg}' matched negation of goal"
            return "disproved", trace
        if goal_clean in arg_lower:
            trace["decision_reason"] = f"ID fallback: arg '{arg}' contains goal"
            return "proved", trace

    trace["decision_reason"] = "ID fallback: no argument ID matched goal"
    return "unknown", trace


def _analyze_unknowns(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Break down 'unknown' predictions to understand their origins:

    - correct_unknown      : predicted unknown AND expected unknown (correct)
    - false_unknown_proved : expected proved   BUT predicted unknown (miss)
    - false_unknown_disproved: expected disproved BUT predicted unknown (miss)
    - predicted_unknown_for_proved/disproved: combined miss count
    - dataset_unknowns     : total cases whose ground-truth label is unknown
    - predicted_unknowns   : total cases where pipeline predicted unknown
    """
    predicted_unknowns = [r for r in results if r["predicted"] == "unknown"]
    dataset_unknowns   = [r for r in results if r["expected"]  == "unknown"]

    breakdown = Counter((r["expected"], r["predicted"]) for r in results)

    return {
        "dataset_unknowns_total": len(dataset_unknowns),
        "predicted_unknowns_total": len(predicted_unknowns),
        "correct_unknown": breakdown[("unknown", "unknown")],
        "false_unknown_proved": breakdown[("proved", "unknown")],
        "false_unknown_disproved": breakdown[("disproved", "unknown")],
        "false_proved_unknown": breakdown[("unknown", "proved")],
        "false_disproved_unknown": breakdown[("unknown", "disproved")],
        # Dataset-unknown accuracy
        "dataset_unknown_accuracy": (
            breakdown[("unknown", "unknown")] / len(dataset_unknowns)
            if dataset_unknowns else None
        ),
    }


def _summarize_leakage(trace_file: str) -> Dict[str, Any]:
    """
    Read the JSONL trace file and aggregate leakage / bias statistics.
    Returns counts of each warning type across all cases.
    """
    warning_counts: Counter = Counter()
    cases_with_warnings = 0
    goal_as_premise_count = 0
    empty_premises_count = 0
    total = 0

    try:
        with open(trace_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                lc = entry.get("leakage_check", {})
                total += 1
                if lc.get("warnings"):
                    cases_with_warnings += 1
                    for w in lc["warnings"]:
                        # Bucket by prefix (e.g., "DIRECT_LEAKAGE", "GOAL_AS_PREMISE", ...)
                        warning_counts[w.split(":")[0]] += 1
                if lc.get("goal_as_premise"):
                    goal_as_premise_count += 1
                if lc.get("empty_premises"):
                    empty_premises_count += 1
    except Exception as e:
        logger.warning("Could not read trace file for leakage summary: %s", e)
        return {}

    return {
        "total_cases_checked": total,
        "cases_with_warnings": cases_with_warnings,
        "goal_as_premise_count": goal_as_premise_count,
        "empty_premises_count": empty_premises_count,
        "warning_type_counts": dict(warning_counts),
    }


def _calculate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate accuracy metrics from test results. Errored cases are excluded from accuracy."""
    errored = [r for r in results if r.get("predicted") == "error"]
    valid = [r for r in results if r.get("predicted") != "error"]
    total = len(valid)
    correct = sum(1 for r in valid if r["correct"])
    
    confusion = Counter()
    for r in valid:
        confusion[(r["expected"], r["predicted"])] += 1

    label_metrics = {}
    for label in ["proved", "disproved", "unknown"]:
        label_results = [r for r in valid if r["expected"] == label]
        if label_results:
            label_correct = sum(1 for r in label_results if r["correct"])
            label_metrics[label] = {
                "total": len(label_results),
                "correct": label_correct,
                "accuracy": label_correct / len(label_results) if label_results else 0
            }

    return {
        "accuracy": correct / total if total > 0 else 0,
        "total": total,
        "correct": correct,
        "errored": len(errored),
        "confusion_matrix": {f"{k[0]}->{k[1]}": v for k, v in dict(confusion).items()},
        "per_label": label_metrics
    }


def _print_boardgame_summary(
    metrics: Dict[str, Any],
    variant: str,
    split: str,
    total: int
) -> None:
    """Print boardgame test summary to console."""
    logger.info("=" * 50)
    logger.info("🎲 BoardgameQA Results: %s (%s)", variant, split)
    logger.info("=" * 50)
    logger.info("Total cases: %d", total)
    logger.info("Errored (excluded): %d", metrics.get("errored", 0))
    logger.info("Accuracy: %.2f%%", metrics["accuracy"] * 100)
    logger.info("Correct: %d/%d", metrics["correct"], metrics["total"])
    logger.info("-" * 50)
    logger.info("Per-label breakdown:")
    for label, data in metrics.get("per_label", {}).items():
        logger.info("  %s: %d/%d (%.2f%%)", label, data["correct"], data["total"], data["accuracy"] * 100)
    logger.info("-" * 50)
    logger.info("Time: %.2fs (%.2f cases/sec)", metrics["total_time"], metrics["cases_per_second"])
    logger.info("=" * 50)


def generate_boardgame_charts(results_dir: str = "outputs/boardgame") -> None:
    """Generate charts from boardgame test results."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')
    except ImportError:
        logger.warning("matplotlib not installed. Skipping chart generation.")
        logger.info("Install with: pip install matplotlib")
        return
    
    result_files = [f for f in os.listdir(results_dir) if f.endswith("_results.json")]
    if not result_files:
        logger.warning("No result files found in %s", results_dir)
        return
    
    datasets = []
    accuracies = []
    total_cases = []
    
    for fname in result_files:
        with open(os.path.join(results_dir, fname), "r") as f:
            data = json.load(f)
        
        variant = data.get("variant", "unknown")
        metrics = data.get("metrics", {})
        datasets.append(variant)
        accuracies.append(metrics.get("accuracy", 0) * 100)
        total_cases.append(metrics.get("total", 0))
    
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(range(len(datasets)), accuracies, color='steelblue')
    ax.set_xticks(range(len(datasets)))
    ax.set_xticklabels(datasets, rotation=45, ha='right')
    ax.set_ylabel('Accuracy (%)')
    ax.set_title('BoardgameQA Accuracy by Dataset Variant')
    ax.set_ylim(0, 100)
    
    for bar, cases in zip(bars, total_cases):
        ax.annotate(f'n={cases}', xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                   ha='center', va='bottom', fontsize=8)
    
    for bar, acc in zip(bars, accuracies):
        ax.annotate(f'{acc:.1f}%', xy=(bar.get_x() + bar.get_width() / 2, bar.get_height() / 2),
                   ha='center', va='center', fontsize=9, fontweight='bold', color='white')
    
    plt.tight_layout()
    chart_path = os.path.join(results_dir, "accuracy_by_dataset.png")
    plt.savefig(chart_path)
    plt.close()
    
    logger.info("📊 Chart saved to: %s", chart_path)


def run_legal_analysis(pipeline: CausalReasoningPipeline, case_id: Optional[str] = None):
    """Run legal case analysis."""
    logger.info("📚 Available cases:")
    for case in GOLDEN_DATASET:
        logger.info("%s. %s", case['id'], case['name'])
    
    if case_id:
        case = next((c for c in GOLDEN_DATASET if str(c["id"]) == case_id), None)
        if not case:
            print(f"⚠️  Caso {case_id} não encontrado")
            return
        results = [analyze_case(pipeline, case)]
    else:
        results = [analyze_case(pipeline, case) for case in GOLDEN_DATASET]
    
    logger.info("📊 Resultados Gerais:")
    successful = sum(1 for r in results 
                    if all(v["matches"] for v in r["validation"].values()))
    logger.info("✅ %s/%s casos passaram em todas as validações", successful, len(results))
    
    summary_path = os.path.join("outputs", "analysis_summary.json")
    os.makedirs("outputs", exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_cases": len(results),
            "successful_cases": successful,
            "case_results": results
        }, f, ensure_ascii=False, indent=2)
    
    logger.info("💾 Resumo salvo em: %s", summary_path)


