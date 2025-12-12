# DSPy + Defeasible Argumentation for Cause-in-Fact Legal Reasoning

Sistema híbrido que combina DSPy (para estruturar e guiar LLMs) com um solver formal de argumentação defeasible para determinar relações de causa-em-fato em casos de direito do consumidor.

## 🏗️ Arquitetura

O pipeline processa casos jurídicos através das seguintes etapas:

```
Texto do Caso → [DSPy] Base de Conhecimento → [DSPy] Modelo Causal 
              → [DSPy] Framework de Argumentação → [Solver] Extensão Fundamentada 
              → [DSPy] Análise Causal → Resultado Final
```

Cada etapa transforma a representação do caso, desde texto em prosa até uma conclusão formal sobre causa-em-fato, seguindo o framework ASPIC+ de argumentação estruturada.

Veja [`architecture.md`](./architecture.md) para detalhes completos da arquitetura e componentes.

## 🚀 Instalação

1. **Clonar e instalar dependências:**

```bash
# Instalar dependências
uv pip install -e ".[dev]"
```

2. **Configurar API key:**

Crie um arquivo `.env` na raiz do projeto com sua chave da API Gemini:

```bash
GEMINI_API_KEY=your-api-key-here
```

## 📖 Uso Básico

### Executar o pipeline completo:

```bash
python pipeline.py
```

Ou como módulo Python:

```bash
python -m src.pipeline
```

O script irá:
1. Carregar o dataset de casos de exemplo
2. Permitir seleção de um caso específico ou análise de todos
3. Processar cada caso através do pipeline completo
4. Validar resultados contra expectativas
5. Salvar resultados detalhados em `outputs/`

### Usar programaticamente:

```python
import os
import dspy
from dotenv import load_dotenv
from src import CausalReasoningPipeline

# Carregar variáveis de ambiente
load_dotenv()

# Configurar DSPy
api_key = os.getenv("GEMINI_API_KEY")
lm = dspy.LM('gemini/gemini-2.5-flash', api_key=api_key, max_tokens=8000)
dspy.configure(lm=lm)

# Inicializar pipeline
pipeline = CausalReasoningPipeline()

# Processar um caso
case_text = """
Comprei um celular online anunciado como à prova d'água. 
Caiu na piscina e parou de funcionar. A empresa se recusa 
a consertar alegando mau uso.
"""

result = pipeline(case_text)
print(result['causal_results'])
```

## 🧪 Testes

O projeto inclui validação automática dos resultados do pipeline contra casos esperados. Execute o pipeline para ver as validações:

```bash
python src/pipeline.py
```

Para executar testes unitários (quando disponíveis):

```bash
pytest tests/ -v
```

## 📊 Dataset Sintético

O projeto inclui 5 casos sintéticos de teste em `src/dataset.py`:

1. **Celular à prova d'água** - undercutting (empresa alega mau uso)
2. **Entrega atrasada** - causa direta simples
3. **Defeito oculto** - defeito de fábrica vs. garantia expirada
4. **Preempção** - duas causas concorrentes (internet lenta + servidor)
5. **Publicidade enganosa** - vício de informação

## 🔧 Componentes Principais

### DSPy Signatures (`src/signatures.py`)
Define os contratos de entrada/saída entre módulos:
- `TextToKnowledgeBase` - Extrai base de conhecimento estruturada do texto
- `ExtractCausalModel` - Identifica regras causais defeasible e preferências
- `BuildArgumentationFramework` - Constrói framework completo de argumentação
- `AnalyzeCausalTest` - Analisa testes contrafactuais para determinar causa-em-fato

### Solver de Argumentação (`src/solver.py`)
Implementação do framework ASPIC+:
- `Literal` - Representa literais (fatos e negações)
- `Rule` - Representa regras defeasible e estritas
- `Argument` - Representa argumentos (cadeias de inferência)
- `Attack` - Representa ataques entre argumentos (undermine, undercut, rebut)
- `ArgumentationFramework` - Calcula extensão fundamentada (grounded extension)

### Pipeline (`src/modules.py`)
- `CausalReasoningPipeline` - Orquestra todo o processo end-to-end
- `ArgumentationSolver` - Integra o solver formal como ferramenta DSPy
- Coordena extração, modelagem, argumentação e análise causal

### Runner (`src/pipeline.py`)
Script principal que:
- Configura ambiente e logging
- Carrega dataset de casos
- Executa análises e validações
- Gera relatórios em JSON

## 📝 Estrutura de Saída

O pipeline gera resultados estruturados em JSON com as seguintes seções:

```json
{
  "knowledge_base": {
    "premises": ["Produto_Anunciado_AprovaAgua", "Produto_Caiu_Piscina", ...],
    "potential_causes": ["Produto_Anunciado_AprovaAgua", ...],
    "target_conclusion": "Dever_Reparo"
  },
  "causal_model": {
    "defeasible_rules": [...],
    "undercutter_rules": [...],
    "strict_rules": [...],
    "preferences": {...}
  },
  "argumentation_framework": {
    "arguments": [...],
    "attacks": [...],
    "defeats": [...]
  },
  "causal_results": {
    "Produto_Anunciado_AprovaAgua": {
      "is_cause": true,
      "causal_explanation": "...",
      "defeated_chain": [...]
    }
  }
}
```

Resultados detalhados são salvos em `outputs/case_{id}_results.json` para cada caso analisado.

## 📁 Estrutura do Repositório

```
repo/
├── src/                    # Implementação principal (versão atual)
│   ├── dataset.py         # Dataset de casos de exemplo
│   ├── signatures.py      # Assinaturas DSPy
│   ├── modules.py         # Pipeline e módulos DSPy
│   ├── solver.py         # Solver de argumentação ASPIC+
│   └── pipeline.py        # Script runner principal
├── v1/                    # Primeira versão (histórico)
├── outputs/               # Resultados das análises
├── architecture.md        # Documentação detalhada da arquitetura
└── pyproject.toml        # Configuração do projeto
```

## 📚 Referências

- **Artigo base:** "Modelling Cause-in-Fact in Legal Cases through Defeasible Argumentation"
- **DSPy:** https://github.com/stanfordnlp/dspy
- **ASPIC+:** Framework de argumentação estruturada

## 📄 Licença

Este projeto é parte de um TCC (Trabalho de Conclusão de Curso).
