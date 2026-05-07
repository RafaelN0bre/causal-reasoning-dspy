"""Main entry point for the causal reasoning pipeline.

Usage:
    uv run main.py                        # Legal mode (default)
    uv run main.py --legal                # Legal case analysis
    uv run main.py --legal --case-id 2   # Analyze a specific legal case

    uv run main.py --boardgame                          # BoardgameQA benchmark (Main-depth2, all test cases)
    uv run main.py -b -d Main-depth2 -n 50              # 50 cases from Main-depth2
    uv run main.py -b -d ZeroConflict-depth2 -s valid   # Valid split of ZeroConflict
    uv run main.py -b --charts                          # Run benchmark and generate charts

Available BoardgameQA variants:
    Main-depth1, Main-depth2, Main-depth3
    ZeroConflict-depth2, LowConflict-depth2, HighConflict-depth2
    EasyConflict-depth2, DifficultConflict-depth2
    SomeDistractors-depth2, ManyDistractors-depth2
    KnowledgeLight-depth2, KnowledgeHeavy-depth2
    Binary-depth1, Binary-depth2, Binary-depth3

Environment:
    GEMINI_API_KEY  (required) — Gemini API key
    LOG_LEVEL       (optional) — Logging level, default INFO
"""
import os
import sys
import logging
import argparse

import dspy
from dotenv import load_dotenv


def setup_logging() -> logging.Logger:
    """Configure logging based on LOG_LEVEL env var."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        log_level = getattr(logging, log_level_name)
    except Exception:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return logging.getLogger(__name__)


def setup_dspy(max_tokens: int = 16000) -> dspy.LM:
    """Initialize DSPy with Gemini LM.

    Args:
        max_tokens: Maximum tokens for LM responses.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found. Create a .env file with:")
        print("  GEMINI_API_KEY=your-api-key-here")
        sys.exit(1)

    os.environ.setdefault("DSPY_CACHEDIR", os.path.join(os.path.dirname(__file__), ".cache", "dspy"))
    lm = dspy.LM('gemini/gemini-2.5-pro', api_key=api_key, max_tokens=max_tokens)
    dspy.configure(lm=lm)
    return lm


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def run_legal_mode(args, pipeline) -> None:
    """Run legal case analysis against the golden dataset."""
    from src.pipeline import run_legal_analysis
    run_legal_analysis(pipeline, args.case_id)


def run_boardgame_mode(args, pipeline) -> None:
    """Run BoardgameQA benchmark.

    Loads the requested dataset variant/split, runs the pipeline on each case,
    and writes results + metrics to --output.  Optionally generates accuracy
    charts when --charts is set.
    """
    from src.pipeline import run_boardgame_tests, generate_boardgame_charts

    run_boardgame_tests(
        pipeline=pipeline,
        variant=args.dataset,
        split=args.split,
        limit=args.limit,
        output_dir=args.output,
    )

    if args.charts:
        generate_boardgame_charts(args.output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the appropriate mode."""
    from src.dataset import BOARDGAME_VARIANTS

    parser = argparse.ArgumentParser(
        description="DSPy + Defeasible Argumentation — Legal/Causal Reasoning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run main.py                            Legal mode (default, all cases)
  uv run main.py -l --case-id 1             Analyze legal case #1
  uv run main.py -b                         BoardgameQA benchmark (Main-depth2, test split)
  uv run main.py -b -d Main-depth2 -n 50    50 cases from Main-depth2
  uv run main.py -b -d Binary-depth1 -s valid --charts
        """,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--legal", "-l",
        action="store_true",
        help="Legal case analysis mode (default when no mode is given)",
    )
    mode_group.add_argument(
        "--boardgame", "-b",
        action="store_true",
        help="BoardgameQA benchmark mode",
    )

    # --- boardgame-only options ---
    parser.add_argument(
        "--dataset", "-d",
        choices=BOARDGAME_VARIANTS,
        default="Main-depth2",
        metavar="VARIANT",
        help=(
            "BoardgameQA dataset variant (default: Main-depth2). "
            f"Choices: {', '.join(BOARDGAME_VARIANTS)}"
        ),
    )
    parser.add_argument(
        "--split", "-s",
        choices=["train", "test", "valid"],
        default="test",
        help="Data split to use (default: test)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        metavar="N",
        help="Limit number of test cases processed (boardgame mode)",
    )
    parser.add_argument(
        "--charts", "-c",
        action="store_true",
        help="Generate accuracy charts after benchmark (requires matplotlib)",
    )
    parser.add_argument(
        "--output", "-o",
        default="outputs/boardgame",
        help="Output directory for boardgame results (default: outputs/boardgame)",
    )

    # --- legal-only options ---
    parser.add_argument(
        "--case-id",
        type=str,
        metavar="ID",
        help="Specific case ID to analyze (legal mode only)",
    )

    # --- shared options ---
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="Max tokens for LM responses (default: 16000)",
    )

    args = parser.parse_args()

    # Default to legal mode when neither flag is given
    if not args.legal and not args.boardgame:
        args.legal = True

    logger = setup_logging()
    logger.info("Starting pipeline (mode=%s)", "boardgame" if args.boardgame else "legal")

    load_dotenv()
    setup_dspy(max_tokens=args.max_tokens)

    from src.modules import CausalReasoningPipeline
    pipeline = CausalReasoningPipeline()

    if args.boardgame:
        run_boardgame_mode(args, pipeline)
    else:
        run_legal_mode(args, pipeline)


if __name__ == "__main__":
    main()