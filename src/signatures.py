"""DSPy Signatures para o pipeline de raciocínio causal baseado em ASPIC+ e Definição 4.3."""
import dspy
from typing import List, Dict, Any


class BoardgameKBExtraction(dspy.Signature):
    """
    Extracts knowledge base from a BoardgameQA case.

    Only facts explicitly stated (or directly derivable via a single rule application
    from stated facts) should become premises. Rule antecedents that are NOT mentioned
    as facts must NOT be added as premises — they are simply not true in this game state.
    The goal literal is the target conclusion to check for provability.
    """
    case_description: str = dspy.InputField(
        desc="Full boardgame case: facts, rules, and preferences"
    )
    goal: str = dspy.InputField(
        desc="The goal predicate string, e.g. '(swan, swear, woodpecker)'"
    )
    knowledge_base: str = dspy.OutputField(
        desc="""JSON containing:
        - premises: List of ASPIC+ literals derived ONLY from stated facts
          (e.g. if 'wolf does not take X' is a fact and Rule1 says 'if not X then Y',
          include 'Y' as a premise; do NOT include rule antecedents that have no
          factual basis)
        - target_conclusion: Single ASPIC+ literal representing the goal
        Example: {
            "premises": ["SeahorseSurrenders", "WolfAcquiresPhoto"],
            "target_conclusion": "SwanSwears"
        }"""
    )


class BoardgameRuleExtraction(dspy.Signature):
    """
    Extracts defeasible rules and preference-based defeat structure from a
    BoardgameQA case. Preferences map to rule strength: if Rule5 > Rule4 and
    both conclusions conflict, Rule5's argument defeats Rule4's (rebut), so
    represent it as a direct negation rebut — NOT an undercutter — unless the
    rule conclusion is literally '¬rN'.
    """
    case_description: str = dspy.InputField(
        desc="Full boardgame case: facts, rules, and preferences"
    )
    knowledge_base: str = dspy.InputField(
        desc="The extracted knowledge base JSON"
    )
    causal_model: str = dspy.OutputField(
        desc="""JSON with:
        - defeasible_rules: Rules that CAN be defeated. Format: 'rN: A AND B => C'
          If a rule concludes the NEGATION of another rule's conclusion (rebut),
          encode it directly, e.g. 'r5: AnimalInvests => ¬SwanSwears'.
          Only use '¬rN' form (undercutter) when the rule explicitly invalidates
          the applicability of rule rN.
        - undercutter_rules: Rules whose conclusion is '¬rN' (undercut rule rN).
        - preferences: Map rule IDs to float strengths (0-1). Higher-priority rules
          get higher values so they win rebut battles.
        Example: {
            "defeasible_rules": [
                "r4: SeahorseSurrenders AND WolfAcquiresPhoto => SwanSwears",
                "r5: AnimalInvests => ¬SwanSwears"
            ],
            "undercutter_rules": [],
            "preferences": {"r4": 0.5, "r5": 0.9}
        }"""
    )



class TextToKnowledgeBase(dspy.Signature):
    """
    Extrai elementos da base de conhecimento do texto do caso, incluindo premissas ordinárias (Kp),
    causas potenciais para teste e a conclusão alvo.

    Convenções obrigatórias:
    1. Literais: use EXATAMENTE os símbolos entre parênteses no texto do caso
       (ex.: se o texto diz "se recusaram a consentir (¬X)", o literal é "¬X").
       NUNCA invente, traduza ou renomeie literais.
    2. premises: todos os fatos afirmados como verdadeiros no caso, incluindo
       alegações das partes, na forma sintática exata (com ¬ quando negativo).
       Registre cada alegação com a polaridade com que foi alegada (alegação de
       mau uso vira 'MiUs', nunca '¬MiUs'), mesmo que outra premissa a conteste.
       EXCEÇÃO: não inclua como premissa um evento que só não ocorreu por causa
       de uma das causas potenciais (ex.: o tratamento não realizado por causa
       de uma recusa) — esse evento pertence à cadeia contrafactual das regras.
    3. potential_causes: SUBCONJUNTO de premises — apenas os fatos que a
       pergunta do caso ("Pergunta-se: ...") questiona como possíveis causas.
    4. target_conclusion: o literal do efeito/dano na pergunta do caso.
       O alvo NUNCA aparece em premises, mesmo que o texto narre que ocorreu:
       ele deve ser derivado pelas regras causais.
    """
    case_description: str = dspy.InputField(
        desc="Texto completo descrevendo o caso jurídico"
    )
    knowledge_base: str = dspy.OutputField(
        desc="""JSON contendo:
        - premises: Lista de literais (positivos ou negativos) de Kp
        - potential_causes: Lista de fatos de Kp para testar como causas (subconjunto de premises)
        - target_conclusion: O efeito/dano a ser analisado (nunca presente em premises)
        Exemplo: {
            "premises": ["FaOc", "¬AgIn", "TeSt"],
            "potential_causes": ["¬AgIn"],
            "target_conclusion": "DaRe"
        }"""
    )


