"""Gera a documentacao de IC em Word, na divisao que a submissao precisa.

Nao e um arquivo unico. A divisao segue o uso de cada documento:

- **dossie**: os cinco documentos que o comite le em sequencia, num arquivo so,
  porque e assim que a leitura flui;
- **um arquivo por termo**: TCLE, uso de imagem, ficha de sessao, compromisso,
  confidencialidade e declaracao da unidade saem separados, porque cada um e
  impresso, rubricado e assinado por conta propria. Juntar os seis num PDF de
  trinta paginas e garantir que alguem assine a pagina errada;
- **apoio**: o que nao vai na submissao, para voce ler.

O motivo de gerar em vez de escrever direto no Word e o mesmo do resto dos
projetos: os numeros saem de script, e Word escrito a mao exigiria copiar numero
por numero a cada reexecucao.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "docs" / "iniciacao-cientifica"
DESTINO = RAIZ / "artefatos" / "iniciacao-cientifica"

TITULO_DA_PESQUISA = (
    "Robustez a movimento e a tom de pele na estimativa de frequencia "
    "cardiaca por camera"
)

# (nome do arquivo de saida, titulo no documento, arquivos de entrada em ordem)
PACOTES: list[tuple[str, str, list[str]]] = [
    (
        "dossie-do-projeto",
        TITULO_DA_PESQUISA,
        [
            "03-projeto-de-pesquisa.md",
            "04-plano-de-trabalho.md",
            "05-resultados-preliminares.md",
            "09-referencias.md",
        ],
    ),
    ("termo-de-consentimento", "Termo de Consentimento Livre e Esclarecido",
     ["07-tcle.md"]),
    ("termos-complementares", "Termos complementares",
     ["08-termos-complementares.md"]),
    (
        "apoio-para-o-aluno",
        "Material de apoio, nao vai na submissao",
        [
            "00-LEIAME.md",
            "01-bolsa-e-vinculo.md",
            "02-como-funciona-ic-unesp.md",
            "06-etica-plataforma-brasil.md",
            "10-roteiro-da-conversa.md",
        ],
    ),
]

# Trechos de instrucao para mim, entre blocos de citacao iniciados por ">".
# Saem do Word da submissao: o comite nao precisa ler o recado de como
# preencher, e deixar isso no documento entregue passa desleixo.
INSTRUCAO = re.compile(r"^> .*$", re.MULTILINE)


def preparar(textos: list[Path], tirar_instrucoes: bool) -> Path:
    """Junta os arquivos num temporario, na ordem pedida."""
    pedacos: list[str] = []
    for caminho in textos:
        conteudo = caminho.read_text(encoding="utf-8")
        if tirar_instrucoes:
            conteudo = INSTRUCAO.sub("", conteudo)
            # colapsa o vazio que a remocao deixou
            conteudo = re.sub(r"\n{3,}", "\n\n", conteudo)
        pedacos.append(conteudo.strip())
    juntado = "\n\n\n".join(pedacos) + "\n"

    temporario = DESTINO / "_juntado"
    temporario.mkdir(parents=True, exist_ok=True)
    for antigo in temporario.glob("*.md"):
        antigo.unlink()
    alvo = temporario / "01-conteudo.md"
    alvo.write_text(juntado, encoding="utf-8")
    return temporario


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    gerador = RAIZ / "docs" / "gerar_docx.py"
    if not gerador.exists():
        print(f"{gerador} nao existe", file=sys.stderr)
        return 1

    falhas = 0
    for nome, titulo, entradas in PACOTES:
        caminhos = [FONTE / e for e in entradas]
        faltando = [c.name for c in caminhos if not c.exists()]
        if faltando:
            print(f"[falta] {nome}: {', '.join(faltando)}")
            falhas += 1
            continue

        # o material de apoio mantem as instrucoes; a submissao nao
        pasta = preparar(caminhos, tirar_instrucoes=nome != "apoio-para-o-aluno")
        saida = DESTINO / f"{nome}.docx"

        r = subprocess.run(
            [
                sys.executable,
                str(gerador),
                "--entrada", str(pasta.relative_to(RAIZ)),
                "--saida", str(saida.relative_to(RAIZ)),
                "--titulo", titulo,
            ],
            cwd=RAIZ, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 or not saida.exists():
            print(f"[erro] {nome}")
            for linha in ((r.stdout or "") + (r.stderr or "")).splitlines()[-6:]:
                print(f"        {linha}")
            falhas += 1
            continue

        tamanho = saida.stat().st_size / 1024
        print(f"[ok] {saida.name:<30} {tamanho:>8.1f} KB   "
              f"({len(entradas)} documento(s))")

    # limpa o temporario
    temporario = DESTINO / "_juntado"
    if temporario.exists():
        for arquivo in temporario.glob("*"):
            arquivo.unlink()
        temporario.rmdir()

    if falhas:
        print(f"\n{falhas} pacote(s) com problema")
        return 1
    print(f"\ngerado em {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
