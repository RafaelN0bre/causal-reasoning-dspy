"""Dataset com casos que demonstram diferentes padrões de raciocínio causal."""
import json
import os
from typing import Dict, Any, List, Optional, Tuple


BOARDGAME_VARIANTS = [
    "Main-depth1",
    "Main-depth2", 
    "Main-depth3",
    "ZeroConflict-depth2",
    "LowConflict-depth2",
    "HighConflict-depth2",
    "EasyConflict-depth2",
    "DifficultConflict-depth2",
    "SomeDistractors-depth2",
    "ManyDistractors-depth2",
    "KnowledgeLight-depth2",
    "KnowledgeHeavy-depth2",
    "Binary-depth1",
    "Binary-depth2",
    "Binary-depth3",
]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "BoardgameQA")


def load_boardgame_dataset(variant: str = "Main-depth2", split: str = "test") -> List[Dict[str, Any]]:
    """
    Load a BoardgameQA dataset variant.
    
    Args:
        variant: Dataset variant (e.g., "Main-depth2", "ZeroConflict-depth2")
        split: Data split - one of "train", "test", or "valid"
    
    Returns:
        List of test cases, each containing:
        - facts: List of factual statements
        - rules: Game rules as text
        - preferences: Rule preferences
        - goal: Target predicate to prove/disprove
        - label: Expected answer ("proved", "disproved", "unknown")
        - proof: Ground truth explanation
    """
    if variant not in BOARDGAME_VARIANTS:
        raise ValueError(f"Unknown variant: {variant}. Available: {BOARDGAME_VARIANTS}")
    
    if split not in ("train", "test", "valid"):
        raise ValueError(f"Invalid split: {split}. Must be train, test, or valid")
    
    file_path = os.path.join(DATA_DIR, f"BoardgameQA-{variant}", f"{split}.json")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data


def parse_boardgame_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a BoardgameQA case into structured format for the pipeline.
    
    Args:
        case: Raw case from BoardgameQA JSON
    
    Returns:
        Parsed case with:
        - facts: List of factual statements
        - rules: List of rule strings
        - preferences: Rule preference string
        - goal: Target predicate tuple (subject, predicate, object)
        - label: Expected result ("proved"/"disproved"/"unknown")
    """
    facts = case.get("facts", "")
    rules = case.get("rules", "")
    preferences = case.get("preferences", "")
    goal_str = case.get("goal", "()")
    
    goal_tuple = _parse_goal(goal_str)
    
    return {
        "facts": facts,
        "rules": rules,
        "preferences": preferences,
        "goal": goal_tuple,
        "goal_str": goal_str,
        "label": case.get("label", "unknown"),
        "proof": case.get("proof", ""),
        "example": case.get("example", ""),
    }


def _parse_goal(goal_str: str) -> Tuple[str, ...]:
    """Parse goal string like '(swan, swear, woodpecker)' into a tuple."""
    goal_str = goal_str.strip()
    if goal_str.startswith("(") and goal_str.endswith(")"):
        inner = goal_str[1:-1]
        parts = [p.strip() for p in inner.split(",")]
        return tuple(parts)
    return (goal_str,)


GOLDEN_DATASET = [
    {
        "id": 1,
        "name": "Caso da Leucemia (Omissão)",
        "case_text": """
        Uma criança com leucemia (ChLe) não recebeu quimioterapia (Chem) porque seus pais se recusaram a consentir (¬PaCo).
        Os médicos recomendaram fortemente a quimioterapia. A criança não foi tratada e morreu (ChDi).
        Fonte: Baseado em Cassazione penale (2023) 
        """,
        "expected_knowledge_base": {
            "premises": ["ChLe", "¬PaCo"],
            "potential_causes": ["¬PaCo"],
            "target_conclusion": "ChDi",
            "axioms": []
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r0: ChLe => ChDi",
                "r1: PaCo => Chem"
            ],
            "undercutter_rules": [
                "r2: Chem => ¬r0"
            ]
        },
        "expected_causal_result": {
            "is_cause": True,
            "explanation": "A omissão do consentimento (¬PaCo) é uma causa da morte (ChDi). " + 
                        "Se uma intervenção fosse feita adicionando 'PaCo'[cite: 343], " +
                        "um novo argumento justificado 'Chem' seria criado (via r1), " + 
                        "que por sua vez ativaria a regra 'r2' para derrotar 'r0'[cite: 344, 345]. " +
                        "Isso bloquearia a conclusão 'ChDi', provando que '¬PaCo' era causal."
        }
    },
    {
        "id": 2,
        "name": "Dlugash Case (Preemption)",
        "case_text": """
        Dlugash atirou em uma vítima (DlKi), mas Bush já havia atirado antes (BuKi) 
        e a vítima já estava morta (ViDe).
        """,
        "expected_knowledge_base": {
            "premises": ["DlKi", "BuKi", "ViDe"],
            "potential_causes": ["DlKi", "BuKi"],
            "target_conclusion": "ViDe"
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r1: DlKi => ViDe",  # Tiro de Dlugash causa morte
                "r2: BuKi => ViDe"   # Tiro de Bush causa morte
            ],
            "undercutter_rules": [
                "r3: BuKi => ¬r1"    # Tiro prévio de Bush impede causalidade de Dlugash
            ]
        },
        "expected_causal_result": {
            "BuKi": {
                "is_cause": True,
                "explanation": "O tiro de Bush (BuKi) é causa da morte pois foi o primeiro e efetivo."
            },
            "DlKi": {
                "is_cause": False,
                "explanation": "O tiro de Dlugash (DlKi) não é causa da morte pois a vítima já estava morta."
            }
        }
    },
    {
        "id": 3,
        "name": "Celular à Prova D'água (Consumer Law)",
        "case_text": """
        Um celular anunciado como à prova d'água (PhWp) caiu na piscina (PoFa) e parou de funcionar.
        A empresa alega mau uso (MiUs), mas cair na piscina é um uso normal para um celular à prova d'água (NoUs).
        """,
        "expected_knowledge_base": {
            "premises": ["PhWp", "PoFa", "MiUs", "NoUs"],
            "potential_causes": ["PhWp", "PoFa"],
            "target_conclusion": "PrLi"  # Product Liability
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r1: PhWp AND PoFa => PrLi",     # Falha do produto à prova d'água gera responsabilidade
                "r2: MiUs => ¬PrLi"              # Mau uso exclui responsabilidade
            ],
            "undercutter_rules": [
                "r3: NoUs => ¬r2"                # Uso normal impede alegação de mau uso
            ]
        },
        "expected_causal_result": {
            "PhWp": {
                "is_cause": True,
                "explanation": "A característica à prova d'água (PhWp) é causa da responsabilidade " +
                             "pois criou a expectativa de funcionamento na água."
            }
        }
    }
]