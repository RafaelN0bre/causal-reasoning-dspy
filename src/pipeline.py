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
from typing import Optional, Dict, Any, List
from collections import Counter

from src.modules import CausalReasoningPipeline
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
    output_dir: str = "outputs/boardgame"
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
    
    results = []
    label_predictions: Dict[str, List[str]] = {"proved": [], "disproved": [], "unknown": []}
    label_actuals: Dict[str, List[str]] = {"proved": [], "disproved": [], "unknown": []}
    
    start_time = time.time()
    
    for idx, case in enumerate(cases):
        parsed = parse_boardgame_case(case)
        expected_label = parsed["label"]
        goal_str = parsed["goal_str"]
        
        logger.debug("Testing case %d/%d: goal=%s", idx + 1, len(cases), goal_str)
        
        case_text = f"Facts: {parsed['facts']}\n\nRules: {parsed['rules']}"
        if parsed['preferences']:
            case_text += f"\n\nPreferences: {parsed['preferences']}"
        
        try:
            result = pipeline.boardgame_forward(case_text, goal_str)
            base_grounded = result.get("base_grounded", [])
            causal_results = result.get("causal_results", {})
            grounded_conclusions = result.get("base_grounded_conclusions", {})
            target_conclusion = result.get("knowledge_base", {}).get("target_conclusion", "")

            logger.debug(
                "Case %d — target_conclusion='%s' | grounded_conclusions=%s",
                idx + 1, target_conclusion, grounded_conclusions,
            )

            predicted_label = _map_solver_to_label(
                base_grounded, causal_results, goal_str,
                grounded_conclusions=grounded_conclusions,
                target_conclusion=target_conclusion,
            )
            
        except Exception as e:
            logger.warning("Error on case %d: %s", idx + 1, e)
            predicted_label = "unknown"
        
        results.append({
            "index": idx,
            "goal": goal_str,
            "expected": expected_label,
            "predicted": predicted_label,
            "correct": predicted_label == expected_label
        })
        
        label_predictions[predicted_label].append(expected_label)
        label_actuals[expected_label].append(predicted_label)
        
        if (idx + 1) % 10 == 0:
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed
            logger.info("Progress: %d/%d (%.1f cases/sec)", idx + 1, len(cases), rate)
    
    total_time = time.time() - start_time
    
    metrics = _calculate_metrics(results)
    metrics["total_time"] = total_time
    metrics["cases_per_second"] = len(cases) / total_time if total_time > 0 else 0
    
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{variant}_{split}_results.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "variant": variant,
            "split": split,
            "total_cases": len(cases),
            "metrics": metrics,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    logger.info("💾 Results saved to: %s", output_file)
    _print_boardgame_summary(metrics, variant, split, len(cases))
    
    return {
        "variant": variant,
        "split": split,
        "metrics": metrics,
        "results": results,
        "output_file": output_file
    }


def _map_solver_to_label(
    base_grounded: List[str],
    causal_results: Dict[str, Any],
    goal_str: str,
    grounded_conclusions: Optional[Dict[str, str]] = None,
    target_conclusion: str = "",
) -> str:
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
        One of "proved", "disproved", or "unknown".
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

    # --- Primary check: use actual conclusions from the grounded extension ---
    if grounded_conclusions:
        for conclusion in grounded_conclusions.values():
            conc = conclusion.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()
            conc_base = _base(conc)
            conc_negated = _is_negation(conc)

            # Match against both goal_str and the LLM-extracted target_conclusion
            for needle in filter(None, [goal_clean, target_clean]):
                needle_base = _base(needle)
                if conc_base == needle_base or needle_base in conc_base or conc_base in needle_base:
                    return "disproved" if conc_negated else "proved"

        logger.debug(
            "_map_solver_to_label: no match in conclusions %s for goal='%s' target='%s'",
            list(grounded_conclusions.values()), goal_str, target_conclusion,
        )
        return "unknown"

    # --- Fallback: string match against argument IDs (will rarely succeed) ---
    logger.debug("_map_solver_to_label: grounded_conclusions unavailable, falling back to ID matching")
    neg_goal_prefixes = (f"not{goal_clean}", f"¬{goal_clean}", f"neg_{goal_clean}", f"neg{goal_clean}")
    for arg in base_grounded:
        arg_lower = arg.lower()
        if any(arg_lower.startswith(pfx) or pfx in arg_lower for pfx in neg_goal_prefixes):
            return "disproved"
        if goal_clean in arg_lower:
            return "proved"

    return "unknown"


def _calculate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate accuracy metrics from test results."""
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    
    confusion = Counter()
    for r in results:
        confusion[(r["expected"], r["predicted"])] += 1
    
    label_metrics = {}
    for label in ["proved", "disproved", "unknown"]:
        label_results = [r for r in results if r["expected"] == label]
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