class ExtractCausalModel(dspy.Signature):
    """
    Extrai tanto regras causais (Rd) quanto regras undercutter que podem derrotá-las.
    Crucial para lidar corretamente com casos de preempção e omissão.

    Convenções obrigatórias:
    1. Use somente literais da base de conhecimento e literais entre parênteses
       no texto do caso; nunca invente literais novos. Os literais dos exemplos
       destas instruções (Doe, Con, Trat, Mor, Ac1, Ac2, JaOc, Res, FaB1, FaB2,
       AlEx, FaNe) são fictícios: NUNCA os use num caso real.
    2. Formato de regra: 'rN: Ant1 AND Ant2 => Cons'. Antecedentes múltiplos
       são separados EXCLUSIVAMENTE por ' AND ' — NUNCA por vírgula.
    3. O alvo (target_conclusion) DEVE ser derivável das premissas pelas regras
       no mundo factual: inclua pelo menos uma regra 'premissa(s) => alvo'.
    4. strict_rules: deixe [] salvo definições logicamente incontestáveis.
    5. Padrão de OMISSÃO (a causa potencial é um fato negativo ¬X): o literal
       negativo ¬X NÃO aparece em NENHUMA regra. Modele:
       (i) a regra que deriva o alvo do estado de fato;
       (ii) a cadeia que parte do literal POSITIVO X (ela só dispara no mundo
            contrafactual em que X vale, mesmo que X não seja premissa);
       (iii) o undercutter '¬rN' em que o fim dessa cadeia derrota (i).
       Ex.: premissas ["Doe", "¬Con"], alvo "Mor":
         defeasible_rules: ["r0: Doe => Mor", "r1: Con => Trat"]
         undercutter_rules: ["r2: Trat => ¬r0"]
       A cadeia contrafactual DEVE terminar em undercutter contra a regra do
       alvo ('r2: Trat => ¬r0'), NUNCA em regra que conclui a negação do alvo
       (ERRADO: 'r2: Trat => ¬Mor').
       PROIBIDO usar o literal negativo ¬X em qualquer regra, seja como
       antecedente, seja em undercutter (ERRADO: 'r3: ¬Con => ¬r1'). Exatamente
       as 3 regras acima bastam — nenhuma regra extra ou redundante.
    6. Padrão de PREEMPÇÃO (duas causas concorrentes para o mesmo alvo): cada
       causa recebe sua própria regra '=> alvo'; o fato que mostra que a causa
       preemptada chegou tarde demais undercutta a regra dela.
       Ex.: premissas ["Ac1", "Ac2", "JaOc"], alvo "Res":
         defeasible_rules: ["r0: Ac1 => Res", "r1: Ac2 => Res"]
         undercutter_rules: ["r2: JaOc => ¬r0"]  # Ac1 chegou tarde: JaOc undercutta r0
    7. Padrão de EXCLUDENTE (uma alegação tenta afastar o alvo): a alegação
       recebe uma regra '=> ¬alvo'; o fato que a neutraliza recebe um
       undercutter contra essa regra.
       Ex.: premissas ["FaB1", "FaB2", "AlEx", "FaNe"], alvo "Res",
       causas potenciais ["FaB1", "FaB2"]:
         defeasible_rules: ["r0: FaB1 AND FaB2 => Res", "r1: AlEx => ¬Res"]
         undercutter_rules: ["r2: FaNe => ¬r1"]
    8. preferences: dê aos undercutters preferência maior ou igual à das regras
       que eles atacam.
    """
    knowledge_base: str = dspy.InputField(
        desc="A base de conhecimento em JSON do TextToKnowledgeBase"
    )
    case_description: str = dspy.InputField(
        desc="Texto original do caso (para contexto)"
    )
    causal_model: str = dspy.OutputField(
        desc="""JSON contendo:
        - strict_rules: Lista de regras estritas (Rs) incontestáveis; normalmente []
        - defeasible_rules: Lista de regras causais (Rd) que podem ser derrotadas
          (ex: "r0: Doe => Mor")
        - undercutter_rules: Lista de regras que podem derrotar outras regras
          (ex: "r2: Trat => ¬r0")
        - preferences: Mapa de preferências entre regras, com valores entre 0 e 1
          (ex: {"r0": 0.8, "r2": 0.9})
        Exemplo: {
            "strict_rules": [],
            "defeasible_rules": [
                "r0: Doe => Mor",
                "r1: Con => Trat"
            ],
            "undercutter_rules": [
                "r2: Trat => ¬r0"
            ],
            "preferences": {
                "r0": 0.8,
                "r1": 0.7,
                "r2": 0.9
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