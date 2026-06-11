# Imports are intentionally omitted here to avoid loading heavy dependencies
# (dspy, litellm) at package import time.  Import directly from submodules instead:
#
#   from src.dataset import BOARDGAME_VARIANTS, load_boardgame_dataset
#   from src.modules import CausalReasoningPipeline
#   from src.solver import ArgumentationFramework
