# Contexto do Projeto — Artefato para LLMs

> Documento autocontido que descreve todo o projeto: objetivos, estrutura do código, como os testes são executados, o que é avaliado e as ferramentas utilizadas. Destinado a ser inserido como artefato/contexto em outra IA.

## 1. O que é o projeto

- Trabalho de Conclusão de Curso (TCC) — Universidade de Brasília (UnB), autor: Rafael Nobre.
- Sistema **neuro-simbólico**: combina LLMs (parte neural) com um **solver formal de argumentação defeasible ASPIC+** (parte simbólica).
- A parte neural é estruturada com **DSPy** (framework de programação declarativa de LLMs, Stanford): o LLM extrai conhecimento estruturado do texto; o solver determinístico faz o raciocínio lógico.
- Avaliado no benchmark **BoardgameQA** (raciocínio defeasible com regras conflitantes e preferências).
- O domínio jurídico (causa-em-fato em direito do consumidor) existe como aplicação demonstrativa (modo `--legal`), mas o foco do trabalho é a **engenharia da arquitetura neuro-simbólica** e a comparação de estratégias de otimização de prompt.

## 2. Objetivos

- **Hipótese central**: delegar o raciocínio lógico a um solver formal (ASPIC+) e usar o LLM apenas para extração estruturada produz melhor acurácia em raciocínio defeasible do que usar o LLM sozinho.
- **Comparar 4 estratégias de execução** no BoardgameQA:
  - `baseline` — LLM puro (Gemini via API direta), recebe fatos/regras/preferências/goal e responde o label diretamente, sem solver.
  - `zero-shot` — pipeline DSPy + solver ASPIC+, sem exemplos few-shot.
  - `few-shot` — mesmo pipeline, compilado com o otimizador **BootstrapFewShot** do DSPy (injeta demos nos prompts).
  - `mipro` — mesmo pipeline, compilado com **MIPROv2** (otimiza instruções + demos via busca Bayesiana).
- **Demonstrar a "compilação" do DSPy** como otimização de prompt (não é treinamento/fine-tuning de modelo).
- **Usar observabilidade (Langfuse)** para inspecionar os prompts finais de cada estratégia e analisar casos de falha.

## 3. Ferramentas e stack

- **Python ≥ 3.13**, gerenciado com **uv** (`uv run`, `uv sync`, `uv pip install -e .`).
- **DSPy** (`dspy-ai`) — signatures, `dspy.ChainOfThought`, otimizadores (teleprompters) BootstrapFewShot e MIPROv2, cache local em `.cache/dspy`.
- **Google Gemini** (`google-generativeai`) — LLM padrão `gemini-2.5-flash`, chave em `GEMINI_API_KEY` (`.env`), `temperature=0.0` no baseline, `max_tokens=16000`.
- **Solver ASPIC+ próprio** (`src/solver.py`, sem dependências externas) — argumentação estruturada com semântica grounded.
- **Langfuse v2** (opcional) — observabilidade self-hosted via `docker-compose.yml` (porta 3010, com Postgres 15).
- **matplotlib** (opcional) — gráficos de acurácia (`--charts`).
- **pytest** (dev) — declarado em `pyproject.toml`.
- Restrição operacional: **nunca executar múltiplos `uv run` em paralelo** (o cache do DSPy é lento e conflita); scripts rodam as estratégias sequencialmente.

## 4. Estrutura do repositório

