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

## 📖 Uso

O ponto de entrada único é `main.py`.  Execute sempre via `uv run main.py [opções]`.

### Modo legal (padrão)

Analisa os casos do `GOLDEN_DATASET` (casos jurídicos sintéticos) e valida contra os resultados esperados.

```bash
# Analisar todos os casos
uv run main.py

# Analisar um caso específico (IDs 1, 2, 3)
uv run main.py --legal --case-id 1
```

Resultados salvos em `outputs/case_<id>_results.json` e `outputs/analysis_summary.json`.

### Modo BoardgameQA (benchmark)

Executa o benchmark de raciocínio defeasible no dataset BoardgameQA.

```bash
# Benchmark padrão (Main-depth2, split test, todos os casos)
uv run main.py --boardgame

# Limitar número de casos (útil para testes rápidos)
uv run main.py -b -d Main-depth2 -n 50

# Outro variant / split
uv run main.py -b -d ZeroConflict-depth2 -s valid

# Com geração de gráficos (requer matplotlib)
uv run main.py -b --charts
```

#### Variantes disponíveis do BoardgameQA

| Grupo | Variantes |
|---|---|
| Main | `Main-depth1`, `Main-depth2`, `Main-depth3` |
| Conflict | `ZeroConflict-depth2`, `LowConflict-depth2`, `HighConflict-depth2` |
| Conflict (dificuldade) | `EasyConflict-depth2`, `DifficultConflict-depth2` |
| Distractors | `SomeDistractors-depth2`, `ManyDistractors-depth2` |
| Knowledge | `KnowledgeLight-depth2`, `KnowledgeHeavy-depth2` |
| Binary | `Binary-depth1`, `Binary-depth2`, `Binary-depth3` |

Resultados salvos em `outputs/boardgame/<variant>_<split>_results.json`.

### Opções gerais

| Flag | Atalho | Descrição |
|---|---|---|
| `--legal` | `-l` | Modo análise jurídica (padrão) |
| `--boardgame` | `-b` | Modo benchmark BoardgameQA |
| `--dataset VARIANT` | `-d` | Variante do dataset (boardgame) |
| `--split {train,test,valid}` | `-s` | Split (boardgame, padrão: test) |
| `--limit N` | `-n` | Limitar N casos (boardgame) |
| `--charts` | `-c` | Gerar gráficos de acurácia |
| `--output DIR` | `-o` | Diretório de saída (boardgame) |
| `--case-id ID` | | ID do caso a analisar (legal) |
| `--max-tokens N` | | Máx. tokens do LM (padrão: 16000) |

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
lm = dspy.LM('gemini/gemini-2.5-pro', api_key=api_key, max_tokens=8000)
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

Validação automática contra casos esperados:

```bash
uv run main.py --legal
```

Testes unitários (quando disponíveis):

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
Funções de execução para cada modo:
- `run_legal_analysis` — analisa casos do GOLDEN_DATASET e salva resultados
- `run_boardgame_tests` — executa benchmark BoardgameQA e calcula métricas
- `generate_boardgame_charts` — gera gráficos de acurácia por variante

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
├── main.py                # Ponto de entrada (uv run main.py)
├── src/
│   ├── dataset.py         # GOLDEN_DATASET (casos jurídicos) + carregamento BoardgameQA
│   ├── signatures.py      # Assinaturas DSPy
│   ├── modules.py         # CausalReasoningPipeline + ArgumentationSolver
│   ├── solver.py          # Solver ASPIC+ (extensão grounded)
│   └── pipeline.py        # Runners: run_legal_analysis, run_boardgame_tests
├── data/BoardgameQA/      # Arquivos JSON do benchmark (não versionados)
├── outputs/               # Resultados gerados
│   ├── case_*_results.json          # Resultados por caso jurídico
│   ├── analysis_summary.json        # Sumário modo legal
│   └── boardgame/<variant>_<split>_results.json
├── architecture.md        # Documentação detalhada da arquitetura
└── pyproject.toml
```

## 📚 Referências

- **Artigo base:** "Modelling Cause-in-Fact in Legal Cases through Defeasible Argumentation"
- **DSPy:** https://github.com/stanfordnlp/dspy
- **ASPIC+:** Framework de argumentação estruturada

## 📄 Licença

Este projeto é parte de um TCC (Trabalho de Conclusão de Curso).
