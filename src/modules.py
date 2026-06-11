"""Módulos DSPy implementando o pipeline de raciocínio causal."""
import json
import ast
import logging
from typing import Dict, Any, List, Tuple, Optional

import dspy

# Module logger
logger = logging.getLogger(__name__)
from .signatures import (
    TextToKnowledgeBase, ExtractCausalModel,
    BuildArgumentationFramework, AnalyzeCausalTest,
    BoardgameKBExtraction, BoardgameRuleExtraction,
)
from .solver import ArgumentationFramework


def _try_parse_json(text: str) -> Optional[Dict]:
    """Try multiple strategies to parse JSON from potentially truncated text."""
    if isinstance(text, (dict, list)):
        return text
    
    if not isinstance(text, str):
        return None
    
    strategies = [
        ("strict_json", lambda: json.loads(text)),
        ("extract_braces", lambda: json.loads(_extract_json_braces(text))),
        ("ast_literal_eval", lambda: ast.literal_eval(text)),
        ("fix_truncated", lambda: _fix_and_parse_json(text)),
    ]
    
    for name, parser in strategies:
        try:
            result = parser()
            if result and isinstance(result, dict):
                return result
        except Exception:
            continue
    
    return None


def _extract_json_braces(text: str) -> str:
    """Extract JSON object from text by finding first { and last }."""
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last != -1 and last > first:
        return text[first:last+1]
    return text


def _fix_and_parse_json(text: str) -> Optional[Dict]:
    """Attempt to fix common JSON truncation issues."""
    text = _extract_json_braces(text)
    
    text = text.replace('\n', ' ').replace('\r', '')
    text = ' '.join(text.split())
    
    missing_closes = text.count('{') - text.count('}')
    for _ in range(missing_closes):
        text += '}'
    
    return json.loads(text)


class ArgumentationSolver(dspy.Tool):
    """
    Ferramenta que computa a extensão grounded de um framework ASPIC+.
    
    Esta implementação faz uso específico da semântica grounded por:
    1. Garantia de existência e unicidade (adequado para análise causal)
    2. Natureza cética (apropriado para raciocínio judicial)
    3. Computação eficiente (ponto fixo da função de defesa)
    
    Importante notar que:
    - A extensão grounded pode ser vazio mesmo com argumentos válidos
    - Ciclos podem impedir a aceitação de argumentos relevantes
    - A ordem de aplicação de regras não afeta o resultado final
    
    O uso para análise causal assume que:
    - Argumentos na extensão grounded são epistemicamente justificados
    - Derrotas representam genuínas invalidações causais
    - Ausência na extensão indica dependência causal
    """
    
    def __init__(self):
        """Initialize the solver tool."""
        def solve_af(af_json: str) -> Tuple[str, str, str]:
            """
            Run the solver on a JSON-encoded argumentation framework.

            Args:
                af_json: JSON string containing the complete AF specification

            Returns:
                Tuple containing:
                - grounded_ids: JSON list of argument IDs in the grounded extension
                - explanations: JSON map of argument ID to support sets
                - grounded_conclusions: JSON map of argument ID -> conclusion literal
                  (used to check whether the target predicate is grounded)
            """
            af_data = _try_parse_json(af_json)

            if af_data is None:
                logger.warning("⚠️ Failed to parse AF JSON, using minimal fallback")
                af_data = {
                    "knowledge": {"premises": [], "axioms": [], "rules": {}},
                    "arguments": [],
                    "attacks": [],
                    "defeats": []
                }

            # Ensure required structure exists
            if "knowledge" not in af_data:
                raise ValueError("AF JSON missing 'knowledge' field")
            if "rules" not in af_data["knowledge"]:
                af_data["knowledge"]["rules"] = {}

            # Create AF instance with default empty lists for missing rule types
            af = ArgumentationFramework(
                knowledge_base=af_data["knowledge"],
                causal_model={
                    "defeasible_rules": af_data["knowledge"].get("rules", {}).get("defeasible", []),
                    "undercutter_rules": af_data["knowledge"].get("rules", {}).get("undercutters", [])
                }
            )

            # Compute grounded extension
            grounded, explanations, defeats = af.compute_grounded_extension()

            # Map each grounded argument ID to its conclusion so callers can
            # check whether a specific predicate is derivable without relying
            # on string matching against opaque argument IDs.
            conclusions = {arg_id: af.arguments[arg_id].conclusion for arg_id in grounded}

            return (
                json.dumps(list(grounded)),
                json.dumps(explanations),
                json.dumps(conclusions),
            )

        super().__init__(
            func=solve_af,
            desc="Computes grounded extension and explanations for an argumentation framework"
        )

    def __call__(self, af_json: str) -> Tuple[str, str, str]:
        """
        Run the solver on a JSON-encoded argumentation framework.

        Args:
            af_json: JSON string containing the complete AF specification

        Returns:
            Tuple containing:
            - grounded_ids: JSON list of argument IDs in the grounded extension
            - explanations: JSON map of argument ID to support sets
            - grounded_conclusions: JSON map of argument ID -> conclusion literal
        """
        logger.debug("🔍 Debug: Argumentation Framework JSON (preview): %s",
                     (af_json[:500] + '...') if isinstance(af_json, (str, bytes)) and len(af_json) > 500 else repr(af_json))
        return self.func(af_json)


