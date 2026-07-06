"""Diagnóstico de observabilidade — verifica Langfuse e logging.

Uso:
    uv run scripts/check_observability.py
"""
import os
import sys


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_python_env() -> None:
    print("\n=== Python / venv ===")
    _ok(f"Executable : {sys.executable}")
    _ok(f"Version    : {sys.version.split()[0]}")
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv:
        _warn(f"VIRTUAL_ENV={venv} (set externally — uv run may ignore it)")
    else:
        _ok("VIRTUAL_ENV not set (uv run will use project .venv)")


def check_langfuse_package() -> bool:
    print("\n=== Pacote langfuse ===")
    try:
        import langfuse
        _ok(f"langfuse {langfuse.__version__} importado com sucesso")
        return True
    except Exception as e:
        _fail(f"Falha ao importar langfuse: {type(e).__name__}: {e}")
        _fail(f"  Python em uso: {sys.executable}")
        _fail("  Corrija com: uv sync --extra observability")
        return False


def check_env_vars() -> dict:
    print("\n=== Variáveis de ambiente ===")
    from dotenv import load_dotenv
    load_dotenv()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3010")

    if public_key:
        _ok(f"LANGFUSE_PUBLIC_KEY = {public_key[:8]}...")
    else:
        _fail("LANGFUSE_PUBLIC_KEY não definido no .env")

    if secret_key:
        _ok(f"LANGFUSE_SECRET_KEY = {secret_key[:8]}...")
    else:
        _fail("LANGFUSE_SECRET_KEY não definido no .env")

    _ok(f"LANGFUSE_HOST = {host}")

    return {"public_key": public_key, "secret_key": secret_key, "host": host}


def check_host_reachable(host: str) -> bool:
    print(f"\n=== Conectividade ({host}) ===")
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.urlopen(host, timeout=5)
        _ok(f"Host respondeu: HTTP {req.status}")
        return True
    except urllib.error.HTTPError as e:
        # Any HTTP response means the server is up
        _ok(f"Host respondeu: HTTP {e.code}")
        return True
    except Exception as e:
        _fail(f"Não foi possível conectar a {host}: {e}")
        _fail("  Verifique se o Langfuse está rodando: docker compose up -d")
        return False


def check_langfuse_auth(public_key: str, secret_key: str, host: str) -> bool:
    print("\n=== Autenticação Langfuse ===")
    try:
        from langfuse import Langfuse
        lf = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        lf.auth_check()
        _ok("auth_check() passou — credenciais válidas")
        return lf
    except Exception as e:
        err = str(e)
        _fail(f"auth_check() falhou: {err}")
        if "organization" in err or "metadata" in err:
            import langfuse as _lf_mod
            _fail(
                f"  Versão do cliente ({_lf_mod.__version__}) incompatível com o servidor Langfuse v2."
            )
            _fail("  Corrija com: uv sync --extra observability  (requer langfuse<3 no pyproject.toml)")
        return None


def check_trace(lf) -> None:
    print("\n=== Trace de teste ===")
    try:
        trace = lf.trace(
            name="observability-check",
            input={"test": True},
            output={"ok": True},
            tags=["diagnostic"],
        )
        lf.flush()
        _ok(f"Trace enviado com sucesso: id={trace.id}")
        _ok(f"Verifique em: {os.getenv('LANGFUSE_HOST', 'http://localhost:3010')}")
    except Exception as e:
        _fail(f"Falha ao enviar trace: {e}")


def check_logs_dir() -> None:
    print("\n=== Pasta de logs ===")
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    if os.path.isdir(logs_dir):
        files = sorted(os.listdir(logs_dir))
        _ok(f"logs/ existe ({len(files)} arquivo(s))")
        if files:
            _ok(f"  Mais recente: {files[-1]}")
    else:
        _warn("logs/ ainda não existe (criada automaticamente na primeira execução)")


def main() -> None:
    print("=" * 55)
    print("  Diagnóstico de Observabilidade")
    print("=" * 55)

    check_python_env()
    check_logs_dir()

    has_langfuse = check_langfuse_package()
    if not has_langfuse:
        print("\n[!] Instale langfuse antes de continuar:")
        print("    uv sync --extra observability")
        sys.exit(1)

    env = check_env_vars()
    if not env["public_key"] or not env["secret_key"]:
        print("\n[!] Configure LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY no .env")
        print("    Siga: docs/observability.md")
        sys.exit(1)

    reachable = check_host_reachable(env["host"])
    if not reachable:
        sys.exit(1)

    lf = check_langfuse_auth(env["public_key"], env["secret_key"], env["host"])
    if not lf:
        sys.exit(1)

    check_trace(lf)

    print("\n" + "=" * 55)
    print("  Tudo OK — observabilidade configurada corretamente.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
