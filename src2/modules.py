"""Módulos DSPy implementando o pipeline de raciocínio causal."""
import json
import ast
import logging
from typing import Dict, Any, List, Tuple

import dspy

# Module logger
logger = logging.getLogger(__name__)
from .signatures import (
    TextToKnowledgeBase, ExtractCausalModel,
    BuildArgumentationFramework, AnalyzeCausalTest
)
from .solver import ArgumentationFramework


class ArgumentationSolver(dspy.Tool):
    """
    Ferramenta que computa a extensão grounded de um framework ASPIC+.
    
    Esta implementação faz uso específico da semântica grounded por:
    1. Garantia de existência e unicidade (adequado para análise causal)
    2. Natureza cética (apropriado para raciocínio judicial)
    3. Computação eficiente (ponto fixo da função de defesa)
    
    Importante notar que:
    - A extensão grounded pode ser vazia mesmo com argumentos válidos
    - Ciclos podem impedir a aceitação de argumentos relevantes
    - A ordem de aplicação de regras não afeta o resultado final
    
    O uso para análise causal assume que:
    - Argumentos na extensão grounded são epistemicamente justificados
    - Derrotas representam genuínas invalidações causais
    - Ausência na extensão indica dependência causal
    """
    
    def __init__(self):
        """Initialize the solver tool."""
        def solve_af(af_json: str) -> Tuple[str, str]:
            """
            Run the solver on a JSON-encoded argumentation framework.
            
            Args:
                af_json: JSON string containing the complete AF specification
            
            Returns:
                Tuple containing:
                - grounded_extension: JSON string with list of argument IDs
                - explanations: JSON string with map of argument ID to support sets
            """
            # Parse the AF JSON with robust error handling.
            # Accept already-parsed objects (defensive) or try JSON parsing.
            if isinstance(af_json, (dict, list)):
                af_data = af_json
            else:
                # First attempt: strict JSON
                try:
                    af_data = json.loads(af_json)
                except json.JSONDecodeError as json_err:
                    # Second attempt: try to extract a JSON-like substring
                    first = af_json.find('{')
                    last = af_json.rfind('}')
                    candidate = None
                    if first != -1 and last != -1 and last > first:
                        candidate = af_json[first:last+1]
                        try:
                            af_data = json.loads(candidate)
                        except Exception:
                            af_data = None
                    else:
                        af_data = None

                    # Third attempt: try ast.literal_eval on either full string or candidate
                    if af_data is None:
                        tried = []
                        for text in (candidate, af_json):
                            if not text:
                                continue
                            try:
                                tried.append(('ast_literal_eval', text[:80]))
                                obj = ast.literal_eval(text)
                                if isinstance(obj, (dict, list)):
                                    af_data = obj
                                    break
                            except Exception as e_ast:
                                # remember last exception for reporting
                                last_exc = e_ast

                    if af_data is None:
                        # Provide helpful debug context and re-raise the original JSON error
                        print(f"❌ JSON decode error: {str(json_err)}")
                        print("--- AF preview (truncated) ---")
                        preview = af_json[:400] + "..." if len(af_json) > 400 else af_json
                        print(preview)
                        if 'last_exc' in locals():
                            print("--- ast.literal_eval error ---")
                            print(repr(last_exc))
                        raise json_err
            
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
            
            return (
                json.dumps(list(grounded)),
                json.dumps(explanations)
            )  # We don't need to return defeats for now
        
        super().__init__(
            func=solve_af,
            desc="Computes grounded extension and explanations for an argumentation framework"
        )
    
    def __call__(self, af_json: str) -> Tuple[str, str]:
        """
        Run the solver on a JSON-encoded argumentation framework.
        
        Args:
            af_json: JSON string containing the complete AF specification
        
        Returns:
            Tuple containing:
            - grounded_extension: JSON string with list of argument IDs
            - explanations: JSON string with map of argument ID to support sets
            Note: defeats are computed but not returned as they're used internally
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
        kb_json = self.extract_kb(
            case_description=case_text
        ).knowledge_base
        kb = json.loads(kb_json)

        # Passo 2: Extrair modelo causal
        model_json = self.extract_model(
            knowledge_base=kb_json,
            case_description=case_text
        ).causal_model
        model = json.loads(model_json)

        # Passo 3: Construir AF base
        base_af_json = self.build_af(
            knowledge_base=kb_json,
            causal_model=model_json
        ).af_json

        # Passo 4: Obter resultados base
        base_grounded, base_explanations = self.solver(base_af_json)

        # Passo 5: Testar cada causa potencial
        causal_results = {}
        for cause in kb["potential_causes"]:
            # Create test AF with contrafactual axiom
            context = {
                "knowledge_base": kb,
                "causal_model": model,
                "base_grounded": json.loads(base_grounded),
                "base_explanations": json.loads(base_explanations)
            }
            
            test_kb = {
                "axioms": [negate_fact(cause, context, case_text)],
                "premises": kb["premises"]
            }
            
            test_af_json = self.build_af(
                knowledge_base=json.dumps(test_kb),
                causal_model=model_json
            ).af_json
            
            # Get test results
            test_grounded, _ = self.solver(test_af_json)
            
            # Analyze causation
            result = self.analyze_test(
                potential_cause=cause,
                target_conclusion=kb["target_conclusion"],
                base_explanations=base_explanations,
                test_grounded_extension=test_grounded,
                case_description=case_text
            )
            
            causal_results[cause] = {
                "is_cause": result.is_cause,
                "explanation": result.causal_explanation
            }
        
        return {
            "case_text": case_text,
            "knowledge_base": kb,
            "causal_model": model,
            "base_framework": json.loads(base_af_json),
            "base_grounded": json.loads(base_grounded),
            "base_explanations": json.loads(base_explanations),
            "causal_results": causal_results
        }