# Otimização do Pipeline

O DSPy permite otimizar o pipeline automaticamente usando exemplos do split de treino.
Os otimizadores injetam exemplos few-shot nos prompts das Signatures e/ou otimizam as
instruções via busca Bayesiana.

Após compilar, o `main.py` carrega o programa automaticamente.

## BootstrapFewShot

O otimizador mais simples: seleciona exemplos do trainset que maximizam a acurácia no
conjunto de validação e os injeta como demos nos prompts.

```bash
# Variante padrão (Main-depth2)
uv run scripts/optimize_fewshot.py

# Outra variante
uv run scripts/optimize_fewshot.py -d Main-depth1
uv run scripts/optimize_fewshot.py -d ZeroConflict-depth2

# Controlar tamanho do trainset e demos
uv run scripts/optimize_fewshot.py -n 30
uv run scripts/optimize_fewshot.py --max-bootstrapped 4 --max-labeled 6

# Ver todas as opções
uv run scripts/optimize_fewshot.py --help
```

### Flags — `optimize_fewshot.py`

| Flag | Atalho | Padrão | Descrição |
|---|---|---|---|
| `--variant VARIANT` | `-d` | `Main-depth2` | Variante do BoardgameQA |
| `--train-limit N` | `-n` | `50` | Nº de exemplos do split `train` |
| `--val-limit N` | | `20` | Nº de exemplos de validação |
| `--max-bootstrapped N` | | `4` | Demos gerados automaticamente por passo |
| `--max-labeled N` | | `4` | Demos rotulados por passo |
| `--output-dir DIR` | | `compiled/few-shot/` | Pasta de saída |
| `--max-tokens N` | | `16000` | Máx. tokens por resposta |

Salva o programa em `compiled/few-shot/boardgame_<VARIANT>.json`.

## MIPROv2

Otimiza tanto as **instruções das signatures** quanto os **exemplos few-shot** via busca
Bayesiana. É mais poderoso que BootstrapFewShot — especialmente em variantes com maior
profundidade de raciocínio (depth3) — mas consome mais chamadas à API.

```bash
# Variante padrão com intensidade light (~10 trials)
uv run scripts/optimize_mipro.py

# Outra variante com intensidade medium (~20 trials)
uv run scripts/optimize_mipro.py -d Main-depth3 --auto medium

# Controle manual de trials
uv run scripts/optimize_mipro.py -d Main-depth2 --num-trials 15

# Ver todas as opções
uv run scripts/optimize_mipro.py --help
```

### Flags — `optimize_mipro.py`

| Flag | Atalho | Padrão | Descrição |
|---|---|---|---|
| `--variant VARIANT` | `-d` | `Main-depth2` | Variante do BoardgameQA |
| `--train-limit N` | `-n` | `50` | Nº de exemplos do split `train` |
| `--val-limit N` | | `20` | Nº de exemplos de validação |
| `--auto MODE` | | `light` | Intensidade: `light` (~10), `medium` (~20), `heavy` (~30) |
| `--num-trials N` | | — | Nº de trials Bayesianos (sobrescreve `--auto`) |
| `--max-bootstrapped N` | | `4` | Demos gerados automaticamente por passo |
| `--max-labeled N` | | `4` | Demos rotulados por passo |
| `--num-threads N` | | `1` | Threads paralelas (1 para evitar rate limit no free tier) |
| `--output-dir DIR` | | `compiled/mipro/` | Pasta de saída |
| `--max-tokens N` | | `16000` | Máx. tokens por resposta |

Salva o programa em `compiled/mipro/boardgame_<VARIANT>.json`.

## Carregamento Automático

O `main.py` detecta e carrega automaticamente o programa compilado:

```
compiled/<optimizer>/boardgame_<VARIANT>.json
```

Para escolher o otimizador ao executar:

```bash
uv run main.py -b -d Main-depth2 --optimizer few-shot   # carrega compiled/few-shot/
uv run main.py -b -d Main-depth2 --optimizer mipro      # carrega compiled/mipro/
uv run main.py -b -d Main-depth2 --no-compiled          # força zero-shot
```

## Fluxo de Trabalho Recomendado

```bash
# 1. Baseline zero-shot
uv run main.py -b -d Main-depth2 -n 50 --no-compiled

# 2. Compilar com BootstrapFewShot
uv run scripts/optimize_fewshot.py -d Main-depth2 -n 50

# 3. Avaliar com few-shot
uv run main.py -b -d Main-depth2 -n 50 --optimizer few-shot

# 4. Compilar com MIPROv2
uv run scripts/optimize_mipro.py -d Main-depth2 -n 50

# 5. Avaliar com MIPRO
uv run main.py -b -d Main-depth2 -n 50 --optimizer mipro

# 6. Comparar resultados em outputs/
```

## Programas Compilados Disponíveis

```
compiled/
├── few-shot/
│   ├── boardgame_Main-depth1.json
│   ├── boardgame_Main-depth2.json
│   └── boardgame_Main-depth3.json
└── mipro/
    ├── boardgame_Main-depth1.json
    ├── boardgame_Main-depth2.json
    └── boardgame_Main-depth3.json
```