- `main.py` — ponto de entrada único (CLI com argparse); configura logging (terminal + arquivo em `logs/`), carrega `.env`, configura o DSPy e despacha para o runner do modo escolhido.
- `src/`
  - `signatures.py` — assinaturas DSPy (contratos entrada/saída dos passos LLM):
    - `BoardgameKBExtraction` — texto do caso + goal → JSON `{premises, target_conclusion}`.
    - `BoardgameRuleExtraction` — texto + KB → JSON `{defeasible_rules, undercutter_rules, preferences}`.
    - `TextToKnowledgeBase`, `ExtractCausalModel`, `BuildArgumentationFramework`, `AnalyzeCausalTest` — usadas no modo legal.
  - `boardgame_module.py` — `BoardgamePipeline(dspy.Module)`, o módulo **compilável** do benchmark:
    - passo 1: `dspy.ChainOfThought(BoardgameKBExtraction)` extrai premissas e conclusão-alvo;
    - passo 2: `dspy.ChainOfThought(BoardgameRuleExtraction)` extrai regras defeasible, undercutters e preferências;
    - passo 3: monta `ArgumentationFramework` (solver determinístico) e calcula a extensão grounded;
    - `_map_label()` mapeia as conclusões grounded para `proved`/`disproved`/`unknown` (matching normalizado do goal, com detecção de negação e fallback por ID de argumento);
    - retorna dict com `label`, extensão grounded, KB e `_trace` (dados brutos para debugging/JSONL).
  - `solver.py` — implementação ASPIC+: `Literal`, `Rule`, `Argument`, `Attack`, `ArgumentationFramework`; constrói argumentos até ponto fixo, identifica ataques (undermine/undercut/rebut), resolve derrotas por preferências e expõe `compute_grounded_extension()`. Semântica grounded escolhida por unicidade, ceticismo e tratabilidade.
  - `pipeline.py` — runner `run_boardgame_tests()` (loop de avaliação, métricas, traces, Langfuse, resume) e `run_legal_analysis()`; funções de métricas `_calculate_metrics`, `_analyze_unknowns`, `_summarize_leakage`, `_map_solver_to_label`; `generate_boardgame_charts()`.
  - `baseline.py` — runner do LLM puro: prompt único com definições de proved/disproved/unknown, regras de raciocínio e formato JSON de saída; parsing robusto em 3 estratégias (JSON direto → regex do bloco `{"label"...}` → keyword scan).
  - `dataset.py` — `BOARDGAME_VARIANTS` (15 variantes), `load_boardgame_dataset(variant, split)`, `parse_boardgame_case()` (separa facts/rules/preferences/goal/label do campo `story`), e `GOLDEN_DATASET` (casos jurídicos do modo legal).
  - `modules.py` — `CausalReasoningPipeline` do modo legal (extração de KB → modelo causal → framework → solver → análise contrafactual) e helper `_try_parse_json`.
  - `observability.py` — integração opcional com Langfuse (no-op se não configurado); detalhes na seção 9.
- `scripts/`
  - `optimize_fewshot.py` — compila `BoardgamePipeline` com BootstrapFewShot → `compiled/few-shot/boardgame_<VARIANT>.json`.
  - `optimize_mipro.py` — compila com MIPROv2 (`--auto light|medium|heavy` ou `--num-trials`) → `compiled/mipro/boardgame_<VARIANT>.json`.
  - `check_observability.py` — diagnóstico Langfuse (pacote, env vars, conectividade, auth, trace de teste).
  - `run_observability_samples.sh` — 5 casos × 4 estratégias em `Main-depth2`, sessões Langfuse distintas, saída em `outputs-observability/`.
- `compiled/` — programas DSPy compilados, **auto-carregados** pelo `main.py` quando existem (`compiled/<optimizer>/boardgame_<VARIANT>.json`).
- `data/BoardgameQA/<VARIANT>/{train,valid,test}.json` — dataset (cada item: `story`, `label`, `proof`).
- `outputs/` — resultados dos benchmarks (ver seção 7).
- `outputs-observability/` — resultados das amostras de observabilidade (baseline/, zero-shot/, few-shot/, mipro/).
- `logs/` — um arquivo de log por execução, com timestamp e comando (gitignored).
- `docs/` — architecture.md, usage.md, optimization.md, dataset.md, observability.md, development.md, TODO.md.
- `docker-compose.yml` — Langfuse v2 + Postgres, UI em http://localhost:3010.

## 5. Dataset — BoardgameQA

- Benchmark de **raciocínio defeasible**: fatos + regras condicionais possivelmente conflitantes + preferências entre regras; tarefa de 3 classes.
- Labels: `proved` (goal derivável), `disproved` (negação do goal derivável), `unknown` (nenhum dos dois).
- 15 variantes, agrupadas por eixo de dificuldade:
  - profundidade de raciocínio: `Main-depth1/2/3`;
  - conflito: `ZeroConflict`, `LowConflict`, `HighConflict`, `EasyConflict`, `DifficultConflict` (depth2);
  - distratores: `SomeDistractors`, `ManyDistractors` (depth2);
  - volume de conhecimento: `KnowledgeLight`, `KnowledgeHeavy` (depth2);
  - binárias (sem `unknown`): `Binary-depth1/2/3`.
