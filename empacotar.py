"""Gera o executável do Cardiocam para Windows.

Uso:
    python empacotar.py

O resultado sai em `dist/Cardiocam.exe`, um arquivo único para Windows que
inclui o interpretador Python. A compatibilidade precisa ser verificada nas
versões de Windows usadas na distribuição. O tamanho fica na casa de centenas de
megabytes porque OpenCV, SciPy, NumPy e Qt vão junto.

O ponto de entrada é o **aplicativo de desktop**, e não a linha de comando: é
nele que o programa é usado. A linha de comando continua existindo para quem
tem Python, por `python -m cardiocam`.

Não existe versão equivalente para celular, e a razão é estrutural: OpenCV e
SciPy compilados para Android ou iOS dariam um trabalho desproporcional, e no
iOS ainda seria preciso conta paga de desenvolvedor.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NOME = "Cardiocam"


def montar_comando(saida: Path, trabalho: Path) -> list[str]:
    import cv2

    # Os arquivos das cascatas de Haar vivem dentro do pacote do OpenCV e não
    # são detectados automaticamente, porque o código os monta por concatenação
    # de caminho em tempo de execução.
    dados_haar = Path(cv2.data.haarcascades)

    separador = ";" if sys.platform.startswith("win") else ":"
    # O modelo de abstenção precisa ir junto. Ele é um arquivo de dados dentro
    # do pacote, e o empacotador não leva dado de pacote por conta própria: sem
    # esta linha o executável sai decidindo pela regra fixa, em silêncio.
    modelo = RAIZ / "src" / "cardiocam" / "qualidade" / "modelo.json"
    if not modelo.is_file() or not dados_haar.is_dir():
        raise FileNotFoundError("Modelo de qualidade ou cascatas do OpenCV ausentes.")

    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        NOME,
        "--distpath",
        str(saida),
        "--workpath",
        str(trabalho / "objetos"),
        "--specpath",
        str(trabalho),
        # Sem console: a interface é a janela, e um prompt preto abrindo junto
        # com ela não informa nada a quem clicou no ícone. Erro que antes ia
        # para o console agora vai para a bandeja, como notificação.
        "--windowed",
        "--add-data",
        f"{dados_haar}{separador}cv2/data",
        "--add-data",
        f"{modelo}{separador}cardiocam/qualidade",
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
        # Redes são ferramentas optativas do pacote Python. A interface de
        # desktop não as importa; dependências instaladas para os testes não
        # devem entrar pelo coletor de adaptadores opcionais do SciPy.
        "--exclude-module",
        "torch",
        "--exclude-module",
        "onnx",
        # O Qt traz módulos pesados que este projeto não usa. Tirar os quatro
        # corta algumas centenas de megabytes do executável.
        "--exclude-module",
        "PySide6.QtWebEngineCore",
        "--exclude-module",
        "PySide6.QtWebEngineWidgets",
        "--exclude-module",
        "PySide6.QtMultimedia",
        "--exclude-module",
        "PySide6.Qt3DCore",
        "--paths",
        str(RAIZ / "src"),
        str(RAIZ / "src" / "cardiocam" / "desktop" / "__main__.py"),
    ]


def main(argumentos: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--saida", type=Path, default=RAIZ / "dist",
                           help="pasta para o executável; outros arquivos são preservados")
    opcoes = analisador.parse_args(argumentos)
    entrada = RAIZ / "src" / "cardiocam" / "desktop" / "__main__.py"
    if not entrada.exists():
        print(f"Ponto de entrada não encontrado: {entrada}", file=sys.stderr)
        return 1

    saida = opcoes.saida.resolve()
    # Cada execução tem seu próprio espaço de trabalho. Não apagamos build,
    # dist ou especificações que podem conter resultados de outra execução.
    trabalho = Path(tempfile.mkdtemp(prefix="cardiocam-build-"))
    print("Empacotando. Isso demora alguns minutos.")
    print(f"Arquivos de construção: {trabalho}")
    resultado = subprocess.run(montar_comando(saida, trabalho), cwd=RAIZ)
    if resultado.returncode != 0:
        print("O empacotamento falhou.", file=sys.stderr)
        return resultado.returncode

    executavel = saida / (f"{NOME}.exe" if sys.platform.startswith("win") else NOME)
    if not executavel.exists():
        print("O executável não foi gerado.", file=sys.stderr)
        return 1

    tamanho = executavel.stat().st_size / (1024 * 1024)
    print()
    print(f"Pronto: {executavel}  ({tamanho:.0f} MB)")
    print()
    print("Como usar:")
    print("  Abra o executável e escolha a origem na janela do aplicativo.")
    print("  A linha de comando é distribuída no pacote Python: python -m cardiocam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
