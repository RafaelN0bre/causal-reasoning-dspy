# DSPy + Defeasible Argumentation for Cause-in-Fact Legal Reasoning

Implementação de um pipeline híbrido que combina DSPy (para estruturar LLMs) com um solver formal de argumentação defeasible para determinar relações de causa-em-fato em casos de direito do consumidor.

## 🏗️ Arquitetura

```
Texto do Caso → [DSPy] Fatos → [DSPy] Regras → [DSPy] Argumentos+Ataques 
              → [Solver] Extensão Fundamentada → [DSPy] Julgamento Causal
```

Veja [`architecture.md`](./architecture.md) para detalhes completos.

## 🚀 Instalação

1. **Clonar e instalar dependências:**

```bash
# Instalar dependências
uv pip install -e ".[dev]"
```

2. **Configurar API key:**

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar .env e adicionar sua chave OpenAI
# OPENAI_API_KEY=sk-...
```

## 📖 Uso Básico

### Executar o pipeline completo:

```bash
python pipeline.py
```

Isso irá:
1. Processar um caso exemplo (celular à prova d'água)
2. Extrair fatos estruturados
3. Identificar regras causais
4. Gerar argumentos e ataques
5. Calcular argumentos justificados
6. Produzir explicação causal

### Usar com seu próprio caso:

```python
from pipeline import run_causal_reasoning_pipeline
import dspy
import os

# Configurar DSPy
dspy.configure(lm=dspy.LM('openai/gpt-4o-mini', api_key=os.getenv('OPENAI_API_KEY')))

# Seu caso
case_text = """
Comprei um produto com defeito...
"""

result = run_causal_reasoning_pipeline(
    case_text=case_text,
    potential_cause="Produto_Defeituoso"
)

print(result['causal_explanation'])
```

## 🧪 Testes

```bash
# Executar testes unitários
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=src --cov-report=html
```

## 📊 Dataset Sintético

O projeto inclui 5 casos sintéticos de teste em `src/dataset.py`:

1. **Celular à prova d'água** - undercutting (empresa alega mau uso)
2. **Entrega atrasada** - causa direta simples
3. **Defeito oculto** - defeito de fábrica vs. garantia expirada
4. **Preempção** - duas causas concorrentes (internet lenta + servidor)
5. **Publicidade enganosa** - vício de informação

## 🔧 Componentes

### DSPy Signatures (`src/signatures.py`)
- `TextToFacts` - Extrai fatos atômicos do texto
- `FactsToRules` - Identifica regras causais defeasible
- `GenerateArgumentsAndAttacks` - Gera argumentos e ataques
- `CausalJudgement` - Produz explicação causal final

### Solver de Argumentação (`src/solver.py`)
- `Argument` - Representa um argumento (premissas → conclusão)
- `Attack` - Representa um ataque (rebut/undercut)
- `ArgumentationFramework` - Calcula extensão fundamentada (grounded extension)

### Pipeline (`pipeline.py`)
- Orquestra todo o processo end-to-end
- Integra DSPy com o solver formal
- Gera saída JSON com análise completa

## 📝 Estrutura de Saída

```json
{
  "case_text": "...",
  "structured_facts": "Produto_Defeituoso, Consumidor_Reclamou, ...",
  "causal_rules": "r1: Produto_Defeituoso => Dever_Reparo\n...",
  "arguments": ["A1: ... => Dever_Reparo", "A2: ... => Nao_Aplica"],
  "attacks": ["A2 undercuts A1"],
  "justified_arguments": ["A1"],
  "support_sets": {"A1": ["A1", "A3"]},
  "causal_explanation": "O fato 'Produto_Defeituoso' é causa-em-fato porque..."
}
```

## 🎯 Próximos Passos

- [ ] Implementar few-shot learning com BootstrapFewShot do DSPy
- [ ] Adicionar métricas de avaliação (precision/recall sobre dataset)
- [ ] Suportar outros tipos de ataque (defeating vs. undermining)
- [ ] Integrar com bases de jurisprudência real
- [ ] Adicionar interface web (Streamlit/Gradio)

## 📚 Referências

- **Artigo base:** "Modelling Cause-in-Fact in Legal Cases through Defeasible Argumentation"
- **DSPy:** https://github.com/stanfordnlp/dspy
- **ASPIC+:** Framework de argumentação estruturada

## 📄 Licença

Este projeto é parte de um TCC (Trabalho de Conclusão de Curso).