- Splits: `train` (compilação dos otimizadores), `valid` (seleção durante compilação), `test` (avaliação final — padrão).
- Variante padrão dos experimentos: **`Main-depth2`**, split `test`, tipicamente `-n 100` casos.

## 6. Como os testes/benchmarks são executados

- Comandos principais (sempre via `uv run`):
  - `uv run main.py -b -d Main-depth2 -n 100` — pipeline DSPy + ASPIC+ (carrega `compiled/few-shot/` automaticamente se existir);
  - `uv run main.py -b ... --optimizer mipro` — carrega o programa compilado pelo MIPROv2;
  - `uv run main.py -b ... --no-compiled` — força zero-shot;
  - `uv run main.py -b ... --baseline` — LLM puro sem solver;
  - `uv run main.py --legal [--case-id N]` — modo jurídico com validação contra `GOLDEN_DATASET`.
- Fluxo de avaliação por caso (em `run_boardgame_tests`):
  - carrega e faz o parse do caso (`facts`, `rules`, `preferences`, `goal`, `label` esperado);
  - monta `case_text` **sem o label esperado** (isolamento explícito — o label só é usado após a predição, para métricas);
  - executa o pipeline (ou a chamada LLM única, no baseline);
  - compara predição vs. esperado, acumula métricas e grava uma linha completa no trace JSONL;
  - erros de API viram label `error` e são **excluídos** do cálculo de acurácia.
- **Resume**: se o `*_results.json` do run já existe, os índices processados são pulados e o trace JSONL é aberto em append — execuções interrompidas continuam de onde pararam.
- **Verificações anti-vazamento** (`_check_answer_leakage`, gravadas por caso e agregadas em `leakage_summary`): label esperado presente no texto de entrada; goal (ou sua negação) extraído como premissa (prova/refutação trivial); premissas vazias (falha de extração); palavras de label dentro de regras extraídas.
- Logging: cada execução gera `logs/<timestamp>_<modo>_<variante>_<split>.log` com o comando completo; `LOG_LEVEL=DEBUG` habilita trace detalhado por caso.

## 7. O que é avaliado (métricas e saídas)

- Arquivos gerados por run, em `outputs/boardgame/{dspy/compiled/<optimizer> | dspy/zero-shot | baseline}/`:
  - `<VARIANT>_<split>_results.json` — métricas agregadas + lista de resultados por caso;
  - `<VARIANT>_<split>_trace.jsonl` — trace completo por caso: inputs, JSONs brutos e parseados do LLM, extensão grounded, razão da decisão (`decision_reason`), leakage check, referência do proof do dataset.
- Métricas em `results.json`:
  - `accuracy` global (casos com erro de API excluídos);
  - `per_label` — acurácia separada para proved/disproved/unknown;
  - `confusion_matrix` — pares `esperado->predito`;
  - `unknown_analysis` — decomposição dos unknowns (corretos vs. falsos unknowns por classe; motivo anotado no trace: extensão grounded vazia vs. goal não casou com nenhuma conclusão);
  - `leakage_summary` — agregação dos avisos de vazamento/viés;
  - `total_time` e `cases_per_second`.
- Comparação central do TCC: **acurácia das 4 estratégias na mesma variante/split**, mais a análise qualitativa dos prompts (via Langfuse) e das falhas (via traces).
- Resultados atuais de referência (test split, n=100; few-shot/mipro apenas nas variantes Main):

| Variante | baseline | zero-shot | few-shot | mipro |
|---|---|---|---|---|
| Main-depth1 | 0.74 | 0.91 | 0.90 | 0.89 |
| Main-depth2 | 0.59 | 0.79 | 0.88 | 0.76 |
| Main-depth3 | 0.46 | 0.75 | 0.80 (n=95) | 0.82 |
| Binary-depth1 | — | 0.82 | — | — |
| KnowledgeLight-depth2 | — | 0.87 | — | — |
| KnowledgeHeavy-depth2 | — | 0.86 | — | — |

- Leitura dos resultados: o pipeline neuro-simbólico supera o baseline em todas as profundidades; a vantagem cresce com a profundidade do raciocínio; a compilação (few-shot/mipro) melhora sobretudo depth2/depth3.

