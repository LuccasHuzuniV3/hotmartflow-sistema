"""Config global dos testes: raiz no sys.path + modo simulado acelerado.

O HOTMARTFLOW_SIM_DELAY precisa ser setado ANTES do primeiro import de
core.robo (qualquer modulo de teste pode ser o primeiro a importar) — por isso
vive aqui no conftest, que roda antes de todos.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("HOTMARTFLOW_SIM_DELAY", "0.02")

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
