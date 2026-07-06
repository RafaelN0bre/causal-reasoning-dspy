"""Script de otimização do BoardgamePipeline via BootstrapFewShot.

Executa o otimizador DSPy contra o split de treino do BoardgameQA e salva
o programa compilado em `compiled/boardgame_<VARIANT>.json`.  Na próxima
execução, `main.py` carrega automaticamente esse arquivo.

Uso:
    uv run scripts/optimize_fewshot.py
    uv run scripts/optimize_fewshot.py -d Main-depth1 -n 30
    uv run scripts/optimize_fewshot.py -d ZeroConflict-depth2 --max-demos 4

Opções:
    -d / --variant          Variante do dataset (padrão: Main-depth2)
    -n / --train-limit      Nº máximo de exemplos de treino (padrão: 50)
    --max-bootstrapped      Demos gerados automaticamente por passo (padrão: 3)
    --max-labeled           Demos rotulados manualmente por passo (padrão: 4)
    --output-dir            Pasta de saída (padrão: compiled/few-shot/)
    --val-limit             Nº de exemplos de validação para seleção final (padrão: 20)
"""
import os
import sys
import argparse
import logging

# Permite rodar como `uv run scripts/optimize_fewshot.py` da raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger(__name__)


def boardgame_metric(example, prediction, trace=None) -> float:
    """Métrica de acurácia: 1.0 se o label predito bate com o esperado."""
    expected = str(example.label).strip().lower()
    predicted = str(prediction.get("label", "unknown")).strip().lower()
    return float(expected == predicted)


def build_trainset(variant: str, limit: int):
    """Carrega o split de treino e converte para dspy.Example."""
    import dspy
    from src.dataset import load_boardgame_dataset, parse_boardgame_case

    cases = load_boardgame_dataset(variant, "train")
    if limit:
        cases = cases[:limit]

    trainset = []
    for case in cases:
        parsed = parse_boardgame_case(case)
        case_text = f"Facts: {parsed['facts']}\n\nRules: {parsed['rules']}"
        if parsed["preferences"]:
            case_text += f"\n\nPreferences: {parsed['preferences']}"
        trainset.append(
            dspy.Example(
                case_text=case_text,
                goal_str=parsed["goal_str"],
                label=parsed["label"],
            ).with_inputs("case_text", "goal_str")
        )

    return trainset


def build_valset(variant: str, limit: int):
    """Carrega o split de validação para seleção final do programa."""
    import dspy
    from src.dataset import load_boardgame_dataset, parse_boardgame_case

    try:
        cases = load_boardgame_dataset(variant, "valid")
        if limit:
            cases = cases[:limit]
    except FileNotFoundError:
        return []

    valset = []
    for case in cases:
        parsed = parse_boardgame_case(case)
        case_text = f"Facts: {parsed['facts']}\n\nRules: {parsed['rules']}"
        if parsed["preferences"]:
            case_text += f"\n\nPreferences: {parsed['preferences']}"
        valset.append(
            dspy.Example(
                case_text=case_text,
                goal_str=parsed["goal_str"],
                label=parsed["label"],
            ).with_inputs("case_text", "goal_str")
        )

    return valset


def main() -> None:
    from src.dataset import BOARDGAME_VARIANTS

    parser = argparse.ArgumentParser(
        description="Otimiza BoardgamePipeline com BootstrapFewShot e salva o programa compilado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  uv run scripts/optimize_fewshot.py
  uv run scripts/optimize_fewshot.py -d Main-depth1 -n 30
  uv run scripts/optimize_fewshot.py -d ZeroConflict-depth2 --max-bootstrapped 4 --max-labeled 6

O programa compilado é salvo em compiled/few-shot/boardgame_<VARIANT>.json.
Na próxima execução de `uv run main.py -b`, ele é carregado automaticamente.
Para forçar zero-shot mesmo com arquivo compilado, use: uv run main.py -b --no-compiled
        """,
    )
    parser.add_argument(
        "--variant", "-d",
        choices=BOARDGAME_VARIANTS,
        default="Main-depth2",
        metavar="VARIANT",
        help=f"Variante do BoardgameQA (padrão: Main-depth2). Opções: {', '.join(BOARDGAME_VARIANTS)}",
    )
    parser.add_argument(
        "--train-limit", "-n",
        type=int,
        default=50,
        metavar="N",
        help="Nº máximo de exemplos do split de treino (padrão: 50)",
    )
    parser.add_argument(
        "--val-limit",
        type=int,
        default=20,
        metavar="N",
        help="Nº máximo de exemplos do split de validação (padrão: 20)",
    )
    parser.add_argument(
        "--max-bootstrapped",
        type=int,
        default=4,
        metavar="N",
        help="Demos gerados automaticamente por passo do pipeline (padrão: 4)",
    )
    parser.add_argument(
        "--max-labeled",
        type=int,
        default=4,
        metavar="N",
        help="Demos rotulados manualmente por passo do pipeline (padrão: 4)",
    )
    parser.add_argument(
        "--output-dir",
        default="compiled/few-shot",
        metavar="DIR",
        help="Diretório de saída para o programa compilado (padrão: compiled/few-shot/)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="Máx. tokens para respostas do LM (padrão: 16000)",
    )
    args = parser.parse_args()
    logger = setup_logging()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY não encontrada. Adicione ao .env")
        sys.exit(1)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    logger.info("=== Otimização BoardgamePipeline ===")
    logger.info("Variante    : %s", args.variant)
    logger.info("Modelo      : %s", model_name)
    logger.info("Train limit : %d", args.train_limit)
    logger.info("Val limit   : %d", args.val_limit)
    logger.info("Max bootstrapped demos : %d", args.max_bootstrapped)
    logger.info("Max labeled demos      : %d", args.max_labeled)

    # Configura DSPy
    import dspy
    os.environ.setdefault("DSPY_CACHEDIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "dspy"))
    lm = dspy.LM(f"gemini/{model_name}", api_key=api_key, max_tokens=args.max_tokens)
    dspy.configure(lm=lm)

    # Carrega dados
    logger.info("Carregando trainset...")
    trainset = build_trainset(args.variant, args.train_limit)
    logger.info("Trainset: %d exemplos", len(trainset))

    valset = build_valset(args.variant, args.val_limit)
    if valset:
        logger.info("Valset  : %d exemplos", len(valset))
    else:
        logger.info("Valset  : split 'valid' não encontrado, usando trainset para seleção")
        valset = trainset[:args.val_limit]

    if not trainset:
        logger.error("Nenhum exemplo de treino carregado. Verifique o dataset.")
        sys.exit(1)

    # Instancia pipeline
    from src.boardgame_module import BoardgamePipeline
    pipeline = BoardgamePipeline()

    # Otimiza
    from dspy.teleprompt import BootstrapFewShot
    optimizer = BootstrapFewShot(
        metric=boardgame_metric,
        max_bootstrapped_demos=args.max_bootstrapped,
        max_labeled_demos=args.max_labeled,
    )

    logger.info("Iniciando compilação (pode demorar conforme o tamanho do trainset)...")
    compiled = optimizer.compile(pipeline, trainset=trainset)

    # Salva
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"boardgame_{args.variant}.json")
    compiled.save(out_path)
    logger.info("Programa compilado salvo em: %s", out_path)
    logger.info("Próxima execução: uv run main.py -b -d %s  (carrega automaticamente)", args.variant)


if __name__ == "__main__":
    main()