## 8. Otimização (compilação DSPy)

- "Compilar" no DSPy = **otimizar prompts** (selecionar demos few-shot e/ou reescrever instruções) — não altera pesos do modelo.
- Métrica de otimização: acerto exato do label no split `valid` (programa que maximiza acurácia de validação é salvo).
- `uv run scripts/optimize_fewshot.py -d <VARIANT> [-n 50] [--max-bootstrapped 4] [--max-labeled 4]` → `compiled/few-shot/`.
- `uv run scripts/optimize_mipro.py -d <VARIANT> [--auto light|medium|heavy] [--num-trials N] [--num-threads 1]` → `compiled/mipro/`.
- `--num-threads 1` por padrão para respeitar rate limit do free tier do Gemini.
- O `main.py` decide sozinho: se `compiled/<optimizer>/boardgame_<VARIANT>.json` existe e `--no-compiled` não foi passado, carrega o programa compilado; caso contrário roda zero-shot (e informa no log).

## 9. Observabilidade (Langfuse)

- Opcional e não-intrusiva: sem `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` no `.env`, tudo vira no-op.
- Infra local: `docker compose up -d` → UI em `http://localhost:3010` (Langfuse v2 + Postgres).
- Instalação do cliente: `uv sync --extra observability` (pin `langfuse>=2,<3` para compatibilidade com o servidor v2).
- Arquitetura da integração (`src/observability.py`):
  - `begin_boardgame_trace()` cria o trace **antes** do pipeline e o registra em um `ContextVar`;
  - um `dspy.BaseCallback` registrado uma vez por processo (`register_dspy_callback`) captura **cada chamada LM do DSPy** (prompt/messages + resposta) como child generation do trace ativo;
  - no baseline (sem DSPy), `log_generation()` loga o prompt e a resposta manualmente;
  - `end_boardgame_trace()` grava output (`predicted`, `correct`), metadata (contagem de premissas/regras/argumentos grounded, `decision_reason`, erro), tags (`correct`/`wrong`/`error`, `optimizer:X`, `label:Y`) e um score `accuracy` (0/1).
- `session_id = <variant>-<split>-<optimizer>[-<session-suffix>]` agrupa os casos de um run; `--session-suffix` diferencia execuções repetidas.
- Casos de uso no TCC: comparar prompts finais entre estratégias (evidenciar o que a compilação mudou), filtrar `tag:wrong` para análise de falhas, detectar falhas de extração (`rules_count = 0`).
- Diagnóstico: `uv run scripts/check_observability.py`; amostras: `./scripts/run_observability_samples.sh`.

## 10. Integridade experimental

- O label esperado nunca entra em nenhum prompt (isolado antes da montagem do `case_text`; comentários no código marcam o fluxo).
- Checagem pré-chamada: alerta se o label aparece verbatim no texto do caso (indicaria vazamento no próprio dataset).
- Checagens pós-chamada por caso + agregação por run (`leakage_summary`) — ver seção 6.
- Baseline recebe **exatamente os mesmos inputs** que o pipeline DSPy (facts, rules, preferences, goal), garantindo comparação justa.
- Temperatura 0 no baseline; cache do DSPy torna reexecuções determinísticas e baratas.

## 11. Convenções e observações operacionais

- Executar tudo via `uv run`; **não** rodar múltiplos `uv run` em paralelo (conflito/lentidão do cache DSPy).
- `.env` obrigatório com `GEMINI_API_KEY`; opcionais: `GEMINI_MODEL`, `LOG_LEVEL`, `DSPY_CACHEDIR`, `LANGFUSE_*`.
- `logs/`, `.cache/`, `.env` e `data/` são gitignored (o dataset BoardgameQA deve ser baixado à parte); `outputs/`, `outputs-observability/` e `compiled/{few-shot,mipro}/` são versionados como evidência dos experimentos.
- Para adicionar uma variante nova: colocar os JSONs em `data/BoardgameQA/<VARIANT>/`, adicionar o nome a `BOARDGAME_VARIANTS` em `src/dataset.py`, compilar e avaliar.
- Documentação detalhada em `docs/` (architecture, usage, optimization, dataset, observability, development).
