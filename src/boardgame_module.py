"""Módulo DSPy compilável para benchmark BoardgameQA.

Este módulo expõe `BoardgamePipeline`, um `dspy.Module` cuja forward está
estruturada como ponto de entrada para os otimizadores do DSPy
(BootstrapFewShot, MIPROv2, etc.).

Diferenças em relação ao `CausalReasoningPipeline.boardgame_forward`:
- `forward` é o entry-point padrão, o que permite compilação.
- Retorna um dict compatível com `run_boardgame_tests` (mesmas chaves).
- Expõe `boardgame_forward` como alias para backward-compat.

Uso em produção (com programa compilado):
    pipeline = BoardgamePipeline()
    pipeline.load("compiled/boardgame_Main-depth2.json")

Uso zero-shot:
    pipeline = BoardgamePipeline()
"""
import json
import logging
from typing import Any, Dict, Optional, Tuple, List

import dspy

from .signatures import BoardgameKBExtraction, BoardgameRuleExtraction
from .solver import ArgumentationFramework
from .modules import _try_parse_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label mapping (importada de pipeline.py produziria import circular, então
# está inlined aqui — é uma função pura sem side-effects)
# ---------------------------------------------------------------------------

def _map_label(
    grounded_conclusions: Dict[str, str],
    base_grounded: List[str],
    goal_str: str,
    target_conclusion: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """
    Mapeia conclusões da extensão grounded para o label BoardgameQA.

    Retorna (label, trace) onde label ∈ {"proved", "disproved", "unknown"}.
    """
    goal_clean = goal_str.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()
    target_clean = target_conclusion.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()

    neg_prefixes = ("not", "¬", "neg_", "neg")

    def _is_negation(lit: str) -> bool:
        return any(lit.startswith(p) for p in neg_prefixes)

    def _base(lit: str) -> str:
        for p in neg_prefixes:
            if lit.startswith(p):
                return lit[len(p):]
        return lit

    trace: Dict[str, Any] = {
        "goal_clean": goal_clean,
        "target_clean": target_clean,
        "grounded_conclusions_list": list(grounded_conclusions.values()),
        "num_grounded_args": len(base_grounded),
        "decision_reason": "",
    }

    if grounded_conclusions:
        for arg_id, conclusion in grounded_conclusions.items():
            conc = conclusion.replace("(", "").replace(")", "").replace(",", "").replace(" ", "").lower()
            conc_base = _base(conc)
            conc_negated = _is_negation(conc)
            for needle in filter(None, [goal_clean, target_clean]):
                needle_base = _base(needle)
                if conc_base == needle_base or needle_base in conc_base or conc_base in needle_base:
                    label = "disproved" if conc_negated else "proved"
                    trace["decision_reason"] = (
                        f"conclusion '{conclusion}' (arg {arg_id}) matched '{needle}'; "
                        f"negated={conc_negated} → {label}"
                    )
                    return label, trace

        trace["decision_reason"] = (
            f"no grounded conclusion matched goal='{goal_str}' or target='{target_conclusion}'. "
            f"Grounded: {list(grounded_conclusions.values())}"
        )
        return "unknown", trace

    # Fallback: ID string matching
    neg_prefixes_goal = (f"not{goal_clean}", f"¬{goal_clean}", f"neg_{goal_clean}", f"neg{goal_clean}")
    for arg in base_grounded:
        arg_lower = arg.lower()
        if any(arg_lower.startswith(pfx) or pfx in arg_lower for pfx in neg_prefixes_goal):
            trace["decision_reason"] = f"ID fallback: '{arg}' matched negation of goal"
            return "disproved", trace
        if goal_clean in arg_lower:
            trace["decision_reason"] = f"ID fallback: '{arg}' contains goal"
            return "proved", trace

    trace["decision_reason"] = "ID fallback: no argument ID matched goal"
    return "unknown", trace


# ---------------------------------------------------------------------------
# Módulo principal
# ---------------------------------------------------------------------------

class BoardgamePipeline(dspy.Module):
    """
    Pipeline DSPy compilável para o benchmark BoardgameQA.

    Realiza extração de KB e regras via LLM, resolve o framework de
    argumentação ASPIC+ via solver determinístico e mapeia o resultado
    para um label ("proved" / "disproved" / "unknown").

    Por usar `forward` como entry-point, este módulo pode ser otimizado
    com qualquer teleprompter DSPy (BootstrapFewShot, MIPROv2, etc.).

    Exemplo — carregar programa compilado:
        pipeline = BoardgamePipeline()
        pipeline.load("compiled/boardgame_Main-depth2.json")
        result = pipeline(case_text=..., goal_str=...)
        print(result["label"])  # "proved" / "disproved" / "unknown"
    """

    def __init__(self) -> None:
        super().__init__()
        self.extract_kb = dspy.ChainOfThought(BoardgameKBExtraction)
        self.extract_rules = dspy.ChainOfThought(BoardgameRuleExtraction)

    def forward(self, case_text: str, goal_str: str) -> Dict[str, Any]:
        """
        Executa o pipeline completo para um caso BoardgameQA.

        Args:
            case_text: Texto do caso (Facts + Rules + Preferences).
            goal_str: Goal a provar/refutar, ex: "(swan, swear, woodpecker)".

        Returns:
            Dicionário com:
            - label              : "proved" | "disproved" | "unknown"
            - base_grounded      : lista de IDs de argumentos na extensão grounded
            - base_grounded_conclusions : {arg_id: conclusion}
            - knowledge_base     : {"premises": [...], "target_conclusion": "..."}
            - causal_results     : {} (não aplicável para boardgame)
            - _trace             : dados internos para debugging / JSONL trace
        """
        logger.info("[BG 1/3] Extracting KB (goal='%s')...", goal_str)
        kb_json = self.extract_kb(
            case_description=case_text,
            goal=goal_str,
        ).knowledge_base
        kb = _try_parse_json(kb_json)
        if kb is None:
            logger.warning("Failed to parse boardgame KB JSON, using fallback")
            kb = {"premises": [], "target_conclusion": ""}
        logger.info(
            "[BG 1/3] KB: premises=%s | target=%s",
            kb.get("premises", []),
            kb.get("target_conclusion", ""),
        )

        logger.info("[BG 2/3] Extracting rules...")
        rules_json = self.extract_rules(
            case_description=case_text,
            knowledge_base=kb_json,
        ).causal_model
        rules = _try_parse_json(rules_json)
        if rules is None:
            logger.warning("Failed to parse boardgame rules JSON, using fallback")
            rules = {"defeasible_rules": [], "undercutter_rules": [], "preferences": {}}
        logger.info(
            "[BG 2/3] Rules: %d defeasible, %d undercutters",
            len(rules.get("defeasible_rules", [])),
            len(rules.get("undercutter_rules", [])),
        )

        logger.info("[BG 3/3] Building AF and running solver...")
        af_kb = {
            "premises": kb.get("premises", []),
            "axioms": [],
            "preferences": rules.get("preferences", {}),
        }
        af = ArgumentationFramework(
            knowledge_base=af_kb,
            causal_model={
                "defeasible_rules": rules.get("defeasible_rules", []),
                "undercutter_rules": rules.get("undercutter_rules", []),
            },
        )
        grounded, _, _ = af.compute_grounded_extension()
        grounded_conclusions = {
            arg_id: af.arguments[arg_id].conclusion for arg_id in grounded
        }
        logger.info(
            "[BG 3/3] Grounded: %d args | conclusions: %s",
            len(grounded),
            list(grounded_conclusions.values()),
        )

        label, label_trace = _map_label(
            grounded_conclusions=grounded_conclusions,
            base_grounded=list(grounded),
            goal_str=goal_str,
            target_conclusion=kb.get("target_conclusion", ""),
        )
        logger.info("[BG] label=%s | reason: %s", label, label_trace.get("decision_reason", ""))

        return {
            "label": label,
            "base_grounded": list(grounded),
            "base_grounded_conclusions": grounded_conclusions,
            "knowledge_base": kb,
            "causal_results": {},
            "_trace": {
                "kb_json_raw": kb_json,
                "rules_json_raw": rules_json,
                "kb_parsed": kb,
                "rules_parsed": rules,
                "grounded_ids": list(grounded),
                "grounded_conclusions": grounded_conclusions,
                "label_trace": label_trace,
            },
        }

    def boardgame_forward(self, case_text: str, goal_str: str) -> Dict[str, Any]:
        """Alias de forward() para compatibilidade com run_boardgame_tests."""
        return self(case_text=case_text, goal_str=goal_str)
