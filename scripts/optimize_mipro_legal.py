"""Script de otimização do pipeline legal (CausalReasoningPipeline) via MIPROv2.

MIPROv2 otimiza tanto as instruções das signatures quanto os exemplos few-shot,
usando busca Bayesiana. É mais poderoso que BootstrapFewShot, mas consome mais
chamadas à API (cada trial reavalia o pipeline completo no valset).

Como o split de teste (data/legal/test.json) é held-out, o valset é extraído do
próprio split de treino: 1 a cada 3 casos (intercalado, para preservar a
cobertura de padrões causais) vai para validação e o restante para treino.

A métrica é a mesma do few-shot (semântica, em três componentes): base de
conhecimento por conjuntos, modelo causal canonizado (independente da numeração
rN) e vereditos da Definição 4.3. Em avaliação retorna a fração de componentes
corretos; no bootstrapping exige os três perfeitos.

O programa compilado é salvo em compiled/mipro/legal.json. Para usar:
    uv run main.py --legal --optimizer mipro
(resultados vão para outputs/legal/compiled/mipro/)

Uso:
    uv run scripts/optimize_mipro_legal.py
    uv run scripts/optimize_mipro_legal.py --auto medium
    uv run scripts/optimize_mipro_legal.py --num-trials 15 --max-bootstrapped 6

Opções:
    --auto              Intensidade da otimização: light, medium, heavy (padrão: light)
    --num-trials        Nº de trials Bayesianos (sobrescreve --auto se fornecido)
    --val-every         1 a cada N casos do treino vira validação (padrão: 3)
    --max-bootstrapped  Demos gerados automaticamente por passo (padrão: 4)
    --max-labeled       Demos rotulados por passo (padrão: 4)
    --num-threads       Threads paralelas de avaliação (padrão: 1 para evitar rate limit)
    --output-dir        Pasta de saída (padrão: compiled/mipro/)
    --check-only        Só verifica a consistência dos datasets (sem LLM) e sai
"""
import os
import sys
import argparse
import logging

# Permite rodar como `uv run scripts/optimize_mipro_legal.py` da raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # O solver loga cada construção de AF em INFO; nos trials isso vira ruído.
    logging.getLogger("ASPIC+").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