def negate_fact(fact: str, context: Dict[str, Any], case_text: str) -> str:
    """
    Gera a negação contrafactual adequada para um fato, considerando seu papel
    causal no contexto do caso.
    
    Args:
        fact: O fato a ser negado (ex: "AdminQuimio", "¬ParaPres")
        context: Dicionário com conhecimento do caso (kb, modelo causal)
        case_text: Texto original do caso para análise contextual
    
    Returns:
        str: A negação apropriada do fato considerando o contexto
    
    Exemplos:
        - "AdminQuimio" → "¬AdminQuimio" (omissão de tratamento)
        - "¬ParaPres" → "ParaPres" (prescrição que deveria ter ocorrido)
        - "Obito" → "Sobreviveu" (estado final alternativo)
        - "LeucAtv" → "LeucCont" (condição controlada vs ativa)
    """
    # Remove qualquer negação existente
    is_negative = fact.startswith("¬")
    base_fact = fact[1:] if is_negative else fact
    
    # Mapeamento de pares positivo/negativo para conceitos comuns
    DOMAIN_PAIRS = {
        # Estados clínicos
        "LeucAtv": "LeucCont",  # Leucemia ativa vs controlada
        "Obito": "Sobreviveu",  # Desfecho fatal vs sobrevivência
        
        # Ações médicas
        "AdminQuimio": "¬AdminQuimio",  # Administração vs omissão
        "ParaPres": "¬ParaPres",    # Prescrição vs não prescrição
        "PaCo": "¬PaCo",          # Parada cardíaca vs ausência
        
        # Relações causais
        "ChDi": "¬ChDi",  # Nexo causal vs ausência de nexo
    }
    
    # Verifica se temos um par definido para este fato
    if base_fact in DOMAIN_PAIRS:
        positive = base_fact
        negative = DOMAIN_PAIRS[base_fact]
        # Se o fato original era negativo, retorna o positivo
        return positive if is_negative else negative
    
    # Regra padrão: adiciona ou remove ¬
    return fact[1:] if is_negative else f"¬{fact}"


