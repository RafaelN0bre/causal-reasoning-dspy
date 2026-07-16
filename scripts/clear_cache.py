"""Limpa os caches de disco do DSPy/LiteLLM usados pelo projeto.

O DSPy mantém um cache de chamadas ao LLM em disco cujo carregamento
atrasa a inicialização de qualquer pipeline, mesmo em modos que não se
beneficiam dele (ex.: análise legal). Este script remove os diretórios
de cache conhecidos e reporta o espaço liberado.

Uso:
    uv run scripts/clear_cache.py           # remove os caches
    uv run scripts/clear_cache.py --dry-run # só mostra o que seria removido
"""
import argparse
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Diretórios de cache que o projeto pode ter criado, em ordem de relevância:
# - ~/.dspy_cache        : cache padrão do DSPy (o efetivamente usado)
# - <repo>/.cache/dspy   : DSPY_CACHEDIR definido em main.py e nos scripts
# - ~/.cache/litellm     : cache de disco do LiteLLM (backend do dspy.LM)
CACHE_DIRS = [
    os.path.expanduser("~/.dspy_cache"),
    os.path.join(REPO_ROOT, ".cache", "dspy"),
    os.path.expanduser("~/.cache/litellm"),
]


def dir_size_bytes(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} GB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpa os caches de disco do DSPy/LiteLLM.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas lista os caches encontrados, sem remover nada",
    )
    args = parser.parse_args()

    found = False
    freed = 0
    for path in CACHE_DIRS:
        if not os.path.isdir(path):
            continue
        found = True
        size = dir_size_bytes(path)
        if args.dry_run:
            print(f"[dry-run] removeria {path} ({human(size)})")
            continue
        try:
            shutil.rmtree(path)
        except OSError as exc:
            print(f"ERRO ao remover {path}: {exc}", file=sys.stderr)
            continue
        freed += size
        print(f"removido {path} ({human(size)})")

    if not found:
        print("Nenhum cache encontrado; nada a fazer.")
    elif not args.dry_run:
        print(f"Total liberado: {human(freed)}")
        print("Atenção: sem cache, chamadas repetidas ao LLM serão reenviadas à API.")


if __name__ == "__main__":
    main()
