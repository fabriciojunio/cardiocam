"""Exporta um quadro como tons de cinza cru, para a suite em Node ler.

Node nao decodifica PNG sem dependencia, e acrescentar uma so para teste seria
peso desnecessario. Um arquivo cru de um byte por pixel resolve, e tem a
vantagem de deixar explicito que o teste exercita o detector e nao o
decodificador de imagem.

Gera tambem um JSON com as dimensoes e com a caixa que o OpenCV encontra, que e
contra ela que a implementacao em JavaScript e comparada.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "testes" / "quadros"

# Quadros de referencia, gerados pelo renderizador sintetico do proprio
# projeto.
#
# **Por que sintetico e nao foto.** O detector foi depurado contra uma captura
# real, e e nela que a conclusao sobre o metodo se apoia. Mas o repositorio e
# publico, e comitar o rosto de alguem nele seria fazer exatamente o que a
# secao de privacidade deste projeto diz para nao fazer. O rosto sintetico tem
# estrutura suficiente para a cascata detectar, que e o que o teste precisa, e
# nao e o rosto de ninguem.
#
# A validacao contra a imagem real continua possivel e esta descrita no final
# deste arquivo: quem quiser refazer aponta para a propria captura, e o
# arquivo gerado fica fora do controle de versao.
PARAMETROS = [
    # (nome, tom de pele em BGR, iluminacao relativa, deslocamento)
    ("rosto-claro", (170, 195, 225), 1.0, (0, 0)),
    ("rosto-medio", (105, 130, 160), 1.0, (0, 0)),
    ("rosto-escuro", (48, 65, 88), 1.0, (0, 0)),
    # Pouca luz, que e a condicao em que a localizacao por cor falhava.
    ("rosto-pouca-luz", (105, 130, 160), 0.28, (0, 0)),
    # Fora do centro, para o teste nao premiar um detector que so olha o meio.
    ("rosto-deslocado", (130, 155, 185), 1.0, (40, -20)),
]

LARGURA_ALVO = 320


def main() -> int:
    sys.path.insert(0, str(RAIZ.parent / "src"))
    from cardiocam.fontes.sintetica import RenderizadorRosto

    DESTINO.mkdir(parents=True, exist_ok=True)
    indice = []

    ALTURA_ALVO = 240
    classificador = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    )

    for nome, tom, luz, deslocamento in PARAMETROS:
        renderizador = RenderizadorRosto(
            largura=LARGURA_ALVO, altura=ALTURA_ALVO, tom_pele=tom
        )
        quadro = renderizador.desenhar(
            modulacao=luz, deslocamento=deslocamento, ruido=2.0, semente=7
        )
        # A iluminacao reduzida tambem escurece o fundo, que no renderizador e
        # constante. Sem isso o cenario de pouca luz teria rosto escuro sobre
        # fundo claro, que nao e o caso real.
        if luz < 1.0:
            quadro = np.clip(quadro.astype(float) * luz, 0, 255).astype(np.uint8)

        # Cinza pelos mesmos coeficientes que o JavaScript usa, para a
        # comparacao medir o detector e nao a diferenca de conversao.
        b, g, r = quadro[:, :, 0], quadro[:, :, 1], quadro[:, :, 2]
        cinza = np.clip(0.299 * r + 0.587 * g + 0.114 * b, 0, 255).astype(np.uint8)

        (DESTINO / f"{nome}.cinza").write_bytes(cinza.tobytes())

        achados = classificador.detectMultiScale(
            cinza, scaleFactor=1.1, minNeighbors=3,
            minSize=(int(ALTURA_ALVO * 0.25), int(ALTURA_ALVO * 0.25)),
        )
        caixas = [
            {"x": int(x), "y": int(y), "largura": int(cw), "altura": int(ch)}
            for x, y, cw, ch in achados
        ]

        indice.append({
            "nome": nome,
            "arquivo": f"{nome}.cinza",
            "largura": LARGURA_ALVO,
            "altura": ALTURA_ALVO,
            "opencv": caixas,
            "tom_pele": list(tom),
            "iluminacao": luz,
        })
        print(f"{nome}: {LARGURA_ALVO}x{ALTURA_ALVO}, tom {tom}, luz {luz}, "
              f"{len(caixas)} rosto(s) pelo OpenCV: {caixas}")

    (DESTINO / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nindice: {DESTINO / 'indice.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
