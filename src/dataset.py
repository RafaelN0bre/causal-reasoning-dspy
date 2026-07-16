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


LEGAL_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "legal")


def load_legal_dataset(split: str) -> List[Dict[str, Any]]:
    """
    Load a legal causal-analysis dataset split from data/legal/<split>.json.

    Args:
        split: "test" (golden de avaliação, usado por `main.py --legal`) ou
               "train" (compilação few-shot, usado por scripts/optimize_fewshot_legal.py)

    Returns:
        List of labeled cases, each containing:
        - id, name, pattern: identificação e padrão causal do caso
        - case_text: texto do caso com literais entre parênteses e pergunta explícita
        - expected_knowledge_base: premises, potential_causes, target_conclusion
        - expected_causal_model: defeasible_rules, undercutter_rules
        - expected_causal_result: veredito is_cause esperado por causa potencial
    """
    if split not in ("train", "test"):
        raise ValueError(f"Invalid split: {split}. Must be train or test")

    file_path = os.path.join(LEGAL_DATA_DIR, f"{split}.json")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Legal dataset file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Splits disjuntos (cenários distintos) para evitar contaminação treino/avaliação.
# Todos os rótulos são auto-consistentes sob a Definição 4.3; a checagem
# determinística roda em scripts/optimize_fewshot_legal.py --check-only.
GOLDEN_DATASET = load_legal_dataset("test")
LEGAL_TRAIN_DATASET = load_legal_dataset("train")
