"""Main entry point for the causal reasoning pipeline.

Usage:
    uv run main.py                        # Legal mode (default)
    uv run main.py --legal                # Legal case analysis
    uv run main.py --legal --case-id 2    # Analyze a specific legal case

    uv run main.py --boardgame                              # DSPy + ASPIC+ (Main-depth2, test split)
    uv run main.py -b -d Main-depth2 -n 50                  # 50 cases, DSPy pipeline
    uv run main.py -b -d Main-depth2 --baseline             # Raw LLM, no solver
    uv run main.py -b -d Main-depth2 -n 50 --baseline       # 50 cases, raw LLM
    uv run main.py -b --charts                              # Run + generate charts
    uv run main.py -b --no-compiled                         # Força zero-shot (ignora compiled/)

Compilação (BootstrapFewShot):
    uv run scripts/optimize_fewshot.py                    # Otimiza Main-depth2, salva em compiled/
    uv run scripts/optimize_fewshot.py -d Main-depth1     # Otimiza outra variante
    uv run scripts/optimize_fewshot.py --help             # Ver todas as opções

Output directories:
    outputs/boardgame/dspy/compiled/<optimizer>/  ← DSPy + ASPIC+ com programa compilado
    outputs/boardgame/dspy/zero-shot/             ← DSPy + ASPIC+ sem programa compilado
    outputs/boardgame/baseline/                   ← raw LLM results (when --baseline is used)
    compiled/<optimizer>/                         ← programas DSPy compilados (auto-carregados)

Optimizers disponíveis (--optimizer):
    few-shot   ← BootstrapFewShot (padrão)
    mipro      ← MIPROv2

Available BoardgameQA variants:
    Main-depth1, Main-depth2, Main-depth3
    ZeroConflict-depth2, LowConflict-depth2, HighConflict-depth2
    EasyConflict-depth2, DifficultConflict-depth2
    SomeDistractors-depth2, ManyDistractors-depth2
    KnowledgeLight-depth2, KnowledgeHeavy-depth2
    Binary-depth1, Binary-depth2, Binary-depth3

Environment:
    GEMINI_API_KEY  (required) — Gemini API key
    GEMINI_MODEL    (optional) — model name, default gemini-2.5-flash
    LOG_LEVEL       (optional) — logging level, default INFO
"""
import os
import sys
import logging
import argparse
from datetime import datetime

from dotenv import load_dotenv

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")


