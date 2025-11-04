"""DSPy Signatures for the causal reasoning pipeline."""
import dspy


class TextToFacts(dspy.Signature):
    """Converts a case description into structured facts and events."""
    
    case_description: str = dspy.InputField(desc="Texto completo do caso de direito do consumidor.")
    structured_facts: str = dspy.OutputField(
        desc="Lista de fatos atômicos separados por vírgula, ex: 'Produto_Defeituoso, Consumidor_Reclamou, Empresa_Nao_Respondeu'"
    )


class FactsToRules(dspy.Signature):
    """Identifies potential defeasible causal rules from facts."""
    
    structured_facts: str = dspy.InputField(desc="Lista de fatos atômicos separados por vírgula.")
    causal_rules: str = dspy.OutputField(
        desc="Lista de regras causais no formato 'r1: [premise1, premise2] => conclusion', uma por linha."
    )


class GenerateArgumentsAndAttacks(dspy.Signature):
    """Generates arguments (chains) and identifies attacks (rebut, undercut)."""
    
    structured_facts: str = dspy.InputField(desc="Lista de fatos atômicos.")
    causal_rules: str = dspy.InputField(desc="Lista de regras defeasible.")
    target_conclusion: str = dspy.InputField(desc="Conclusão alvo (ex: 'Dever_Reparo').")
    arguments_and_attacks: str = dspy.OutputField(
        desc="JSON com formato {\"arguments\": [{\"id\": \"A1\", \"premises\": [...], \"conclusion\": \"...\"}], \"attacks\": [{\"attacker\": \"A2\", \"target\": \"A1\", \"type\": \"undercut\"}]}"
    )


class CausalJudgement(dspy.Signature):
    """Produces a causal judgment given a justified argument and its support set."""
    
    justified_argument: str = dspy.InputField(desc="Argumento identificado como justificado pelo solver.")
    support_set: str = dspy.InputField(desc="Conjunto mínimo de fatos/argumentos que sustentam a justificativa.")
    potential_cause: str = dspy.InputField(desc="O fato que estamos avaliando como causa-em-fato.")
    case_description: str = dspy.InputField(desc="Texto original do caso.")
    causal_explanation: str = dspy.OutputField(
        desc="Explicação detalhada se potential_cause é (ou não) causa-em-fato e por quê, com base no support_set."
    )
