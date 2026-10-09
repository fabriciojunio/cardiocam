"""Os comandos científicos produzem UTF-8 mesmo sob um console legado."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("modulo,argumentos,trecho", [
    ("cardiocam.avaliacao.experimentos", [], "Avaliação experimental"),
    ("cardiocam.avaliacao.referencia", ["--help"], "referência"),
])
def test_comandos_experimentais_usam_utf8(modulo, argumentos, trecho, tmp_path):
    ambiente = {**os.environ, "PYTHONIOENCODING": "cp1252",
                "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
    resultado = subprocess.run([sys.executable, "-B", "-m", modulo, *argumentos],
                               cwd=tmp_path, env=ambiente, capture_output=True, timeout=60)
    assert resultado.returncode == 0, resultado.stderr.decode("utf-8", errors="replace")
    assert trecho in resultado.stdout.decode("utf-8")