class CausalReasoningPipeline(dspy.Module):
    """
    Pipeline completo para raciocínio causal em casos jurídicos baseado em ASPIC+.
    
    Este pipeline implementa uma abordagem para análise de causalidade em casos jurídicos
    baseada na semântica argumentativa do ASPIC+. A conexão entre argumentação e causalidade
    é estabelecida através das seguintes suposições fundamentais:
    
    1. Ponte Semântica-Causal:
       - Um fato φ é considerado causa de um efeito ψ se e somente se a introdução
         de ¬φ como axioma remove ψ da extensão grounded do framework
       - Isso mapeia aceitabilidade argumentativa (status dialético) para
         relevância causal (necessidade/suficiência)
    
    2. Suposições Teóricas:
       a) Fechamento sob Reinstanciação:
          - O framework não contém ciclos de ataque
          - Garante existência e unicidade da extensão grounded
          - Necessário para interpretação causal unívoca
    
       b) Preferências como Confiabilidade Epistêmica:
          - Valores de preferência (0 a 1) representam confiabilidade
          - Regras mais preferidas são epistemicamente mais confiáveis
          - Justifica uso de preferências para resolver conflitos
    
       c) Semântica Grounded (Cética):
          - Uso de extensão grounded em vez de preferred/stable
          - Representa o conjunto mínimo de argumentos justificados
          - Apropriado para raciocínio judicial (standard probatório)
    
    Estas suposições permitem tratar a remoção de um argumento da extensão
    grounded como evidência de dependência causal, mas devem ser consideradas
    ao interpretar os resultados."""
    
    def __init__(self):
        """Inicializa os componentes do pipeline."""
        super().__init__()
        
        # Componentes principais DSPy
        self.extract_kb = dspy.ChainOfThought(TextToKnowledgeBase)
        self.extract_model = dspy.ChainOfThought(ExtractCausalModel)
        self.build_af = dspy.ChainOfThought(BuildArgumentationFramework)
        self.analyze_test = dspy.ChainOfThought(AnalyzeCausalTest)
        
        # Ferramenta externa do solver
        self.solver = ArgumentationSolver()

        # Boardgame-specific extraction components
        self.boardgame_extract_kb = dspy.ChainOfThought(BoardgameKBExtraction)
        self.boardgame_extract_rules = dspy.ChainOfThought(BoardgameRuleExtraction)
    
    def forward(self, case_text: str) -> Dict[str, Any]:
        """
        Executa o pipeline completo de análise causal usando argumentação abstrata.
        
        O processo segue estas etapas:
        1. Extração da base de conhecimento (K = Kp ∪ Kn)
        2. Construção do modelo causal (regras estritas e defeasible)
        3. Construção do framework base (status quo)
        4. Teste contrafactual para cada causa potencial
        5. Análise da relevância causal
        
        A análise causal é baseada no seguinte princípio:
        Para cada causa potencial φ e efeito ψ, considera-se φ como causa-in-fact
        de ψ se e somente se:
        1. ψ está na extensão grounded do framework base
        2. Ao adicionar ¬φ como axioma, ψ é removido da extensão grounded
        
        Este teste captura a intuição de sine qua non através da argumentação:
        - Se ¬φ derrota os argumentos que suportam ψ, então
        - φ é necessário para a justificação argumentativa de ψ, logo
        - φ é causalmente relevante para ψ
        
        Args:
            case_text: Descrição em linguagem natural do caso jurídico
        
        Returns:
            Dicionário contendo:
            - Base de conhecimento extraída
            - Modelo causal construído
            - Framework base e sua extensão grounded
            - Resultados dos testes causais
            - Explicações das relações causais identificadas
        
        Note:
            A validade desta análise depende das suposições documentadas
            na docstring da classe sobre fechamento, preferências e
            escolha da semântica grounded.
        """
        # Passo 1: Extrair base de conhecimento
        logger.info("[1/5] Extracting knowledge base via LLM...")
        kb_json = self.extract_kb(
            case_description=case_text
        ).knowledge_base
        kb = _try_parse_json(kb_json)
        if kb is None:
            logger.warning("⚠️ Failed to parse KB JSON, using fallback")
            kb = {"premises": [], "potential_causes": [], "target_conclusion": ""}
        logger.info(
            "[1/5] Knowledge base extracted: premises=%s | potential_causes=%s | target=%s",
            kb.get("premises", []),
            kb.get("potential_causes", []),
            kb.get("target_conclusion", ""),
        )

        # Passo 2: Extrair modelo causal
        logger.info("[2/5] Extracting causal model via LLM...")
        model_json = self.extract_model(
            knowledge_base=kb_json,
            case_description=case_text
        ).causal_model
        model = _try_parse_json(model_json)
        if model is None:
            logger.warning("⚠️ Failed to parse causal model JSON, using fallback")
            model = {"defeasible_rules": [], "undercutter_rules": [], "strict_rules": [], "preferences": {}}
        logger.info(
            "[2/5] Causal model extracted: %d defeasible rules, %d undercutter rules | rules: %s",
            len(model.get("defeasible_rules", [])),
            len(model.get("undercutter_rules", [])),
            model.get("defeasible_rules", []) + model.get("undercutter_rules", []),
        )

        # Passo 3: Construir AF base
        logger.info("[3/5] Building base argumentation framework via LLM...")
        base_af_json = self.build_af(
            knowledge_base=kb_json,
            causal_model=model_json
        ).af_json
        base_af_data = _try_parse_json(base_af_json)
        if base_af_data is None:
            base_af_data = {"knowledge": {"premises": kb.get("premises", []), "axioms": [], "rules": {}}, "arguments": [], "attacks": [], "defeats": []}
        logger.info("[3/5] Base AF built, invoking solver...")

        # Passo 4: Obter resultados base
        logger.info("[4/5] Running solver on base framework...")
        base_grounded, base_explanations, base_conclusions_json = self.solver(base_af_json)
        base_grounded_list = json.loads(base_grounded)
        base_grounded_conclusions = json.loads(base_conclusions_json)  # {id: conclusion}
        logger.info(
            "[4/5] Base grounded extension: %d argument(s) | conclusions: %s",
            len(base_grounded_list),
            list(base_grounded_conclusions.values()) if base_grounded_conclusions
            else "[] (empty — target may be ungrounded)",
        )

        # Passo 5: Testar cada causa potencial
        potential_causes = kb.get("potential_causes", [])
        logger.info("[5/5] Running counterfactual tests for %d potential cause(s): %s", len(potential_causes), potential_causes)
        causal_results = {}
        for cause in potential_causes:
            logger.info("[5/5]   Testing cause: '%s'", cause)

            # Create test AF with contrafactual axiom
            context = {
                "knowledge_base": kb,
                "causal_model": model,
                "base_grounded": base_grounded_list,
                "base_explanations": json.loads(base_explanations)
            }

            negated = negate_fact(cause, context, case_text)
            logger.info("[5/5]     Counterfactual axiom: '%s'", negated)

            test_kb = {
                "axioms": [negated],
                "premises": kb["premises"]
            }

            test_af_json = self.build_af(
                knowledge_base=json.dumps(test_kb),
                causal_model=model_json
            ).af_json

            # Get test results
            test_grounded, _, test_conclusions_json = self.solver(test_af_json)
            test_grounded_list = json.loads(test_grounded)
            test_grounded_conclusions = json.loads(test_conclusions_json)
            logger.info(
                "[5/5]     Counterfactual grounded extension: %d argument(s) | conclusions: %s",
                len(test_grounded_list),
                list(test_grounded_conclusions.values()) if test_grounded_conclusions else "[]",
            )

            # Analyze causation
            try:
                result = self.analyze_test(
                    potential_cause=cause,
                    target_conclusion=kb["target_conclusion"],
                    base_explanations=base_explanations,
                    test_grounded_extension=test_grounded,
                    case_description=case_text
                )
                logger.info(
                    "[5/5]     Result for '%s': is_cause=%s | %s",
                    cause, result.is_cause, result.causal_explanation,
                )
                causal_results[cause] = {
                    "is_cause": result.is_cause,
                    "explanation": result.causal_explanation
                }
            except Exception as e:
                logger.warning(
                    "[5/5]     analyze_test failed for '%s': %s — falling back to solver-based determination",
                    cause, e,
                )
                target_clean = (
                    kb.get("target_conclusion", "")
                    .lower().replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
                )
                base_has_target = any(
                    target_clean in c.lower().replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
                    for c in base_grounded_conclusions.values()
                )
                test_has_target = any(
                    target_clean in c.lower().replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
                    for c in test_grounded_conclusions.values()
                )
                is_cause = base_has_target and not test_has_target
                logger.info(
                    "[5/5]     Fallback result for '%s': is_cause=%s (base_has_target=%s, test_has_target=%s)",
                    cause, is_cause, base_has_target, test_has_target,
                )
                causal_results[cause] = {
                    "is_cause": is_cause,
                    "explanation": f"[solver fallback] base_has_target={base_has_target}, test_has_target={test_has_target}"
                }
        
        return {
            "case_text": case_text,
            "knowledge_base": kb,
            "causal_model": model,
            "base_framework": base_af_data,
            "base_grounded": base_grounded_list,
            "base_grounded_conclusions": base_grounded_conclusions,
            "base_explanations": json.loads(base_explanations),
            "causal_results": causal_results
        }

    def boardgame_forward(self, case_text: str, goal_str: str) -> Dict[str, Any]:
        """
        Simplified forward pass for BoardgameQA benchmarking.

        Unlike the legal causal pipeline, this method asks only one question:
        is the goal provable from the stated facts and rules?  It therefore:
          1. Extracts premises ONLY from stated facts (no potential-cause separation)
          2. Extracts defeasible rules with preference-based strengths (rebuts, not
             undercutters, for preference conflicts)
          3. Runs the solver on the resulting AF
          4. Returns grounded extension conclusions for label determination

        This mode does NOT run counterfactual causal testing — that is specific
        to the legal causal analysis path (`forward()`).

        Args:
            case_text: Full game description (facts + rules + preferences).
            goal_str: Goal predicate string, e.g. '(swan, swear, woodpecker)'.

        Returns:
            Dict with keys matching what `_map_solver_to_label` expects:
              - base_grounded: list of grounded argument IDs
              - base_grounded_conclusions: {arg_id: conclusion}
              - knowledge_base: {"target_conclusion": str, "premises": [...]}
              - causal_results: {} (empty — not applicable for boardgame)
        """
        logger.info("[BG 1/3] Extracting KB for boardgame case (goal='%s')...", goal_str)
        kb_json = self.boardgame_extract_kb(
            case_description=case_text,
            goal=goal_str,
        ).knowledge_base
        kb = _try_parse_json(kb_json)
        if kb is None:
            logger.warning("⚠️ Failed to parse boardgame KB JSON, using fallback")
            kb = {"premises": [], "target_conclusion": ""}
        logger.info(
            "[BG 1/3] KB extracted: premises=%s | target=%s",
            kb.get("premises", []),
            kb.get("target_conclusion", ""),
        )

        logger.info("[BG 2/3] Extracting rules...")
        rules_json = self.boardgame_extract_rules(
            case_description=case_text,
            knowledge_base=kb_json,
        ).causal_model
        rules = _try_parse_json(rules_json)
        if rules is None:
            logger.warning("⚠️ Failed to parse boardgame rules JSON, using fallback")
            rules = {"defeasible_rules": [], "undercutter_rules": [], "preferences": {}}
        logger.info(
            "[BG 2/3] Rules extracted: %d defeasible, %d undercutters | %s",
            len(rules.get("defeasible_rules", [])),
            len(rules.get("undercutter_rules", [])),
            rules.get("defeasible_rules", []) + rules.get("undercutter_rules", []),
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
        grounded_conclusions = {arg_id: af.arguments[arg_id].conclusion for arg_id in grounded}
        logger.info(
            "[BG 3/3] Grounded extension: %d argument(s) | conclusions: %s",
            len(grounded),
            list(grounded_conclusions.values()),
        )

        return {
            "case_text": case_text,
            "knowledge_base": kb,
            "base_grounded": list(grounded),
            "base_grounded_conclusions": grounded_conclusions,
            "causal_results": {},
            # Raw LLM outputs preserved for tracing/debugging
            "_trace": {
                "kb_json_raw": kb_json,
                "rules_json_raw": rules_json,
                "kb_parsed": kb,
                "rules_parsed": rules,
                "grounded_ids": list(grounded),
                "grounded_conclusions": grounded_conclusions,
            },
        }