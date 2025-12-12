"""Pipeline de raciocínio causal para análise de causa-em-fato em casos jurídicos.

Este pacote implementa um sistema híbrido que combina DSPy (para estruturar LLMs)
com um solver formal de argumentação defeasible para determinar relações de
causa-em-fato em casos de direito do consumidor.
"""

from .modules import CausalReasoningPipeline
from .solver import ArgumentationFramework, Argument, Attack, Literal, Rule
from .dataset import GOLDEN_DATASET

__all__ = [
    'CausalReasoningPipeline',
    'ArgumentationFramework',
    'Argument',
    'Attack',
    'Literal',
    'Rule',
    'GOLDEN_DATASET',
]

