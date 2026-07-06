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
```

## Documentação

| Documento | Descrição |
|---|---|
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
