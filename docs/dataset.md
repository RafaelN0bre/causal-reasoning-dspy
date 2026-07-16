# Datasets

O projeto usa dois datasets: o benchmark público **BoardgameQA** (raciocínio defeasible) e um
**dataset legal próprio** de casos causais pré-rotulados (`data/legal/`).

## BoardgameQA

BoardgameQA é um benchmark de raciocínio defeasible baseado em cenários de jogos de tabuleiro.
Cada caso contém fatos, regras condicionais (possivelmente conflitantes) e preferências entre regras.
A tarefa é determinar se um goal é **proved**, **disproved** ou **unknown**.

Referência: Kazemi et al., *BoardgameQA: A Dataset for Natural Language Reasoning with
Contradictory Information* (NeurIPS 2023).

## Download do BoardgameQA

O dataset é distribuído pelo Google Research como um zip único (~todas as variantes):

```bash
# Da raiz do repositório
curl -L -o /tmp/BoardgameQA.zip \
  "https://storage.googleapis.com/gresearch/BoardgameQA/BoardgameQA.zip"
unzip /tmp/BoardgameQA.zip -d data/
```

Após extrair, confira que a estrutura ficou como em [Formato dos Arquivos](#formato-dos-arquivos):
cada variante em uma pasta `data/BoardgameQA/BoardgameQA-<VARIANTE>/` contendo
`train.json`, `valid.json` e `test.json`. A pasta `data/` está no `.gitignore`, então
o download precisa ser refeito em cada clone novo.

## Variantes Disponíveis

| Grupo | Variante | Descrição |
|---|---|---|
| **Main** | `Main-depth1` | Raciocínio de profundidade 1 |
| | `Main-depth2` | Raciocínio de profundidade 2 (padrão) |
| | `Main-depth3` | Raciocínio de profundidade 3 |
| **Conflict** | `ZeroConflict-depth2` | Sem conflitos entre regras |
| | `LowConflict-depth2` | Conflitos ocasionais |
| | `HighConflict-depth2` | Alta densidade de conflitos |
| **Dificuldade** | `EasyConflict-depth2` | Conflitos fáceis de resolver |
| | `DifficultConflict-depth2` | Conflitos difíceis de resolver |
| **Distractors** | `SomeDistractors-depth2` | Algumas regras irrelevantes |
| | `ManyDistractors-depth2` | Muitas regras irrelevantes |
| **Knowledge** | `KnowledgeLight-depth2` | Poucos fatos e regras |
| | `KnowledgeHeavy-depth2` | Muitos fatos e regras |
| **Binary** | `Binary-depth1` | Apenas proved/disproved (sem unknown) |
| | `Binary-depth2` | Idem, profundidade 2 |
| | `Binary-depth3` | Idem, profundidade 3 |

## Splits

| Split | Uso |
|---|---|
| `train` | Compilação dos otimizadores (BootstrapFewShot, MIPROv2) |
| `valid` | Seleção do melhor programa durante compilação |
| `test` | Avaliação final (padrão no `main.py`) |

## Estrutura de um Caso

```
Facts: The blobfish assassinated the mayor. The grizzly bear has a card that is indigo in color.

Rules: Rule1: If the blobfish killed the mayor, then it knocks down the fortress of the panda bear.
       Rule2: If the grizzly bear has a card of a rainbow color, then it sings a victory song.

Preferences: Rule1 is preferred over Rule2.

Goal: (panda bear, knock, fortress)
Label: proved
```

## Labels

| Label | Significado |
|---|---|
| `proved` | O goal é derivado pela extensão fundamentada |
| `disproved` | A negação do goal é derivada |
| `unknown` | Nem o goal nem sua negação são derivados |

## Formato dos Arquivos

Os datasets ficam em `data/BoardgameQA/BoardgameQA-<VARIANT>/` (o prefixo `BoardgameQA-`
vem do próprio zip oficial; `src/dataset.py` monta o caminho como
`data/BoardgameQA/BoardgameQA-{variant}/{split}.json`):

```
data/BoardgameQA/
├── BoardgameQA-Main-depth1/
│   ├── train.json
│   ├── valid.json
│   └── test.json
├── BoardgameQA-Main-depth2/
│   └── ...
└── ...
```

Cada arquivo é uma lista de objetos JSON com os campos `story`, `label`, e `proof`.

> **Nota**: a pasta `data/` está no `.gitignore`; veja a seção
> [Download do BoardgameQA](#download-do-boardgameqa) para obter os arquivos.

## Resultados por Variante

Os resultados dos benchmarks ficam em `outputs/boardgame/`:

```
outputs/boardgame/
├── dspy/
│   ├── compiled/
│   │   ├── few-shot/
│   │   │   ├── Main-depth1_test_results.json
│   │   │   └── Main-depth1_test_trace.jsonl
│   │   └── mipro/
│   │       └── ...
│   └── zero-shot/
│       └── ...
└── baseline/
    └── ...
```

Cada `_results.json` contém métricas de acurácia por label, confusion matrix e análise de unknowns.
Cada `_trace.jsonl` contém o trace completo de cada caso (inputs, outputs do LLM, solver, decisão).
