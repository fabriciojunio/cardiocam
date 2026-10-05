"""Gera a monografia em Word a partir dos arquivos de texto.

**Por que gerar em vez de escrever direto no Word.** Os numeros da monografia
saem de script; se o Word fosse escrito a mao, cada reexecucao exigiria copiar
numero por numero e a chance de um ficar para tras e de cem por cento. Aqui o
documento sai do mesmo arquivo que o resto do projeto le, entao reexecutar os
experimentos e regerar o Word mantem os dois em acordo.

**O que o conversor cobre**, porque e o que a monografia usa:

    # ate ######      titulos, mapeados para os estilos de titulo do Word
    paragrafo         texto corrido, com **negrito**, *italico* e `codigo`
    | a | b |         tabela com cabecalho, com estilo de grade
    ```              bloco de codigo, em fonte monoespacada
    ![x](caminho)    figura, com legenda
    - item           lista com marcador
    1. item          lista numerada
    > citacao        citacao recuada

O que ele **nao** cobre esta declarado: nota de rodape, equacao e referencia
cruzada automatica. A monografia nao usa os tres, e um conversor que finge
cobrir o que nao cobre e pior que um que diz o que faz.

Uso:
    python engenharia/gerar_docx.py
    python engenharia/gerar_docx.py --entrada monografia --saida artefatos/monografia.docx
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor
except ImportError:  # pragma: sem cobertura
    print(
        "falta o python-docx. Instale com: pip install python-docx",
        file=sys.stderr,
    )
    raise

RAIZ = Path(__file__).resolve().parents[1]

# As marcas de formatacao dentro de um paragrafo. A ordem importa: `codigo`
# vem primeiro para que um trecho entre crases nao tenha asteriscos
# interpretados dentro dele.
MARCAS = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")


def _escrever_com_marcas(paragrafo, texto: str) -> None:
    """Quebra o texto em trechos e aplica negrito, italico e monoespacado."""
    for pedaco in MARCAS.split(texto):
        if not pedaco:
            continue
        if pedaco.startswith("`") and pedaco.endswith("`"):
            r = paragrafo.add_run(pedaco[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
        elif pedaco.startswith("**") and pedaco.endswith("**"):
            paragrafo.add_run(pedaco[2:-2]).bold = True
        elif pedaco.startswith("*") and pedaco.endswith("*") and len(pedaco) > 2:
            paragrafo.add_run(pedaco[1:-1]).italic = True
        else:
            paragrafo.add_run(pedaco)


def _tabela(doc, linhas: list[str]) -> None:
    """Uma tabela de Markdown vira tabela do Word com estilo de grade.

    A linha de separacao (`|---|---|`) e descartada, e a primeira linha vira
    cabecalho em negrito.
    """
    celulas = [
        [c.strip() for c in linha.strip().strip("|").split("|")] for linha in linhas
    ]
    celulas = [c for c in celulas if not all(set(x) <= set("-: ") for x in c)]
    if not celulas:
        return
    colunas = max(len(linha) for linha in celulas)
    tabela = doc.add_table(rows=len(celulas), cols=colunas)
    tabela.style = "Table Grid"
    for i, linha in enumerate(celulas):
        for j in range(colunas):
            texto = linha[j] if j < len(linha) else ""
            p = tabela.cell(i, j).paragraphs[0]
            _escrever_com_marcas(p, texto)
            if i == 0:
                for r in p.runs:
                    r.bold = True
    doc.add_paragraph()


def _codigo(doc, linhas: list[str]) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run("\n".join(linhas))
    r.font.name = "Consolas"
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x30, 0x30, 0x30)


def _figura(doc, caminho: Path, legenda: str) -> bool:
    if not caminho.exists():
        return False
    doc.add_picture(str(caminho), width=Cm(15))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if legenda:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(legenda)
        r.italic = True
        r.font.size = Pt(9)
    return True


def converter(texto: str, doc, raiz: Path, nivel_extra: int = 0) -> dict:
    """Converte um documento de texto para dentro do `doc`. Devolve a contagem."""
    contagem = {"titulos": 0, "paragrafos": 0, "tabelas": 0, "codigo": 0,
                "figuras": 0, "figuras_faltando": 0, "listas": 0}
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        despido = linha.strip()

        if not despido:
            i += 1
            continue

        if despido.startswith("```"):
            bloco = []
            i += 1
            while i < len(linhas) and not linhas[i].strip().startswith("```"):
                bloco.append(linhas[i])
                i += 1
            i += 1
            _codigo(doc, bloco)
            contagem["codigo"] += 1
            continue

        if despido.startswith("|") and despido.endswith("|"):
            bloco = []
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                bloco.append(linhas[i])
                i += 1
            _tabela(doc, bloco)
            contagem["tabelas"] += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", despido)
        if m:
            nivel = min(len(m.group(1)) + nivel_extra, 9)
            doc.add_heading(m.group(2).strip(), level=nivel)
            contagem["titulos"] += 1
            i += 1
            continue

        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", despido)
        if m:
            legenda, destino = m.group(1), m.group(2)
            if _figura(doc, (raiz / destino).resolve(), legenda):
                contagem["figuras"] += 1
            else:
                p = doc.add_paragraph()
                r = p.add_run(f"[figura nao encontrada: {destino}]")
                r.italic = True
                contagem["figuras_faltando"] += 1
            i += 1
            continue

        if despido.startswith("> "):
            p = doc.add_paragraph(style="Intense Quote")
            _escrever_com_marcas(p, despido[2:])
            contagem["paragrafos"] += 1
            i += 1
            continue

        m = re.match(r"^[-*]\s+(.*)$", despido)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            _escrever_com_marcas(p, m.group(1))
            contagem["listas"] += 1
            i += 1
            continue

        m = re.match(r"^\d+\.\s+(.*)$", despido)
        if m:
            p = doc.add_paragraph(style="List Number")
            _escrever_com_marcas(p, m.group(1))
            contagem["listas"] += 1
            i += 1
            continue

        if despido.startswith("---"):
            i += 1
            continue

        # paragrafo corrido: junta as linhas ate a proxima linha em branco, que
        # e como o Markdown trata quebra simples
        bloco = [despido]
        i += 1
        while i < len(linhas) and linhas[i].strip() and not re.match(
            r"^(#{1,6}\s|\||```|[-*]\s|\d+\.\s|>\s|!\[|---)", linhas[i].strip()
        ):
            bloco.append(linhas[i].strip())
            i += 1
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _escrever_com_marcas(p, " ".join(bloco))
        contagem["paragrafos"] += 1

    return contagem


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="monografia")
    ap.add_argument("--saida", default="artefatos/monografia.docx")
    ap.add_argument(
        "--titulo",
        default="Aprendizado evolutivo da estrutura de dependencia entre "
        "instituicoes financeiras brasileiras",
    )
    ap.add_argument("--autor", default="Fabricio Junio Almeida Dias")
    args = ap.parse_args()

    entrada = RAIZ / args.entrada
    if not entrada.exists():
        print(f"{entrada} nao existe", file=sys.stderr)
        return 1
    arquivos = sorted(entrada.glob("*.md"))
    if not arquivos:
        print(f"nenhum .md em {entrada}", file=sys.stderr)
        return 1

    doc = Document()
    # corpo em 12 pt e espacamento de 1,5, que e o padrao de monografia
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)
    estilo.paragraph_format.space_after = Pt(8)
    estilo.paragraph_format.line_spacing = 1.4

    doc.add_heading(args.titulo, level=0)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(args.autor).bold = True

    total = {}
    print(f"gerando a partir de {len(arquivos)} arquivos:")
    for caminho in arquivos:
        print(f"  {caminho.name}")
        doc.add_page_break()
        c = converter(caminho.read_text(encoding="utf-8"), doc, RAIZ)
        for k, v in c.items():
            total[k] = total.get(k, 0) + v

    destino = RAIZ / args.saida
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destino)

    print("\n== o que entrou ==")
    for k, v in total.items():
        print(f"  {k}: {v}")
    if total.get("figuras_faltando"):
        print(f"\n  ATENCAO: {total['figuras_faltando']} figuras nao foram "
              f"encontradas e viraram marcador no texto. Rode os experimentos "
              f"que as geram antes de entregar.")
    tamanho = destino.stat().st_size / 1024
    print(f"\n{destino} ({tamanho:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
