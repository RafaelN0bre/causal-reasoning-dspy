"""DSPy Signatures para o pipeline de raciocínio causal baseado em ASPIC+ e Definição 4.3."""
import dspy
from typing import List, Dict, Any


class TextToKnowledgeBase(dspy.Signature):
    """
    Extrai elementos da base de conhecimento do texto do caso, incluindo premissas ordinárias (Kp),
    causas potenciais para teste e a conclusão alvo.
    """
    case_description: str = dspy.InputField(
        desc="Texto completo descrevendo o caso jurídico"
    )
    knowledge_base: str = dspy.OutputField(
        desc="""JSON contendo:
        - premises: Lista de literais (positivos ou negativos) de Kp
        - potential_causes: Lista de fatos para testar como causas
        - target_conclusion: O efeito/dano a ser analisado
        Exemplo: {
            "premises": ["LeucAtv", "¬ParaPres"],
            "potential_causes": ["¬PaCo"],
            "target_conclusion": "ChDi"
        }"""
    )


class ExtractCausalModel(dspy.Signature):
    """
    Extrai tanto regras causais (Rd) quanto regras undercutter que podem derrotá-las.
    Crucial para lidar corretamente com casos de preempção e omissão.
    """
    knowledge_base: str = dspy.InputField(
        desc="A base de conhecimento em JSON do TextToKnowledgeBase"
    )
    case_description: str = dspy.InputField(
        desc="Texto original do caso (para contexto)"
    )
    causal_model: str = dspy.OutputField(
        desc="""JSON contendo:
        - strict_rules: Lista de regras estritas (Rs) que são incontestáveis 
          (ex: "rS0: PaCo -> Lesao")
        - defeasible_rules: Lista de regras causais (Rd) que podem ser derrotadas 
          (ex: "r0: LeucAtv => Obito")
        - undercutter_rules: Lista de regras que podem derrotar outras regras 
          (ex: "r2: Quimio => ¬r0")
        - preferences: Mapa de preferências entre regras, com valores entre 0 e 1
          (ex: {"r0": 0.8, "r2": 0.9})
        Exemplo: {
            "strict_rules": [
                "rS0: PaCo -> Lesao",
                "rS1: Morte -> ¬Vida"
            ],
            "defeasible_rules": [
                "r0: LeucAtv => Obito",
                "r1: ParaPres => Quimio"
            ],
            "undercutter_rules": [
                "r2: Quimio => ¬r0"
            ],
            "preferences": {
                "r0": 0.8,
                "r2": 0.9,
                "r1": 0.7
            }
        }""")


class BuildArgumentationFramework(dspy.Signature):
    """
    Constructs a complete ASPIC+ argumentation framework from the knowledge base
    and rules, optionally adding axioms for causal testing.
    """
    knowledge_base: str = dspy.InputField(
        desc="O JSON da base de conhecimento, contendo 'premises' (Kp) e 'axioms' (Kn)."
    )
    causal_model: str = dspy.InputField(
        desc="O JSON do modelo causal com 'defeasible_rules' e 'undercutter_rules'."
    )
    af_json: str = dspy.OutputField(
        desc="""Complete argumentation framework in JSON format:
        {
            "knowledge": {
                "axioms": ["..."],     # Kn (axiomas)
                "premises": ["..."],    # Kp (premissas ordinárias)
                "rules": {
                    "strict": ["rS0: A -> B", ...],      # Rs (regras estritas)
                    "defeasible": ["r0: A => B", ...],   # Rd (regras derrotáveis)
                    "undercutters": ["r2: C => ¬r0", ...] # Ru (regras undercutter)
                },
                "preferences": {        # Função de preferência (0 a 1)
                    "r0": 0.8,
                    "r2": 0.9
                }
            },
            "arguments": [
                {
                    "id": "A1", 
                    "premises": ["P1"], 
                    "strict_rules": ["rS0"],  # Rs usadas
                    "defeasible_rules": ["r0"],  # Rd usadas
                    "conclusion": "C1",
                    "strength": 0.8  # Força do argumento baseada nas preferências
                },
                ...
            ],
            "attacks": [
                {
                    "attacker": "A2", 
                    "target": "A1", 
                    "type": "undercut",  # ou "rebuttal" para conflito direto
                    "rule": "r0",
                    "succeeds": true  # Indica se o ataque vira uma derrota (defeat)
                                    # baseado nas preferências dos argumentos
                },
                ...
            ],
            "defeats": [
                {
                    "defeater": "A2",
                    "defeated": "A1",
                    "type": "undercut",
                    "explanation": "Argumento A2 (força 0.9) derrota A1 (força 0.8)"
                },
                ...
            ]
        }"""
    )

class AnalyzeCausalTest(dspy.Signature):
    """
    Implements the causal test logic from Definition 4.3, comparing base and test results
    to determine if a potential cause actually qualifies as a cause-in-fact.
    Provides detailed analysis of the causal relationship and the critical points
    of defeat in the argumentation framework.
    """
    potential_cause: str = dspy.InputField(
        desc="The fact φ being tested as a potential cause"
    )
    target_conclusion: str = dspy.InputField(
        desc="The effect/damage ψ being analyzed"
    )
    base_explanations: str = dspy.InputField(
        desc="""JSON list of explanations (minimal winning strategies) from the base AF:
        [
            {
                "arguments": ["A1", "A2"],
                "rules": ["r0", "r1"],
                "premises": ["P1", "P2"]
            },
            ...
        ]"""
    )
    test_grounded_extension: str = dspy.InputField(
        desc="The grounded extension of the modified AF (with ¬φ as axiom)"
    )
    case_description: str = dspy.InputField(
        desc="Original case text (for generating natural language explanation)"
    )
    is_cause: bool = dspy.OutputField(
        desc="True if φ is a cause-in-fact of ψ according to Definition 4.3"
    )
    causation_type: str = dspy.OutputField(
        desc="""O tipo de relação causal identificada:
        - "production": φ diretamente produz ψ
        - "omission": A ausência de φ permite ψ
        - "preemption": φ previne uma cadeia causal alternativa para ψ
        - "supervention": φ sobrepõe outros fatores causais de ψ
        - "none": Quando não há relação causal"""
    )
    defeated_chain: Dict[str, Any] = dspy.OutputField(
        desc="""Análise detalhada da cadeia causal derrotada quando φ é negado:
        {
            "critical_rule": {
                "id": "r0",  # ID da regra crítica
                "content": "LeucAtv => Obito",  # Conteúdo da regra
                "type": "defeasible",  # Tipo da regra (strict/defeasible)
                "defeat_type": "undercut"  # Como a regra foi derrotada
            },
            "affected_arguments": [
                {
                    "id": "A1",  # ID do argumento afetado
                    "conclusion": "Obito",  # Conclusão perdida
                    "strength": 0.8,  # Força do argumento
                    "defeat_explanation": "Derrotado por A2 (0.9) via undercut de r2"
                },
                ...
            ],
            "causal_chain": [
                "LeucAtv",  # Premissa inicial
                "r0: LeucAtv => Obito",  # Regra intermediária
                "Obito"  # Conclusão final
            ]
        }"""
    )
    causal_explanation: str = dspy.OutputField(
        desc="""Explicação detalhada da análise causal, incluindo:
        1. Identificação do tipo de causa (produção, omissão, etc.)
        2. Regras críticas afetadas pela negação de φ
        3. Argumentos derrotados e suas cadeias causais
        4. Justificativa jurídica para classificação como causa-in-fact
        5. Referência a conceitos da Definição 4.3"""
    )