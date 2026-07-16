"""Script de otimização do pipeline legal (CausalReasoningPipeline) via BootstrapFewShot.

Compila os passos de extração do pipeline legal contra o LEGAL_TRAIN_DATASET
(dataset rotulado, disjunto do GOLDEN_DATASET para evitar contaminação
treino/avaliação) usando uma métrica semântica com três componentes:
  - base de conhecimento: conjuntos de premissas/causas potenciais e alvo
  - modelo causal: regras canonizadas, independentes da numeração rN
  - vereditos causais: is_cause por causa esperada (Definição 4.3)

Antes de compilar, verifica deterministicamente (sem LLM) que cada rótulo do
dataset é auto-consistente: o alvo é derivável no AF base e os vereditos
esperados são reproduzidos pelo solver.

O programa compilado é salvo em compiled/<optimizer>/legal.json. Na próxima
execução de `uv run main.py --legal`, ele é carregado automaticamente
(use --no-compiled para forçar zero-shot).

Uso:
    uv run scripts/optimize_fewshot_legal.py
    uv run scripts/optimize_fewshot_legal.py -n 6 --max-bootstrapped 3
    uv run scripts/optimize_fewshot_legal.py --check-only

Opções:
    -n / --train-limit      Nº máximo de exemplos de treino (padrão: todos)
    --max-bootstrapped      Demos gerados automaticamente por passo (padrão: 4)
    --max-labeled           Demos rotulados por passo (padrão: 4)
    --output-dir            Pasta de saída (padrão: compiled/few-shot/)
    --check-only            Só verifica a consistência do dataset e sai
"""
import os
import sys
import argparse
import logging

# Permite rodar como `uv run scripts/optimize_fewshot_legal.py` da raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # O solver loga cada construção de AF em INFO; na checagem de consistência
    # e na compilação isso vira ruído.
    logging.getLogger("ASPIC+").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


def legal_metric(example, prediction, trace=None):
    """Métrica semântica do pipeline legal.

    Retorna a fração de componentes corretos (kb, modelo causal, vereditos)
    em avaliação, e exige os três perfeitos durante o bootstrapping (trace
    não-nulo), para que só execuções integralmente corretas virem demos.
    """
    from src.pipeline import _canonical_causal_model

    prediction = prediction or {}

    kb_got = prediction.get("knowledge_base") or {}
    kb_exp = example.expected_kb
    kb_ok = (
        set(kb_got.get("premises", [])) == set(kb_exp.get("premises", []))
        and set(kb_got.get("potential_causes", [])) == set(kb_exp.get("potential_causes", []))
        and kb_got.get("target_conclusion") == kb_exp.get("target_conclusion")
    )

    model_ok = (
        _canonical_causal_model(prediction.get("causal_model") or {})
        == _canonical_causal_model(example.expected_model)
    )

    results_got = prediction.get("causal_results") or {}
    verdicts_ok = all(
        results_got.get(cause, {}).get("is_cause") == (
            expected["is_cause"] if isinstance(expected, dict) else expected
        )
        for cause, expected in example.expected_result.items()
    )

    score = (float(kb_ok) + float(model_ok) + float(verdicts_ok)) / 3.0
    if trace is not None:
        return score == 1.0
    return score


def build_trainset(limit=None):
    """Converte o LEGAL_TRAIN_DATASET em dspy.Example (input: case_text)."""
    import dspy
    from src.dataset import LEGAL_TRAIN_DATASET

    cases = LEGAL_TRAIN_DATASET[:limit] if limit else LEGAL_TRAIN_DATASET
    return [
        dspy.Example(
            case_text=case["case_text"],
            expected_kb=case["expected_knowledge_base"],
            expected_model=case["expected_causal_model"],
            expected_result=case["expected_causal_result"],
        ).with_inputs("case_text")
        for case in cases
    ]