def legal_metric(example, prediction, trace=None):
    """Métrica semântica do pipeline legal (idêntica à de optimize_fewshot_legal).

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


def build_examples():
    """Converte o LEGAL_TRAIN_DATASET em dspy.Example (input: case_text)."""
    import dspy
    from src.dataset import LEGAL_TRAIN_DATASET

    return [
        dspy.Example(
            case_text=case["case_text"],
            expected_kb=case["expected_knowledge_base"],
            expected_model=case["expected_causal_model"],
            expected_result=case["expected_causal_result"],
        ).with_inputs("case_text")
        for case in LEGAL_TRAIN_DATASET
    ]


def split_train_val(examples, val_every: int):
    """Separa treino/validação de forma intercalada (1 a cada N vai para o valset),
    preservando a distribuição de padrões causais em ambos os conjuntos."""
    valset = examples[val_every - 1::val_every]
    trainset = [ex for i, ex in enumerate(examples) if (i + 1) % val_every != 0]
    return trainset, valset


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
        description="Otimiza o pipeline legal com MIPROv2 e salva o programa compilado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  uv run scripts/optimize_mipro_legal.py
  uv run scripts/optimize_mipro_legal.py --auto medium
  uv run scripts/optimize_mipro_legal.py --num-trials 15 --max-bootstrapped 6

O programa compilado é salvo em compiled/mipro/legal.json.
Para avaliar: uv run main.py --legal --optimizer mipro
Para forçar zero-shot: uv run main.py --legal --no-compiled
        """,
    )
    parser.add_argument(
        "--auto",
        choices=["light", "medium", "heavy"],
        default="light",
        help="Intensidade da otimização MIPROv2 (padrão: light). light≈10 trials, medium≈20, heavy≈30",
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        default=None,
        metavar="N",
        help="Nº de trials Bayesianos (desativa --auto; requer também --num-candidates)",
    )
    parser.add_argument(
        "--num-candidates",
        type=int,
        default=5,
        metavar="N",
        help="Nº de candidatos de instruções/demos por predictor quando --num-trials é usado (padrão: 5)",
    )
    parser.add_argument(
        "--val-every",
        type=int,
        default=3,
        metavar="N",
        help="1 a cada N casos do treino vai para o valset, intercalado (padrão: 3 → 20 treino / 10 validação)",
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
        "--num-threads",
        type=int,
        default=1,
        metavar="N",
        help="Threads paralelas de avaliação (padrão: 1 para evitar rate limit na free tier)",
    )
    parser.add_argument(
        "--output-dir",
        default="compiled/mipro",
        metavar="DIR",
        help="Diretório de saída para o programa compilado (padrão: compiled/mipro/)",
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
        help="Só verifica a consistência dos datasets (sem LLM) e sai",
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

    logger.info("=== Otimização do pipeline legal (MIPROv2) ===")
    logger.info("Modelo      : %s", model_name)
    logger.info("Auto        : %s", args.auto)
    logger.info("Num trials  : %s", args.num_trials if args.num_trials is not None else f"definido por --auto={args.auto}")
    logger.info("Val every   : %d", args.val_every)
    logger.info("Max bootstrapped demos : %d", args.max_bootstrapped)
    logger.info("Max labeled demos      : %d", args.max_labeled)
    logger.info("Num threads            : %d", args.num_threads)

    import dspy
    os.environ.setdefault(
        "DSPY_CACHEDIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "dspy"),
    )
    lm = dspy.LM(f"gemini/{model_name}", api_key=api_key, max_tokens=args.max_tokens)
    dspy.configure(lm=lm)

    examples = build_examples()
    trainset, valset = split_train_val(examples, args.val_every)
    logger.info("Trainset: %d exemplos | Valset: %d exemplos (test held-out não é usado)",
                len(trainset), len(valset))
    if not trainset or not valset:
        logger.error("Split de treino/validação vazio; ajuste --val-every.")
        sys.exit(1)

    from src.modules import CausalReasoningPipeline
    pipeline = CausalReasoningPipeline()

    from dspy.teleprompt import MIPROv2
    mipro_kwargs = dict(
        metric=legal_metric,
        max_bootstrapped_demos=args.max_bootstrapped,
        max_labeled_demos=args.max_labeled,
        num_threads=args.num_threads,
        verbose=True,
    )
    if args.num_trials is not None:
        # O MIPROv2 exige auto=None quando num_trials/num_candidates são
        # definidos manualmente (senão os valores seriam sobrescritos pelo auto).
        mipro_kwargs["auto"] = None
        mipro_kwargs["num_candidates"] = args.num_candidates
    else:
        mipro_kwargs["auto"] = args.auto
    optimizer = MIPROv2(**mipro_kwargs)

    compile_kwargs = dict(
        trainset=trainset,
        valset=valset,
        requires_permission_to_run=False,
        # O valset aqui é pequeno (dezena de casos): avalia inteiro em cada
        # trial em vez de minibatch (cujo tamanho padrão excederia o valset).
        minibatch=False,
    )
    if args.num_trials is not None:
        compile_kwargs["num_trials"] = args.num_trials

    logger.info("Iniciando compilação MIPROv2 (pode demorar bastante: cada trial reavalia o valset)...")
    compiled = optimizer.compile(pipeline, **compile_kwargs)

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "legal.json")
    compiled.save(out_path)
    logger.info("Programa compilado salvo em: %s", out_path)
    logger.info("Próxima execução: uv run main.py --legal --optimizer mipro")


if __name__ == "__main__":
    main()
