# Desenvolvimento

## Estrutura do Projeto

```
repo/
├── main.py                              # Ponto de entrada (uv run main.py)
├── docker-compose.yml                   # Langfuse local
├── pyproject.toml                       # Dependências e configuração
│
├── scripts/
│   ├── optimize_fewshot.py              # Compilação com BootstrapFewShot
│   ├── optimize_mipro.py                # Compilação com MIPROv2
│   ├── check_observability.py           # Diagnóstico da configuração Langfuse/logs
│   └── run_observability_samples.sh     # 5 casos × 4 estratégias → outputs-observability/
│
├── src/
│   ├── boardgame_module.py              # BoardgamePipeline (compilável)
│   ├── modules.py                       # CausalReasoningPipeline (modo legal)
│   ├── signatures.py                    # Assinaturas DSPy
│   ├── solver.py                        # Solver ASPIC+ (extensão grounded)
│   ├── pipeline.py                      # Runners: run_boardgame_tests, run_legal_analysis
│   ├── baseline.py                      # Runner baseline (LLM direto)
│   ├── dataset.py                       # GOLDEN_DATASET + carregamento BoardgameQA
│   └── observability.py                 # Integração Langfuse (opcional)
│
├── compiled/                            # Programas DSPy compilados (auto-carregados)
│   ├── few-shot/
│   │   └── boardgame_<VARIANT>.json     # Gerado por optimize_fewshot.py
│   └── mipro/
│       └── boardgame_<VARIANT>.json     # Gerado por optimize_mipro.py
│
├── data/BoardgameQA/                    # Arquivos JSON do benchmark
│
├── outputs/
│   ├── case_*_results.json              # Resultados por caso jurídico
│   ├── analysis_summary.json            # Sumário modo legal
│   └── boardgame/
│       ├── dspy/compiled/<optimizer>/   # Resultados DSPy + ASPIC+ compilado
│       ├── dspy/zero-shot/              # Resultados DSPy zero-shot
│       └── baseline/                    # Resultados baseline LLM
│
├── outputs-observability/               # Amostras (5 casos × 4 estratégias) p/ análise Langfuse
│   ├── baseline/ | zero-shot/ | few-shot/ | mipro/
│
├── logs/                                # Logs por execução (gitignored)
│
└── docs/                                # Documentação
    ├── architecture.md
    ├── usage.md
    ├── optimization.md
    ├── dataset.md
    ├── observability.md
    └── development.md
```

## Dependências

```bash
# Instalação básica
uv pip install -e "."

# Com ferramentas de desenvolvimento
uv pip install -e ".[dev]"

# Com geração de gráficos
uv pip install -e ".[charts]"

# Com observabilidade Langfuse
uv pip install -e ".[observability]"

# Tudo
uv pip install -e ".[dev,charts,observability]"
```

## Variáveis de Ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `GEMINI_API_KEY` | Sim | — | Chave de API do Google Gemini |
| `GEMINI_MODEL` | Não | `gemini-2.5-flash` | Modelo Gemini a usar |
| `LOG_LEVEL` | Não | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`) |
| `LANGFUSE_PUBLIC_KEY` | Não | — | Habilita observabilidade Langfuse |
| `LANGFUSE_SECRET_KEY` | Não | — | Chave secreta Langfuse |
| `LANGFUSE_HOST` | Não | `http://localhost:3010` | Host da instância Langfuse |
| `DSPY_CACHEDIR` | Não | `.cache/dspy` | Diretório de cache do DSPy |

## Formato do Trace (JSONL)

Cada linha do arquivo `*_trace.jsonl` é um objeto JSON com:

```json
{
  "index": 0,
  "goal": "(swan, swear, woodpecker)",
  "expected": "proved",
  "predicted": "proved",
  "correct": true,
  "case_text": "Facts: ...\nRules: ...",
  "pipeline_trace": {
    "kb_json_raw": "...",
    "rules_json_raw": "...",
    "kb_parsed": {"premises": [...], "target_conclusion": "..."},
    "rules_parsed": {"defeasible_rules": [...], "preferences": {}},
    "grounded_ids": ["A0", "A1"],
    "grounded_conclusions": {"A0": "SwanSwearsToWoodpecker"}
  },
  "prediction_trace": {
    "method": "conclusions",
    "decision_reason": "conclusion 'SwanSwearsToWoodpecker' matched goal",
    "num_grounded_args": 2
  },
  "leakage_check": {
    "goal_as_premise": false,
    "empty_premises": false,
    "warnings": []
  }
}
```

## Adicionando Novas Variantes

1. Adicione os arquivos `train.json`, `valid.json`, `test.json` em `data/BoardgameQA/<NOVA_VARIANTE>/`
2. Adicione o nome à lista `BOARDGAME_VARIANTS` em `src/dataset.py`
3. Compile: `uv run scripts/optimize_fewshot.py -d <NOVA_VARIANTE>`
4. Avalie: `uv run main.py -b -d <NOVA_VARIANTE>`

## Testes

```bash
uv run pytest
uv run pytest --cov=src
```
