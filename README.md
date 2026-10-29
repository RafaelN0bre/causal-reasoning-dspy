# DSPy + Defeasible Argumentation for Cause-in-Fact Legal Reasoning

Sistema híbrido que combina **DSPy** (para estruturar e guiar LLMs) com um **solver ASPIC+** de argumentação defeasible para determinar relações de causa-em-fato em casos de direito do consumidor. Avaliado no benchmark **BoardgameQA**.

## Início Rápido

```bash
uv pip install -e ".[dev]"
cp .env.example .env          # edite com sua GEMINI_API_KEY

# Benchmark BoardgameQA (100 casos, pipeline compilado)
uv run main.py -b -d Main-depth2 -n 100

# Análise de casos jurídicos
uv run main.py --legal

# Processo real (RE 608.880/MT), só a camada simbólica, sem LLM
uv run scripts/run_real_case.py
```

## Resultados das execuções

Todo resultado reportado na monografia está versionado em [`outputs/`](outputs/), com o log da
execução correspondente em [`logs/`](logs/).

| Pasta | Execução | Capítulo da monografia |
|---|---|---|
| [`outputs/boardgame/`](outputs/boardgame/) | BoardgameQA: baseline, zero-shot, few-shot e MIPROv2, `Main-depth{1,2,3}` e variantes complementares (resultado agregado `*_results.json` + rastreamento por caso `*_trace.jsonl`) | Resultados no BoardgameQA |
| [`outputs/legal/`](outputs/legal/) | Detecção de nexo causal nos 30 casos de teste de [`data/legal/`](data/legal/) (um arquivo por caso + `analysis_summary.json`) | Resultados na Detecção de Nexo Causal |
| [`outputs/caso-real/`](outputs/caso-real/) | Solver ASPIC+ sobre a formalização do RE 608.880/MT (Tema 362 do STF); fonte, acórdão e figuras em [`data/caso-real/`](data/caso-real/) | Execução sobre um Processo Real |
| [`outputs-observability/`](outputs-observability/) | Amostras com Langfuse (5 casos × 4 estratégias) e exportação dos *prompts* | Análise dos *Prompts* / Apêndice de *prompts* |
| [`compiled/`](compiled/) | Programas DSPy compilados (BootstrapFewShot e MIPROv2) | Otimização de *Prompts* |

## Documentação

| Documento | Descrição |
|---|---|
| [Caso real](data/caso-real/README.md) | RE 608.880/MT: procedência da formalização, arquitetura de duas camadas, resultados e limitação exposta |
| [Arquitetura](docs/architecture.md) | Visão geral do sistema, componentes, fluxos e contratos de dados |
| [Uso](docs/usage.md) | CLI, flags, exemplos e API programática |
| [Otimização](docs/optimization.md) | BootstrapFewShot e MIPROv2 — como compilar e comparar |
| [Dataset](docs/dataset.md) | Variantes do BoardgameQA, splits e formato dos dados |
| [Observabilidade](docs/observability.md) | Langfuse — rastreamento local e análise de falhas |
| [Desenvolvimento](docs/development.md) | Estrutura do projeto, dependências, formato do trace |
| [Contexto](context.md) | Resumo completo do projeto em bullet points (artefato para LLMs) |

## Estrutura Resumida

```
main.py                  ← ponto de entrada
scripts/
  optimize_fewshot.py    ← compilação com BootstrapFewShot
  optimize_mipro.py      ← compilação com MIPROv2
  check_observability.py ← diagnóstico Langfuse/logs
  run_observability_samples.sh ← amostras das 4 estratégias p/ Langfuse
  run_real_case.py       ← solver sobre a formalização do RE 608.880/MT
data/
  legal/                 ← casos causais pré-rotulados (train/test)
  caso-real/             ← formalização, acórdão e figuras do caso real
  BoardgameQA/           ← baixado à parte (não versionado)
outputs/                 ← resultados de todas as execuções
logs/                    ← log de cada execução
src/
  boardgame_module.py    ← BoardgamePipeline (compilável)
  modules.py             ← CausalReasoningPipeline (modo legal)
  signatures.py          ← assinaturas DSPy
  solver.py              ← solver ASPIC+
  pipeline.py            ← runners e métricas
  observability.py       ← integração Langfuse (opcional)
compiled/                ← programas otimizados (auto-carregados)
docker-compose.yml       ← Langfuse local
docs/                    ← documentação completa
```

## Referências

- **DSPy**: https://github.com/stanfordnlp/dspy
- **ASPIC+**: Framework de argumentação estruturada defeasible
- **BoardgameQA**: Benchmark de raciocínio defeasible
- **Langfuse**: https://langfuse.com

---

*TCC — Universidade de Brasília (UnB)*