def setup_logging(run_label: str = "") -> logging.Logger:
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        log_level = getattr(logging, log_level_name)
    except Exception:
        log_level = logging.INFO

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Terminal handler
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # File handler — logs/<timestamp>_<label>.log
    os.makedirs(LOGS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = run_label.replace("/", "-").replace(" ", "_") if run_label else "run"
    log_filename = os.path.join(LOGS_DIR, f"{ts}_{safe_label}.log")
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logger = logging.getLogger(__name__)
    logger.info("Log file: %s", log_filename)
    logger.info("Command : %s", " ".join(sys.argv))
    return logger


def setup_dspy(api_key: str, model_name: str, max_tokens: int):
    import dspy
    os.environ.setdefault("DSPY_CACHEDIR", os.path.join(os.path.dirname(__file__), ".cache", "dspy"))
    lm = dspy.LM(f"gemini/{model_name}", api_key=api_key, max_tokens=max_tokens)
    dspy.configure(lm=lm)


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def run_legal_mode(args, pipeline) -> None:
    from src.pipeline import run_legal_analysis
    run_legal_analysis(pipeline, args.case_id)


def run_boardgame_dspy(args, pipeline) -> None:
    from src.pipeline import run_boardgame_tests, generate_boardgame_charts
    run_boardgame_tests(
        pipeline=pipeline,
        variant=args.dataset,
        split=args.split,
        limit=args.limit,
        output_dir=args.output,
        optimizer=args.optimizer if not args.no_compiled else "zero-shot",
        session_suffix=args.session_suffix,
    )
    if args.charts:
        generate_boardgame_charts(args.output)


def load_boardgame_pipeline(variant: str, optimizer: str, no_compiled: bool, logger) -> "BoardgamePipeline":
    """Instancia BoardgamePipeline e carrega programa compilado, se disponível."""
    from src.boardgame_module import BoardgamePipeline
    pipeline = BoardgamePipeline()

    if no_compiled:
        logger.info("Pipeline    : zero-shot (--no-compiled)")
        return pipeline

    compiled_path = os.path.join("compiled", optimizer, f"boardgame_{variant}.json")
    if os.path.exists(compiled_path):
        logger.info("Pipeline    : compilado (carregando %s)", compiled_path)
        pipeline.load(compiled_path)
    else:
        logger.info(
            "Pipeline    : zero-shot (nenhum programa compilado em '%s')", compiled_path
        )
        logger.info(
            "             Para compilar: uv run scripts/optimize_fewshot.py -d %s", variant
        )

    return pipeline


def run_boardgame_baseline(args, model) -> None:
    from src.baseline import run_baseline_tests
    run_baseline_tests(
        model=model,
        variant=args.dataset,
        split=args.split,
        limit=args.limit,
        output_dir=args.output,
        session_suffix=args.session_suffix,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    from src.dataset import BOARDGAME_VARIANTS

    parser = argparse.ArgumentParser(
        description="DSPy + Defeasible Argumentation — Legal/Causal Reasoning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  uv run main.py                                      Modo legal (todos os casos)
  uv run main.py -l --case-id 1                       Caso jurídico #1

  uv run main.py -b                                   BoardgameQA, DSPy + ASPIC+ (carrega compiled/ se existir)
  uv run main.py -b --no-compiled                     BoardgameQA, força zero-shot
  uv run main.py -b --baseline                        BoardgameQA, LLM direto sem solver
  uv run main.py -b -d Main-depth2 -n 50              50 casos, pipeline DSPy
  uv run main.py -b -d Main-depth2 -n 50 --baseline   50 casos, LLM direto
  uv run main.py -b -d Binary-depth1 -s valid --charts

Compilação (BootstrapFewShot):
  uv run scripts/optimize_fewshot.py                Otimiza Main-depth2, salva em compiled/
  uv run scripts/optimize_fewshot.py -d Main-depth1 Otimiza outra variante
  uv run scripts/optimize_fewshot.py --help         Ver todas as opções de otimização
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

    # --- boardgame options ---
    parser.add_argument(
        "--baseline",
        action="store_true",
        help=(
            "Use raw LLM call instead of DSPy + ASPIC+ solver. "
            "Output goes to outputs/boardgame/baseline/ by default."
        ),
    )
    parser.add_argument(
        "--dataset", "-d",
        choices=BOARDGAME_VARIANTS,
        default="Main-depth2",
        metavar="VARIANT",
        help=f"BoardgameQA variant (default: Main-depth2). Choices: {', '.join(BOARDGAME_VARIANTS)}",
    )
    parser.add_argument(
        "--split", "-s",
        choices=["train", "test", "valid"],
        default="test",
        help="Data split (default: test)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        metavar="N",
        help="Max number of cases to process (default: all)",
    )
    parser.add_argument(
        "--charts", "-c",
        action="store_true",
        help="Generate accuracy charts after benchmark (requires matplotlib)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help=(
            "Output directory for boardgame results. "
            "Defaults to outputs/boardgame/dspy or outputs/boardgame/baseline "
            "depending on --baseline."
        ),
    )

    # --- legal options ---
    parser.add_argument(
        "--case-id",
        type=str,
        metavar="ID",
        help="Specific case ID to analyze (legal mode only)",
    )

    parser.add_argument(
        "--no-compiled",
        action="store_true",
        help=(
            "Ignora programa compilado em compiled/ e executa em zero-shot. "
            "Por padrão, o pipeline carrega automaticamente compiled/<optimizer>/boardgame_<VARIANT>.json se existir."
        ),
    )
    parser.add_argument(
        "--optimizer",
        default="few-shot",
        metavar="NAME",
        help=(
            "Nome do otimizador usado para compilar o programa. "
            "Define de onde carregar (compiled/<NAME>/) e onde salvar resultados "
            "(outputs/boardgame/dspy/compiled/<NAME>/). Padrão: few-shot."
        ),
    )

    # --- utility ---
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Gemini models and exit",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="Max tokens for LM responses (default: 16000)",
    )
    parser.add_argument(
        "--session-suffix",
        default=None,
        metavar="SUFFIX",
        help=(
            "Suffix appended to the Langfuse session_id to differentiate runs. "
            "E.g. --session-suffix sample-1 → session 'Main-depth2-test-zero-shot-sample-1'."
        ),
    )

    args = parser.parse_args()
    load_dotenv()

    # Build a short label for the log filename before setting up logging
    if args.boardgame:
        _mode = "baseline" if args.baseline else "dspy"
        run_label = f"boardgame_{_mode}_{args.dataset}_{args.split}"
    else:
        run_label = f"legal_{args.case_id or 'all'}"
    logger = setup_logging(run_label)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found. Add it to .env")
        sys.exit(1)

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    if args.list_models:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                logger.info("  %s", m.name)
        sys.exit(0)

    # Default to legal mode when no mode flag is given
    if not args.legal and not args.boardgame:
        args.legal = True

    # Resolve default output directory based on mode
    if args.output is None:
        if args.baseline:
            args.output = "outputs/boardgame/baseline"
        else:
            compiled_path = os.path.join("compiled", args.optimizer, f"boardgame_{args.dataset}.json")
            compiled_used = not args.no_compiled and os.path.exists(compiled_path)
            args.output = os.path.join("outputs", "boardgame", "dspy", "compiled", args.optimizer) if compiled_used else "outputs/boardgame/dspy/zero-shot"

    mode_label = "boardgame" if args.boardgame else "legal"
    pipeline_label = "baseline (raw LLM)" if args.baseline else "DSPy + ASPIC+"
    logger.info("=== Pipeline starting ===")
    logger.info("Mode       : %s", mode_label)
    logger.info("Model      : %s", model_name)
    logger.info("Max tokens : %d", args.max_tokens)
    if args.boardgame:
        logger.info("Pipeline   : %s", pipeline_label)
        if not args.baseline:
            compiled_path = os.path.join("compiled", args.optimizer, f"boardgame_{args.dataset}.json")
            compiled_exists = os.path.exists(compiled_path)
            logger.info("Optimizer  : %s", args.optimizer)
            logger.info("Compiled   : %s", compiled_path if compiled_exists and not args.no_compiled else "não (zero-shot)")
        logger.info("Dataset    : %s", args.dataset)
        logger.info("Split      : %s", args.split)
        logger.info("Limit      : %s", args.limit if args.limit is not None else "all")
        logger.info("Output dir : %s", args.output)
    elif args.legal:
        logger.info("Case ID    : %s", args.case_id if args.case_id else "all")

    if args.boardgame:
        if args.baseline:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=args.max_tokens,
                    temperature=0.0,
                ),
            )
            run_boardgame_baseline(args, model)
        else:
            setup_dspy(api_key, model_name, args.max_tokens)
            pipeline = load_boardgame_pipeline(args.dataset, args.optimizer, args.no_compiled, logger)
            run_boardgame_dspy(args, pipeline)
    else:
        setup_dspy(api_key, model_name, args.max_tokens)
        from src.modules import CausalReasoningPipeline
        pipeline = CausalReasoningPipeline()
        run_legal_mode(args, pipeline)


if __name__ == "__main__":
    main()
