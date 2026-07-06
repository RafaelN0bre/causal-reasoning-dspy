# Guia de Uso

O ponto de entrada único é `main.py`. Execute sempre via `uv run main.py [opções]`.

## Instalação

```bash
uv pip install -e ".[dev]"
```

Crie o arquivo `.env` na raiz do projeto:

```bash
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-2.5-flash   # opcional
LOG_LEVEL=INFO                   # opcional
```

## Modo Legal (padrão)

Analisa casos do `GOLDEN_DATASET` e valida contra resultados esperados.

```bash
# Todos os casos
uv run main.py
uv run main.py --legal

# Caso específico
uv run main.py --legal --case-id 1
uv run main.py -l --case-id 2
```

Resultados salvos em `outputs/case_<id>_results.json` e `outputs/analysis_summary.json`.

## Modo BoardgameQA (benchmark)

Executa benchmark de raciocínio defeasible.

| Pipeline | Como ativar | Descrição |
|---|---|---|
| DSPy + ASPIC+ compilado | padrão (se `compiled/` existir) | Few-shot otimizado + solver |
| DSPy + ASPIC+ zero-shot | `--no-compiled` | Sem exemplos few-shot |
| Baseline LLM | `--baseline` | LLM direto, sem solver |

```bash
# Pipeline padrão (carrega compiled/ automaticamente)
uv run main.py --boardgame
uv run main.py -b

# Forçar zero-shot
uv run main.py -b --no-compiled

# Baseline LLM direto
uv run main.py -b --baseline

# Limitar casos e escolher variante
uv run main.py -b -d Main-depth2 -n 50
uv run main.py -b -d Main-depth2 -n 50 --baseline

# Especificar variante, split e saída
uv run main.py -b -d ZeroConflict-depth2 -s valid
uv run main.py -b -d Binary-depth1 -s test -n 30 -o outputs/exp01

# Gerar gráficos após benchmark
uv run main.py -b --charts
```

## Referência de Flags

### `main.py`

| Flag | Atalho | Padrão | Descrição |
|---|---|---|---|
| `--legal` | `-l` | — | Modo análise jurídica |
| `--boardgame` | `-b` | — | Modo benchmark BoardgameQA |
| `--baseline` | | `false` | LLM direto sem solver |
| `--no-compiled` | | `false` | Força zero-shot |
| `--dataset VARIANT` | `-d` | `Main-depth2` | Variante do dataset |
| `--split SPLIT` | `-s` | `test` | Split: `train`, `test`, `valid` |
| `--limit N` | `-n` | todos | Máximo de casos |
| `--optimizer NAME` | | `few-shot` | Otimizador: `few-shot`, `mipro` |
| `--charts` | `-c` | `false` | Gera gráficos após benchmark |
| `--output DIR` | `-o` | auto | Diretório de saída |
| `--case-id ID` | | — | ID do caso (modo legal) |
| `--max-tokens N` | | `16000` | Máx. tokens por resposta |
| `--session-suffix S` | | — | Sufixo no `session_id` do Langfuse (diferencia runs) |
| `--list-models` | | — | Lista modelos Gemini e sai |

### Saídas

| Diretório | Conteúdo |
|---|---|
| `outputs/boardgame/dspy/compiled/<optimizer>/` | DSPy + ASPIC+ com programa compilado |
| `outputs/boardgame/dspy/zero-shot/` | DSPy + ASPIC+ sem compilação |
| `outputs/boardgame/baseline/` | Resultados LLM direto |
| `outputs-observability/<estrategia>/` | Amostras para análise no Langfuse (ver `scripts/run_observability_samples.sh`) |
| `outputs/case_*_results.json` | Resultados por caso jurídico |

## Uso Programático

```python
import os
import dspy
from dotenv import load_dotenv
from src.boardgame_module import BoardgamePipeline

load_dotenv()
lm = dspy.LM("gemini/gemini-2.5-flash", api_key=os.getenv("GEMINI_API_KEY"), max_tokens=16000)
dspy.configure(lm=lm)

# Zero-shot
pipeline = BoardgamePipeline()

# Com programa compilado
pipeline = BoardgamePipeline()
pipeline.load("compiled/few-shot/boardgame_Main-depth2.json")

result = pipeline(case_text="Facts: ...\n\nRules: ...", goal_str="(swan, swear, woodpecker)")
print(result["label"])  # "proved" / "disproved" / "unknown"
```

Pipeline jurídico:

```python
from src.modules import CausalReasoningPipeline

pipeline = CausalReasoningPipeline()
result = pipeline("Um celular anunciado como à prova d'água caiu na piscina e parou de funcionar...")
print(result["causal_results"])
```