def check_dataset_consistency(logger) -> bool:
    """Verifica, sem LLM, que cada rótulo dos splits train e test é
    auto-consistente sob a Definição 4.3 (solver sobre KB+modelo esperados)."""
    from src.dataset import GOLDEN_DATASET, LEGAL_TRAIN_DATASET
    from src.solver import ArgumentationFramework
    from src.modules import negate_fact

    def grounded_conclusions(premises, axioms, model):
        af = ArgumentationFramework(
            knowledge_base={
                "premises": premises,
                "axioms": axioms,
                "preferences": model.get("preferences", {}),
            },
            causal_model={
                "strict_rules": model.get("strict_rules", []),
                "defeasible_rules": model.get("defeasible_rules", []),
                "undercutter_rules": model.get("undercutter_rules", []),
            },
        )
        grounded, _, _ = af.compute_grounded_extension()
        return {af.arguments[arg_id].conclusion for arg_id in grounded}

    ok = True
    total = 0
    for split, dataset in (("train", LEGAL_TRAIN_DATASET), ("test", GOLDEN_DATASET)):
        for case in dataset:
            total += 1
            kb = case["expected_knowledge_base"]
            model = case["expected_causal_model"]
            target = kb["target_conclusion"]
            premises = kb["premises"]

            base = grounded_conclusions(premises, [], model)
            if target not in base:
                logger.error(
                    "[%s] Caso %s (%s): alvo '%s' NÃO é derivável no AF base — rótulo inconsistente.",
                    split, case["id"], case["name"], target,
                )
                ok = False
                continue

            for cause, expected in case["expected_causal_result"].items():
                exp = expected["is_cause"] if isinstance(expected, dict) else expected
                test = grounded_conclusions(premises, [negate_fact(cause, {}, "")], model)
                is_cause = target not in test
                if is_cause != exp:
                    logger.error(
                        "[%s] Caso %s (%s): veredito do solver para '%s' é %s, mas o rótulo diz %s.",
                        split, case["id"], case["name"], cause, is_cause, exp,
                    )
                    ok = False

    if ok:
        logger.info("Datasets consistentes: %d casos (train+test) verificados contra o solver.", total)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Otimiza o pipeline legal com BootstrapFewShot e salva o programa compilado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  uv run scripts/optimize_fewshot_legal.py
  uv run scripts/optimize_fewshot_legal.py -n 6 --max-bootstrapped 3
  uv run scripts/optimize_fewshot_legal.py --check-only

O programa compilado é salvo em compiled/few-shot/legal.json.
Na próxima execução de `uv run main.py --legal`, ele é carregado automaticamente.
Para forçar zero-shot mesmo com arquivo compilado: uv run main.py --legal --no-compiled
        """,
    )
    parser.add_argument(
        "--train-limit", "-n",
        type=int,
        default=None,
        metavar="N",
        help="Nº máximo de exemplos do LEGAL_TRAIN_DATASET (padrão: todos)",
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
        help="Demos rotulados por passo do pipeline (padrão: 4)",
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
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Só verifica a consistência do dataset (sem LLM) e sai",
    )
    args = parser.parse_args()
    logger = setup_logging()

    # Checagem determinística dos rótulos antes de gastar chamadas de LLM
    if not check_dataset_consistency(logger):
        logger.error("Dataset inconsistente; corrija os rótulos antes de compilar.")
        sys.exit(1)
    if args.check_only:
        return

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY não encontrada. Adicione ao .env")
        sys.exit(1)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    logger.info("=== Otimização do pipeline legal ===")
    logger.info("Modelo      : %s", model_name)
    logger.info("Train limit : %s", args.train_limit if args.train_limit else "todos")
    logger.info("Max bootstrapped demos : %d", args.max_bootstrapped)
    logger.info("Max labeled demos      : %d", args.max_labeled)

    # Configura DSPy
    import dspy
    os.environ.setdefault(
        "DSPY_CACHEDIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "dspy"),
    )
    lm = dspy.LM(f"gemini/{model_name}", api_key=api_key, max_tokens=args.max_tokens)
    dspy.configure(lm=lm)

    trainset = build_trainset(args.train_limit)
    logger.info("Trainset: %d exemplos", len(trainset))
    if not trainset:
        logger.error("Nenhum exemplo de treino carregado.")
        sys.exit(1)

    from src.modules import CausalReasoningPipeline
    pipeline = CausalReasoningPipeline()

    from dspy.teleprompt import BootstrapFewShot
    optimizer = BootstrapFewShot(
        metric=legal_metric,
        max_bootstrapped_demos=args.max_bootstrapped,
        max_labeled_demos=args.max_labeled,
    )

    logger.info("Iniciando compilação (cada exemplo executa o pipeline completo)...")
    compiled = optimizer.compile(pipeline, trainset=trainset)

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "legal.json")
    compiled.save(out_path)
    logger.info("Programa compilado salvo em: %s", out_path)
    logger.info("Próxima execução: uv run main.py --legal  (carrega automaticamente)")


if __name__ == "__main__":
    main()
