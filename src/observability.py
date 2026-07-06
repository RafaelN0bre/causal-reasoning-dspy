"""Integração opcional com Langfuse para observabilidade do pipeline.

Se LANGFUSE_PUBLIC_KEY não estiver configurado, todas as chamadas são no-ops.

Variáveis de ambiente necessárias:
    LANGFUSE_PUBLIC_KEY   — chave pública (pk-lf-...)
    LANGFUSE_SECRET_KEY   — chave secreta (sk-lf-...)
    LANGFUSE_HOST         — host da instância (padrão: http://localhost:3000)

Uso:
    from src.observability import get_langfuse, flush_langfuse

    lf = get_langfuse()
    if lf:
        trace = lf.trace(name="boardgame-case", input={...})
        lf.score(trace_id=trace.id, name="accuracy", value=1.0)
    flush_langfuse()
"""
import logging
import os
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_instance = None
_langfuse_tried = False

# Active Langfuse trace for the current case (ContextVar is safe across async and threading contexts)
_ACTIVE_TRACE: ContextVar = ContextVar("langfuse_active_trace", default=None)

# Guards against registering the DSPy callback more than once per process
_dspy_callback_registered = False


def get_langfuse():
    """Retorna instância Langfuse se configurada, senão None."""
    global _langfuse_instance, _langfuse_tried
    if _langfuse_tried:
        return _langfuse_instance
    _langfuse_tried = True

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.warning(
            "Langfuse desabilitado: LANGFUSE_PUBLIC_KEY e/ou LANGFUSE_SECRET_KEY não definidos. "
            "Traces não serão enviados. Configure em .env para habilitar observabilidade."
        )
        return None

    try:
        from langfuse import Langfuse
        host = os.getenv("LANGFUSE_HOST", "http://localhost:3010")
        _langfuse_instance = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.info("Langfuse habilitado (host=%s)", host)
        return _langfuse_instance
    except ImportError:
        logger.warning(
            "Pacote langfuse não instalado. "
            "Para habilitar: uv pip install -e '.[observability]'. "
            "Continuando sem observabilidade."
        )
        return None
    except Exception as e:
        logger.warning("Falha ao inicializar Langfuse: %s", e)
        return None


def flush_langfuse() -> None:
    """Envia eventos pendentes para o Langfuse. Chamar ao final de cada run."""
    lf = get_langfuse()
    if lf:
        try:
            lf.flush()
            logger.debug("Langfuse: eventos enviados.")
        except Exception as e:
            logger.warning("Langfuse flush error: %s", e)


def register_dspy_callback(lf) -> None:
    """Registers a DSPy BaseCallback that logs every LM call to Langfuse as a child generation.

    Safe to call multiple times — only registers once per process.
    Each generation is automatically linked to the active trace set by
    begin_boardgame_trace() via a ContextVar, so concurrent cases don't cross-contaminate.

    Call this once after dspy.configure() and get_langfuse():
        register_dspy_callback(get_langfuse())
    """
    global _dspy_callback_registered
    if lf is None or _dspy_callback_registered:
        return

    try:
        import dspy
        from dspy.utils.callback import BaseCallback

        class _LangfuseCallback(BaseCallback):
            def __init__(self):
                self._pending: dict = {}  # call_id -> Langfuse generation object

            def on_lm_start(self, call_id: str, instance, inputs: dict):
                trace = _ACTIVE_TRACE.get()
                if trace is None:
                    return
                try:
                    # DSPy LM.__call__(prompt=None, messages=None, **kwargs)
                    # inputs will have "prompt" and/or "messages" keys
                    prompt_input = inputs.get("messages") or inputs.get("prompt")
                    model = getattr(instance, "model", "unknown")
                    gen = trace.generation(
                        name="dspy-lm",
                        model=model,
                        input=prompt_input,
                    )
                    self._pending[call_id] = gen
                except Exception as e:
                    logger.warning("Langfuse on_lm_start error: %s", e)

            def on_lm_end(self, call_id: str, outputs, exception=None):
                gen = self._pending.pop(call_id, None)
                if gen is None:
                    return
                try:
                    if exception:
                        gen.end(level="ERROR", status_message=str(exception))
                    else:
                        # DSPy LM outputs is a list of completion strings
                        output = outputs[0] if isinstance(outputs, list) and outputs else outputs
                        gen.end(output=output)
                except Exception as e:
                    logger.warning("Langfuse on_lm_end error: %s", e)

        existing_callbacks = dspy.settings.get("callbacks", [])
        dspy.configure(callbacks=existing_callbacks + [_LangfuseCallback()])
        _dspy_callback_registered = True
        logger.info("Langfuse DSPy callback registered — LM calls will appear as child generations in each trace.")
    except ImportError as e:
        logger.warning("Could not register DSPy callback (import error): %s", e)
    except Exception as e:
        logger.warning("DSPy callback registration failed: %s", e)


