# Observabilidade com Langfuse e Logs

## Logs de Execução

Cada execução gera automaticamente um arquivo de log em `logs/`:

```
logs/
  2026-06-25_14-30-00_boardgame_baseline_KnowledgeHeavy-depth2_test.log
  2026-06-25_15-10-00_boardgame_dspy_Main-depth2_test.log
```

O nome do arquivo inclui timestamp e modo (`boardgame_dspy`, `boardgame_baseline`, `legal_all`, etc.).

As primeiras linhas de cada log são sempre:

```
2026-06-25 14:30:00 INFO __main__: Log file: logs/2026-06-25_14-30-00_...log
2026-06-25 14:30:00 INFO __main__: Command : uv run main.py -b -d KnowledgeHeavy-depth2 -n 100
```

Todos os logs também aparecem no terminal em tempo real. O nível padrão é `INFO`; use `LOG_LEVEL=DEBUG` no `.env` para saída detalhada (trace por caso, chamadas ao solver, etc.).

A pasta `logs/` está no `.gitignore` e não é commitada.

---

## Langfuse (Rastreamento por Caso)

O pipeline integra com [Langfuse](https://langfuse.com) para rastreamento de cada chamada LLM,
comparação de otimizadores e análise de casos onde o pipeline falha.

## Subindo o Langfuse Localmente

```bash
docker compose up -d
```

Acesse em http://localhost:3010. Crie uma conta, vá em **Settings → API Keys** e gere as chaves.

## Configuração

Adicione ao `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3010   # ou https://cloud.langfuse.com para cloud
```

Instale o pacote:

```bash
uv sync --extra observability
# ou: uv pip install -e ".[observability]"
```

## Diagnóstico

Verifique toda a configuração (pacote, variáveis, conectividade, autenticação, envio de trace de teste):

```bash
uv run scripts/check_observability.py
```

## Uso

Nenhuma alteração no comando de execução — a integração é automática quando as variáveis
de ambiente estão configuradas:

```bash
uv run main.py -b -d Main-depth2 -n 100 --optimizer mipro
```

Se `LANGFUSE_PUBLIC_KEY` não estiver definido, o pipeline roda normalmente sem observabilidade.

Use `--session-suffix` para diferenciar runs da mesma configuração no Langfuse:

```bash
uv run main.py -b -d Main-depth2 -n 5 --session-suffix sample-1
# session_id: "Main-depth2-test-few-shot-sample-1"
```

### Amostras para Comparação de Prompts

O script `scripts/run_observability_samples.sh` executa 5 casos de `Main-depth2` para cada
uma das 4 estratégias (baseline, zero-shot, few-shot, mipro), cada uma em uma sessão
Langfuse distinta, salvando resultados em `outputs-observability/<estrategia>/`:

```bash
./scripts/run_observability_samples.sh
```

Isso permite comparar lado a lado, na UI do Langfuse, os prompts finais enviados ao LLM
por cada estratégia (ex.: demos few-shot injetados, instruções reescritas pelo MIPROv2).

## O que é Rastreado

Para cada caso do benchmark, o Langfuse registra:

| Campo | Descrição |
|---|---|
| `session_id` | `{variant}-{split}-{optimizer}` — agrupa todos os casos de um run |
| `input` | `case_text`, `goal`, `expected` |
| `output` | `predicted`, `correct` |
| `metadata.optimizer` | `few-shot`, `mipro` ou `zero-shot` |
| `metadata.kb_premises_count` | Número de premissas extraídas pelo LLM |
| `metadata.rules_count` | Número de regras defeasible extraídas |
| `metadata.grounded_count` | Número de argumentos na extensão grounded |
| `metadata.decision_reason` | Razão textual da decisão (qual conclusão casou com o goal) |
| `score: accuracy` | `1.0` se correto, `0.0` se incorreto |
| `tags` | `[variant, optimizer:X, label:Y, correct/wrong, error?]` |

## Casos de Uso no Contexto do TCC

### Comparar Otimizadores

Na UI do Langfuse, filtre por `optimizer:few-shot` vs `optimizer:mipro` para comparar:
- Acurácia média por label (proved/disproved/unknown)
- Latência e custo de tokens por caso
- Quais casos um otimizador acerta e o outro erra

### Analisar Falhas

Filtre por `tag: wrong` e inspecione:
- O que o LLM extraiu como premissas vs. o que era esperado
- Se o goal foi mapeado para a conclusão errada
- Se a extensão grounded ficou vazia (falha de extração de regras)

### Debug de Extração LLM

O campo `metadata.rules_count = 0` indica falha na extração de regras — o LLM não retornou
regras válidas para aquele caso. Filtre por este campo para identificar padrões.

## Implementação

O módulo `src/observability.py` gerencia a conexão com o Langfuse de forma opcional
(todas as funções são no-ops quando o Langfuse não está configurado):

| Função | Papel |
|---|---|
| `get_langfuse()` | Retorna a instância Langfuse (ou `None` se desabilitado) |
| `register_dspy_callback(lf)` | Registra um `BaseCallback` do DSPy que loga cada chamada LM como *child generation* do trace ativo |
| `begin_boardgame_trace(...)` | Cria o trace **antes** do pipeline rodar e o define como contexto ativo (via `ContextVar`) |
| `end_boardgame_trace(...)` | Atualiza o trace com output, metadata, tags e score de acurácia |
| `log_generation(...)` | Loga prompt + resposta de chamadas não-DSPy (usado pelo baseline) |
| `flush_langfuse()` | Envia eventos pendentes ao final do run |

Fluxo em `src/pipeline.py` (e análogo em `src/baseline.py`):

```python
lf = get_langfuse()
register_dspy_callback(lf)              # uma vez por processo

for caso in casos:
    trace = begin_boardgame_trace(lf, session_id=..., case_text=..., ...)
    result = pipeline.boardgame_forward(case_text, goal_str)   # LM calls viram child generations
    end_boardgame_trace(trace, predicted_label=..., correct=..., ...)

flush_langfuse()
```
