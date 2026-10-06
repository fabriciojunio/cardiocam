"""Gera um vídeo y4m com pulso de frequência conhecida, para a câmera falsa.

O Chromium aceita `--use-file-for-fake-video-capture=arquivo.y4m` e passa a
entregar aquele arquivo em laço no lugar da câmera. Isso dá o que faltava para
testar a página inteira sem ninguém na frente da webcam: um rosto com
frequência cardíaca escolhida por nós, entrando pelo mesmo caminho que uma
câmera de verdade, com `getUserMedia`, `requestVideoFrameCallback` e tudo o
mais.

O conteúdo sai do mesmo simulador que a suíte em Python usa, então o vídeo não
é um arquivo solto que alguém gravou: é o cenário sintético do projeto, com a
física que já está documentada e testada.

O arquivo repete em laço, e o laço é uma emenda: entre o último quadro e o
primeiro há um salto de fase. Por isso a duração é escolhida para conter um
número inteiro de batimentos, o que faz a emenda cair exatamente onde o ciclo
recomeça e some do espectro.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao


def quadros_com_ciclos_inteiros(bpm: float, alvo_s: float, fps: float) -> int:
    """Escolhe o número de quadros que fecha um número inteiro de batimentos.

    As duas condições precisam valer ao mesmo tempo: o arquivo tem um número
    inteiro de quadros, e o trecho tem um número inteiro de ciclos. Fechar só a
    segunda deixa o último quadro pela metade e o salto volta por outra porta.

    Nem todo par de bpm e taxa admite solução exata. Com 72 batimentos a 20
    quadros por segundo, um ciclo dura 16,67 quadros, e nenhum múltiplo inteiro
    de ciclos cai num número inteiro de quadros em duração razoável. Por isso a
    função devolve a melhor aproximação e o chamador avisa quanto sobrou: com a
    emenda mal fechada, o espectro ganha uma risca na frequência do laço, e um
    teste que não soubesse disso culparia o algoritmo.
    """
    quadros_por_ciclo = 60.0 * fps / bpm
    melhor = None
    for ciclos in range(1, 1 + int(4 * alvo_s * bpm / 60.0)):
        exato = ciclos * quadros_por_ciclo
        quadros = round(exato)
        if quadros < fps:  # menos de um segundo não serve de laço
            continue
        sobra = abs(exato - quadros) / quadros_por_ciclo  # em fração de ciclo
        distancia = abs(quadros / fps - alvo_s)
        nota = (round(sobra, 6), distancia)
        if melhor is None or nota < melhor[0]:
            melhor = (nota, quadros, sobra)
    assert melhor is not None, "nenhuma duração possível"
    _, quadros, sobra = melhor
    if sobra > 1e-6:
        print(
            f"aviso: a emenda do laço sobra {sobra:.4f} de ciclo. "
            f"Escolha bpm e taxa que fechem (por exemplo 75 bpm a 20 q/s)."
        )
    return quadros


def escrever_y4m(destino: Path, parametros: ParametrosSimulacao) -> int:
    fonte = FonteSintetica(parametros)
    largura, altura = parametros.largura, parametros.altura
    # O formato pede dimensões pares nos dois eixos, porque o plano de cor tem
    # metade da resolução.
    assert largura % 2 == 0 and altura % 2 == 0, "largura e altura precisam ser pares"

    taxa = parametros.fps
    numerador = round(taxa * 1000)
    cabecalho = (
        f"YUV4MPEG2 W{largura} H{altura} F{numerador}:1000 Ip A1:1 C420mpeg2\n"
    ).encode("ascii")

    escritos = 0
    with destino.open("wb") as saida:
        saida.write(cabecalho)
        for imagem, _instante in fonte.quadros():
            yuv = cv2.cvtColor(imagem, cv2.COLOR_BGR2YUV_I420)
            saida.write(b"FRAME\n")
            saida.write(yuv.tobytes())
            escritos += 1
    return escritos


def principal() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--saida", type=Path, required=True)
    analisador.add_argument("--bpm", type=float, default=72.0)
    analisador.add_argument("--fps", type=float, default=20.0)
    analisador.add_argument("--duracao", type=float, default=12.0)
    analisador.add_argument("--largura", type=int, default=640)
    analisador.add_argument("--altura", type=int, default=480)
    argumentos = analisador.parse_args()

    quadros_alvo = quadros_com_ciclos_inteiros(
        argumentos.bpm, argumentos.duracao, argumentos.fps
    )
    duracao = quadros_alvo / argumentos.fps
    parametros = ParametrosSimulacao(
        bpm=argumentos.bpm,
        duracao_s=duracao,
        fps=argumentos.fps,
        largura=argumentos.largura,
        altura=argumentos.altura,
    )
    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    quadros = escrever_y4m(argumentos.saida, parametros)
    tamanho = argumentos.saida.stat().st_size / 1e6
    batimentos = duracao * argumentos.bpm / 60.0
    print(
        f"{argumentos.saida}: {quadros} quadros, {duracao:.3f} s, "
        f"{batimentos:.2f} batimentos, {tamanho:.1f} MB"
    )


if __name__ == "__main__":
    principal()