def begin_boardgame_trace(
    lf,
    *,
    session_id: str,
    idx: int,
    case_text: str,
    goal_str: str,
    expected_label: str,
    variant: str,
    split: str,
    optimizer: str,
):
    """Creates a Langfuse trace before the pipeline runs and sets it as the active context.

    LM calls made by DSPy during pipeline execution will automatically be linked to this
    trace as child generations (requires register_dspy_callback() to have been called).

    Returns the trace object, or None if Langfuse is disabled.
    Always pair with end_boardgame_trace() to update the output and score.
    """
    if lf is None:
        return None
    try:
        trace = lf.trace(
            name="boardgame-case",
            session_id=session_id,
            input={
                "case_text": case_text,
                "goal": goal_str,
            },
            metadata={
                "variant": variant,
                "split": split,
                "optimizer": optimizer,
                "index": idx,
                "expected": expected_label,
            },
            tags=[variant, f"optimizer:{optimizer}", f"label:{expected_label}"],
        )
        _ACTIVE_TRACE.set(trace)
        return trace
    except Exception as e:
        logger.warning("Langfuse begin trace error (case %d): %s", idx, e)
        return None


def log_generation(
    *,
    name: str,
    model: str,
    input: Any,
    output: Any = None,
    level: str = "DEFAULT",
    status_message: str | None = None,
) -> None:
    """Log a single LLM generation (prompt + response) to the active Langfuse trace.

    Useful for non-DSPy calls (e.g. baseline raw LLM) where the DSPy callback
    doesn't fire.  Safe to call when Langfuse is disabled — it's a no-op.
    """
    trace = _ACTIVE_TRACE.get()
    if trace is None:
        return
    try:
        gen = trace.generation(
            name=name,
            model=model,
            input=input,
        )
        gen.end(output=output, level=level, status_message=status_message)
    except Exception as e:
        logger.warning("Langfuse log_generation error: %s", e)


def end_boardgame_trace(
    trace,
    *,
    idx: int,
    expected_label: str,
    predicted_label: str,
    correct: bool,
    pipeline_trace: dict,
    prediction_trace: dict,
    error_info,
) -> None:
    """Updates the Langfuse trace with the pipeline result, clears the active context, and adds a score.

    Always call this after begin_boardgame_trace(), even if the pipeline raised an exception.
    """
    _ACTIVE_TRACE.set(None)
    if trace is None:
        return

    lf = get_langfuse()
    if lf is None:
        return

    try:
        result_tags = ["correct" if correct else "wrong"]
        if error_info:
            result_tags.append("error")

        # Upsert the trace with output and remaining metadata fields
        lf.trace(
            id=trace.id,
            output={
                "predicted": predicted_label,
                "correct": correct,
            },
            metadata={
                "kb_premises_count": len(
                    pipeline_trace.get("kb_parsed", {}).get("premises", [])
                ),
                "rules_count": len(
                    pipeline_trace.get("rules_parsed", {}).get("defeasible_rules", [])
                ),
                "grounded_count": len(pipeline_trace.get("grounded_ids", [])),
                "decision_reason": prediction_trace.get("decision_reason", ""),
                "error": error_info,
            },
            tags=result_tags,
        )
        lf.score(
            trace_id=trace.id,
            name="accuracy",
            value=1.0 if correct else 0.0,
            comment=f"expected={expected_label}, predicted={predicted_label}",
        )
    except Exception as e:
        logger.warning("Langfuse end trace error (case %d): %s", idx, e)
