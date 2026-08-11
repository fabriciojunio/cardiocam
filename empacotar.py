"""Gera o executável do Cardiocam para Windows.

Uso:
    python empacotar.py

O resultado sai em `dist/Cardiocam.exe`, um arquivo único que roda em qualquer
Windows sem Python instalado. O tamanho fica na casa de algumas centenas de
megabytes porque OpenCV, SciPy e NumPy vão junto.

Não existe versão equivalente para celular, e a razão é estrutural: OpenCV e
SciPy compilados para Android ou iOS dariam um trabalho desproporcional, e no
iOS ainda seria preciso conta paga de desenvolvedor. Para celular o caminho é a
versão web, que instala na tela inicial e roda igual a um aplicativo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
NOME = "Cardiocam"


def limpar() -> None:
    for pasta in ("build", "dist"):
        alvo = RAIZ / pasta
        if alvo.exists():
            shutil.rmtree(alvo)
    especificacao = RAIZ / f"{NOME}.spec"
    if especificacao.exists():
        especificacao.unlink()


def montar_comando() -> list[str]:
    import cv2

    # Os arquivos das cascatas de Haar vivem dentro do pacote do OpenCV e não
    # são detectados automaticamente, porque o código os monta por concatenação
    # de caminho em tempo de execução.
    dados_haar = Path(cv2.data.haarcascades)

    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        NOME,
        # Console visível de propósito: a interface principal do programa é a
        # linha de comando, e esconder o console deixaria o usuário sem as
        # mensagens de erro e sem o resultado final.
        "--console",
        "--add-data",
        f"{dados_haar}{';' if sys.platform.startswith('win') else ':'}cv2/data",
        "--collect-submodules",
        "scipy",
        "--collect-submodules",
        "sklearn",
        # Reduz bastante o tamanho: nada aqui usa interface gráfica dessas
        # bibliotecas.
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PySide2",
        "--exclude-module",
        "pytest",
        "--paths",
        str(RAIZ / "src"),
        str(RAIZ / "src" / "cardiocam" / "__main__.py"),
    ]


def main() -> int:
    entrada = RAIZ / "src" / "cardiocam" / "__main__.py"
    if not entrada.exists():
        print(f"Ponto de entrada não encontrado: {entrada}", file=sys.stderr)
        return 1

    print("Limpando saídas anteriores.")
    limpar()

    print("Empacotando. Isso demora alguns minutos.")
    resultado = subprocess.run(montar_comando(), cwd=RAIZ)
    if resultado.returncode != 0:
        print("O empacotamento falhou.", file=sys.stderr)
        return resultado.returncode

    executavel = RAIZ / "dist" / (f"{NOME}.exe" if sys.platform.startswith("win") else NOME)
    if not executavel.exists():
        print("O executável não foi gerado.", file=sys.stderr)
        return 1

    tamanho = executavel.stat().st_size / (1024 * 1024)
    print()
    print(f"Pronto: {executavel}  ({tamanho:.0f} MB)")
    print()
    print("Como usar:")
    print(f"  {NOME}.exe ao-vivo")
    print(f"  {NOME}.exe arquivo video.mp4 --mostrar")
    print(f"  {NOME}.exe diagnostico --duracao 45")
    print(f"  {NOME}.exe simular --bpm 84")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
