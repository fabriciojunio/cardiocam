"""Converte a cascata de Haar do OpenCV para um JSON compacto.

Por que isto existe
-------------------

A versao web localizava o rosto pela mancha de pele. Medido na foto real de um
quarto comum, o metodo falhou pela razao mais simples possivel: **a parede bege
cai na faixa de crominancia da pele e e maior que o rosto**. A maior regiao
conexa de "pele" era a parede. Nenhum ajuste de limiar conserta isso, porque o
problema nao e o limiar, e a premissa de que a maior mancha cor de pele e um
rosto.

Na mesma imagem, a cascata de Haar acha o rosto com precisao, em tres variantes
do modelo, com e sem equalizacao, e em tres resolucoes. A diferenca e que ela
procura **estrutura** (a faixa dos olhos escura sobre as macas do rosto claras)
e nao cor.

O caminho obvio seria o BlazeFace via MediaPipe, e ele foi medido e descartado:
9,3 MB de runtime em WebAssembly, politica de seguranca do site que precisaria
ser afrouxada em duas diretivas, e impossibilidade de rodar na suite em Node.

A cascata de Haar nao tem nenhum desses problemas. E um classificador em
cascata de 1992 arvores sobre caracteristicas retangulares, avaliadas em tempo
constante por imagem integral. O modelo inteiro cabe em algumas centenas de
kilobytes de JSON, roda em JavaScript puro e e exatamente o mesmo algoritmo que
a versao em Python usa, o que coloca as duas implementacoes em paridade.

O que o JSON contem
-------------------

So o necessario para avaliar: tamanho da janela base, e por estagio o limiar e
a lista de classificadores fracos. Cada fraco tem o limiar do no, os dois
valores de folha e os retangulos da caracteristica com seus pesos.

Os numeros sao arredondados para seis casas. A cascata foi treinada com
tolerancia muito maior que isso, e o arredondamento corta quase um terco do
tamanho do arquivo sem mudar nenhuma decisao, o que esta conferido no teste de
paridade.

Uso:
    python ferramentas/converter_cascata.py
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import cv2
except ImportError:  # pragma: sem cobertura
    print("precisa do opencv-python para achar o arquivo da cascata", file=sys.stderr)
    raise

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "modelo" / "cascata-rosto.json"

# A variante `alt2` foi escolhida por medicao: na imagem real de teste as tres
# acharam o rosto, e a alt2 tem menos estagios que a default (20 contra 25),
# logo arquivo menor e avaliacao mais rapida, com a mesma deteccao.
NOME = "haarcascade_frontalface_alt2.xml"


def texto(no: ET.Element | None) -> str:
    return (no.text or "").strip() if no is not None else ""


def numeros(no: ET.Element | None) -> list[float]:
    return [float(x) for x in texto(no).split()]


def converter(caminho: Path) -> dict:
    raiz = ET.parse(caminho).getroot()
    cascata = raiz.find("cascade")
    if cascata is None:
        raise SystemExit(
            f"{caminho.name} nao esta no formato novo do OpenCV; "
            "este conversor nao trata o formato antigo"
        )

    largura = int(texto(cascata.find("width")))
    altura = int(texto(cascata.find("height")))

    # As caracteristicas sao compartilhadas entre estagios e referenciadas por
    # indice, entao sao convertidas uma vez so.
    caracteristicas = []
    for elemento in cascata.find("features").findall("_"):
        rects = []
        for r in elemento.find("rects").findall("_"):
            x, y, w, h, peso = numeros(r)
            rects.append([int(x), int(y), int(w), int(h), round(peso, 6)])
        caracteristicas.append(rects)

    estagios = []
    for estagio in cascata.find("stages").findall("_"):
        limiar = float(texto(estagio.find("stageThreshold")))
        fracos = []
        for fraco in estagio.find("weakClassifiers").findall("_"):
            internos = numeros(fraco.find("internalNodes"))
            folhas = numeros(fraco.find("leafValues"))

            # Cada no interno ocupa quatro numeros:
            #     [esquerda, direita, indiceDaCaracteristica, limiar]
            #
            # Esta cascata **nao** e feita de tocos de decisao, e supor que era
            # custou uma rodada inteira de depuracao. Uma versao anterior deste
            # conversor lia so os quatro primeiros numeros e jogava o resto da
            # arvore fora. O detector entao passava os dois primeiros estagios
            # e morria no terceiro, em qualquer posicao e qualquer escala, que
            # e exatamente o sintoma de avaliar arvore pela metade.
            #
            # Convencao dos ramos, conferida contra o OpenCV:
            #   valor positivo  -> indice de outro no interno desta arvore
            #   valor <= 0      -> folha de indice -valor
            nos = []
            for i in range(0, len(internos), 4):
                esquerda, direita, indice, limiar_do_no = internos[i:i + 4]
                nos.append([
                    int(esquerda), int(direita), int(indice), round(limiar_do_no, 6),
                ])
            fracos.append([nos, [round(f, 6) for f in folhas]])
        estagios.append([round(limiar, 6), fracos])

    return {
        "largura": largura,
        "altura": altura,
        "caracteristicas": caracteristicas,
        "estagios": estagios,
    }


def main() -> int:
    caminho = Path(cv2.data.haarcascades) / NOME
    if not caminho.exists():
        print(f"nao achei {caminho}", file=sys.stderr)
        return 1

    dados = converter(caminho)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, separators=(",", ":")), encoding="utf-8")

    total_fracos = sum(len(e[1]) for e in dados["estagios"])
    tamanho = DESTINO.stat().st_size / 1024
    print(f"origem: {caminho}")
    print(f"janela base: {dados['largura']}x{dados['altura']}")
    print(f"estagios: {len(dados['estagios'])}")
    print(f"classificadores fracos: {total_fracos}")
    print(f"caracteristicas: {len(dados['caracteristicas'])}")
    print(f"destino: {DESTINO}  ({tamanho:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
