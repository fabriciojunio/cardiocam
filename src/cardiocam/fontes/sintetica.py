"""Simulador de vídeo com pulso de frequência conhecida.

Este módulo é o que torna o projeto verificável. Medir alguém de verdade não
prova que o sistema está certo, porque não se sabe o valor correto sem um
oxímetro ao lado. Aqui a frequência é escolhida por nós, então o erro é
mensurável com exatidão.

O simulador reproduz os quatro fenômenos que atrapalham a medição real:

1. Pulso não senoidal. A onda de pulso tem subida rápida e descida lenta, então
   é montada com harmônicos.
2. Ruído do sensor, por pixel e independente entre pixels. Além de realista, ele
   funciona como dithering: sem ele, uma região de cor perfeitamente uniforme
   seria quantizada para o mesmo inteiro em todos os pixels e a média espacial
   não conseguiria resolver variações abaixo de um nível.
3. Deriva e tremor de iluminação, que afetam os três canais na mesma proporção.
   É a distorção que CHROM e POS foram feitos para cancelar e que o método do
   canal verde não cancela.
4. Movimento da cabeça, que desloca a região de interesse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import cv2
import numpy as np

from cardiocam.dominio.sinal import SerieRGB
from cardiocam.fontes.base import Quadro
from cardiocam.visao.geometria import Retangulo

# Sensibilidade relativa de cada canal à variação de volume sanguíneo. O verde
# domina porque a absorção da hemoglobina tem máximo perto de 540 nm.
GANHO_CANAL = {"vermelho": 0.30, "verde": 1.00, "azul": 0.55}

# Amplitudes dos harmônicos que dão à onda o formato de pletismograma.
HARMONICOS_PADRAO = (1.0, 0.35, 0.12)


@dataclass(frozen=True, slots=True)
class ParametrosSimulacao:
    """Tudo que descreve um cenário sintético."""

    bpm: float = 72.0
    duracao_s: float = 20.0
    fps: float = 30.0
    largura: int = 320
    altura: int = 240

    amplitude_pulso: float = 0.02
    """Variação relativa de intensidade causada pelo pulso. Na pele real fica
    entre 0,1% e 1%; usamos um pouco mais para os testes rodarem em janelas
    curtas."""

    harmonicos: tuple[float, ...] = HARMONICOS_PADRAO
    ruido_sensor: float = 2.0
    """Desvio padrão do ruído por pixel, em níveis de intensidade."""

    deriva_iluminacao: float = 0.0
    """Rampa lenta de iluminação ao longo do vídeo, em fração da intensidade."""

    amplitude_tremor: float = 0.0
    tremor_iluminacao_hz: float = 0.2
    """Oscilação de iluminação comum aos três canais."""

    movimento_px: float = 0.0
    movimento_hz: float = 0.15
    """Deslocamento senoidal da cabeça, em pixels."""

    tom_pele: tuple[int, int, int] = (150, 175, 205)
    """Cor base da pele em BGR."""

    semente: int = 0
    jitter_fps: float = 0.0
    """Desvio padrão do erro de temporização entre quadros, em segundos."""

    fase: float = 0.0

    def __post_init__(self) -> None:
        if self.bpm <= 0:
            raise ValueError("O BPM simulado precisa ser positivo.")
        if self.fps <= 0:
            raise ValueError("A taxa de quadros precisa ser positiva.")
        if self.duracao_s <= 0:
            raise ValueError("A duração precisa ser positiva.")
        if self.largura < 32 or self.altura < 32:
            raise ValueError("O quadro simulado precisa ter ao menos 32x32 pixels.")

    @property
    def frequencia_hz(self) -> float:
        return self.bpm / 60.0

    @property
    def total_quadros(self) -> int:
        return max(2, int(round(self.duracao_s * self.fps)))


def instantes(parametros: ParametrosSimulacao) -> np.ndarray:
    """Carimbos de tempo dos quadros, com jitter opcional.

    O jitter simula a irregularidade real da captura: uma webcam anunciada como
    30 fps entrega quadros com intervalos que variam vários milissegundos.
    """
    base = np.arange(parametros.total_quadros, dtype=float) / parametros.fps
    if parametros.jitter_fps <= 0:
        return base
    gerador = np.random.default_rng(parametros.semente + 977)
    perturbado = base + gerador.normal(0.0, parametros.jitter_fps, base.size)
    perturbado[0] = base[0]
    # Garante monotonicidade: o tempo não anda para trás.
    return np.maximum.accumulate(perturbado)


def onda_de_pulso(
    tempos: np.ndarray, frequencia_hz: float, harmonicos: tuple[float, ...], fase: float = 0.0
) -> np.ndarray:
    """Forma de onda do pulso, normalizada para amplitude máxima unitária."""
    onda = np.zeros_like(tempos, dtype=float)
    for ordem, amplitude in enumerate(harmonicos, start=1):
        onda += amplitude * np.sin(2.0 * np.pi * ordem * frequencia_hz * tempos + fase)
    maximo = float(np.max(np.abs(onda)))
    return onda / maximo if maximo > 1e-12 else onda


def _distorcao_iluminacao(
    tempos: np.ndarray, parametros: ParametrosSimulacao
) -> np.ndarray:
    """Fator multiplicativo comum aos três canais."""
    distorcao = np.ones_like(tempos, dtype=float)
    if parametros.deriva_iluminacao:
        duracao = max(1e-9, float(tempos[-1] - tempos[0]))
        distorcao += parametros.deriva_iluminacao * (tempos - tempos[0]) / duracao
    if parametros.amplitude_tremor:
        distorcao += parametros.amplitude_tremor * np.sin(
            2.0 * np.pi * parametros.tremor_iluminacao_hz * tempos
        )
    return distorcao


def gerar_serie_rgb(parametros: ParametrosSimulacao) -> SerieRGB:
    """Série RGB analítica, sem renderizar imagem.

    Atalho usado nos testes que exercitam apenas a parte de sinais. É a mesma
    física do simulador de vídeo, sem o custo de desenhar e reamostrar quadros.
    """
    tempos = instantes(parametros)
    pulso = onda_de_pulso(
        tempos, parametros.frequencia_hz, parametros.harmonicos, parametros.fase
    )
    iluminacao = _distorcao_iluminacao(tempos, parametros)
    gerador = np.random.default_rng(parametros.semente)

    azul_base, verde_base, vermelho_base = parametros.tom_pele
    canais = {}
    for nome, base in (
        ("vermelho", vermelho_base),
        ("verde", verde_base),
        ("azul", azul_base),
    ):
        ganho = GANHO_CANAL[nome]
        limpo = base * iluminacao * (1.0 + parametros.amplitude_pulso * ganho * pulso)
        # Ruído já reduzido pela média espacial sobre a região de interesse.
        ruido = gerador.normal(0.0, parametros.ruido_sensor / 40.0, tempos.size)
        canais[nome] = limpo + ruido

    return SerieRGB(
        canais["vermelho"],
        canais["verde"],
        canais["azul"],
        parametros.fps,
        tempos,
    )


@dataclass
class RenderizadorRosto:
    """Desenha um rosto frontal sintético detectável pela cascata de Haar.

    Não é fotorrealismo: é o mínimo de estrutura (região dos olhos escura sobre
    maçãs do rosto claras, sombra do nariz, boca) que produz o padrão de
    contraste que as características de Haar procuram.

    A renderização é separada em duas camadas porque a composição é linear na
    cor da pele. Tudo que é desenhado tem cor constante ou proporcional ao tom
    de pele, e o desfoque gaussiano também é linear, então o quadro final vale

        imagem(m) = constante + m · camada_de_pele

    para qualquer multiplicador m. Calculamos as duas camadas uma única vez e
    cada quadro vira uma multiplicação e uma soma, em vez de uma dezena de
    chamadas de desenho. Além de deixar a suíte de testes viável, isso garante
    que a modulação seja exatamente a pretendida, sem erro de rasterização.
    """

    largura: int = 320
    altura: int = 240
    tom_pele: tuple[int, int, int] = (150, 175, 205)
    cor_fundo: int = 60
    _gerador: np.random.Generator = field(
        default_factory=lambda: np.random.default_rng(0), repr=False
    )
    _camadas_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = field(
        default_factory=dict, repr=False
    )

    def caixa_esperada(self, deslocamento: tuple[int, int] = (0, 0)) -> Retangulo:
        """Região aproximada do rosto, útil para conferir a detecção."""
        centro_x = self.largura // 2 + deslocamento[0]
        centro_y = self.altura // 2 + deslocamento[1]
        raio_x = int(self.largura * 0.20)
        raio_y = int(self.altura * 0.30)
        return Retangulo(
            centro_x - raio_x, centro_y - raio_y, 2 * raio_x, 2 * raio_y
        )

    def _rasterizar(
        self, tom_pele: tuple[float, float, float], deslocamento: tuple[int, int]
    ) -> np.ndarray:
        """Desenha o rosto com um tom de pele arbitrário, sem ruído."""
        imagem = np.full(
            (self.altura, self.largura, 3), float(self.cor_fundo), dtype=np.float64
        )
        centro_x = self.largura // 2 + deslocamento[0]
        centro_y = self.altura // 2 + deslocamento[1]
        raio_x = int(self.largura * 0.20)
        raio_y = int(self.altura * 0.30)
        pele = tuple(float(canal) for canal in tom_pele)

        cv2.ellipse(imagem, (centro_x, centro_y + raio_y),
                    (raio_x // 2, raio_y // 3), 0, 0, 360, pele, -1)
        cv2.ellipse(imagem, (centro_x, centro_y), (raio_x, raio_y), 0, 0, 360, pele, -1)
        cv2.ellipse(imagem, (centro_x, centro_y - int(raio_y * 0.75)),
                    (int(raio_x * 1.05), int(raio_y * 0.45)), 0, 180, 360,
                    (35, 40, 55), -1)

        # As proporções abaixo perseguem o padrão de contraste que as
        # características de Haar de um rosto codificam: a faixa dos olhos
        # escura, o dorso do nariz e as maçãs do rosto claros logo abaixo e ao
        # centro, e a testa clara acima. Sem esse contraste explícito, a cascata
        # simplesmente não enxerga o rosto desenhado.
        olho_dx = int(raio_x * 0.42)
        olho_dy = int(raio_y * 0.20)

        # Faixa horizontal escurecida cobrindo os dois olhos de uma vez.
        cv2.ellipse(imagem, (centro_x, centro_y - olho_dy),
                    (int(raio_x * 0.86), int(raio_y * 0.20)), 0, 0, 360,
                    tuple(canal * 0.72 for canal in pele), -1)

        for lado in (-1, 1):
            olho_x = centro_x + lado * olho_dx
            olho_y = centro_y - olho_dy
            cv2.ellipse(imagem, (olho_x, olho_y),
                        (int(raio_x * 0.30), int(raio_y * 0.16)), 0, 0, 360,
                        tuple(canal * 0.58 for canal in pele), -1)
            cv2.ellipse(imagem, (olho_x, olho_y),
                        (int(raio_x * 0.19), int(raio_y * 0.095)), 0, 0, 360,
                        (240, 240, 240), -1)
            cv2.circle(imagem, (olho_x, olho_y), max(2, int(raio_x * 0.10)),
                       (35, 30, 28), -1)
            cv2.ellipse(imagem, (olho_x, olho_y - int(raio_y * 0.20)),
                        (int(raio_x * 0.32), int(raio_y * 0.06)), 0, 180, 360,
                        (40, 45, 58), -1)

        # Dorso do nariz claro, separando as duas órbitas escuras.
        cv2.ellipse(imagem, (centro_x, centro_y - int(raio_y * 0.02)),
                    (int(raio_x * 0.11), int(raio_y * 0.30)), 0, 0, 360,
                    tuple(min(255.0, canal * 1.14) for canal in pele), -1)

        # Maçãs do rosto claras logo abaixo da faixa dos olhos.
        for lado in (-1, 1):
            cv2.ellipse(imagem,
                        (centro_x + lado * int(raio_x * 0.52),
                         centro_y + int(raio_y * 0.16)),
                        (int(raio_x * 0.32), int(raio_y * 0.20)), 0, 0, 360,
                        tuple(min(255.0, canal * 1.10) for canal in pele), -1)

        # Sombra da base do nariz e boca.
        cv2.ellipse(imagem, (centro_x, centro_y + int(raio_y * 0.32)),
                    (int(raio_x * 0.20), int(raio_y * 0.08)), 0, 0, 360,
                    tuple(canal * 0.80 for canal in pele), -1)
        cv2.ellipse(imagem, (centro_x, centro_y + int(raio_y * 0.54)),
                    (int(raio_x * 0.36), int(raio_y * 0.10)), 0, 0, 360,
                    (88, 88, 138), -1)
        cv2.ellipse(imagem, (centro_x, centro_y + int(raio_y * 0.66)),
                    (int(raio_x * 0.30), int(raio_y * 0.07)), 0, 0, 360,
                    tuple(canal * 0.86 for canal in pele), -1)

        return cv2.GaussianBlur(imagem, (5, 5), 0)

    def camadas(
        self, deslocamento: tuple[int, int] = (0, 0)
    ) -> tuple[np.ndarray, np.ndarray]:
        """Camada constante e camada proporcional ao tom de pele."""
        chave = (int(deslocamento[0]), int(deslocamento[1]))
        if chave not in self._camadas_cache:
            constante = self._rasterizar((0.0, 0.0, 0.0), chave)
            com_pele = self._rasterizar(
                tuple(float(canal) for canal in self.tom_pele), chave
            )
            # Precisão simples basta: o quadro final é quantizado em 8 bits, e
            # trabalhar em float32 reduz pela metade o custo de gerar o ruído,
            # que domina o tempo de renderização.
            self._camadas_cache[chave] = (
                constante.astype(np.float32),
                (com_pele - constante).astype(np.float32),
            )
        return self._camadas_cache[chave]

    def desenhar(
        self,
        modulacao: float | tuple[float, float, float] = 1.0,
        deslocamento: tuple[int, int] = (0, 0),
        ruido: float = 2.0,
        semente: int | None = None,
    ) -> np.ndarray:
        """Renderiza um quadro.

        `modulacao` multiplica a camada de pele. Aceita um escalar (variação de
        intensidade pura, igual nos três canais) ou uma tripla em ordem BGR, que
        é o caso fisicamente correto: a hemoglobina absorve muito mais no verde
        que no vermelho, então o pulso não é uma mudança de brilho, é uma
        mudança de cor. Essa diferença entre canais é exatamente a informação
        que CHROM e POS exploram para separar sangue de iluminação.
        """
        constante, camada_pele = self.camadas(deslocamento)

        if np.isscalar(modulacao):
            fatores = np.array([modulacao] * 3, dtype=np.float32)
        else:
            fatores = np.asarray(modulacao, dtype=np.float32)
            if fatores.size != 3:
                raise ValueError("A modulação precisa ser um escalar ou uma tripla BGR.")

        imagem = constante + camada_pele * fatores.reshape(1, 1, 3)

        if ruido > 0:
            gerador = (
                np.random.default_rng(semente) if semente is not None else self._gerador
            )
            imagem += gerador.standard_normal(imagem.shape, dtype=np.float32) * np.float32(ruido)

        return np.clip(imagem, 0, 255).astype(np.uint8)


class FonteSintetica:
    """Fonte de vídeo que gera quadros com pulso de frequência conhecida."""

    def __init__(self, parametros: ParametrosSimulacao | None = None) -> None:
        self.parametros = parametros or ParametrosSimulacao()
        self.fps = self.parametros.fps
        self._renderizador = RenderizadorRosto(
            largura=self.parametros.largura,
            altura=self.parametros.altura,
            tom_pele=self.parametros.tom_pele,
        )
        self._tempos = instantes(self.parametros)
        self._pulso = onda_de_pulso(
            self._tempos,
            self.parametros.frequencia_hz,
            self.parametros.harmonicos,
            self.parametros.fase,
        )
        self._iluminacao = _distorcao_iluminacao(self._tempos, self.parametros)

    @property
    def bpm_verdadeiro(self) -> float:
        """O valor que o sistema deveria encontrar."""
        return self.parametros.bpm

    @property
    def total_quadros(self) -> int:
        return self.parametros.total_quadros

    def caixa_esperada(self) -> Retangulo:
        return self._renderizador.caixa_esperada()

    def modulacao_em(self, indice: int) -> np.ndarray:
        """Multiplicador da pele neste quadro, em ordem BGR.

        Junta as duas coisas que mexem na cor da pele: a iluminação, que age
        igual nos três canais, e o pulso, que age com peso diferente em cada um.
        Um método que só olhe a intensidade não consegue distinguir as duas; os
        métodos cromáticos conseguem exatamente porque os pesos diferem.
        """
        parametros = self.parametros
        pulso = float(self._pulso[indice])
        iluminacao = float(self._iluminacao[indice])
        ganhos = (
            GANHO_CANAL["azul"],
            GANHO_CANAL["verde"],
            GANHO_CANAL["vermelho"],
        )
        return np.array(
            [
                iluminacao * (1.0 + parametros.amplitude_pulso * ganho * pulso)
                for ganho in ganhos
            ],
            dtype=float,
        )

    def deslocamento_em(self, indice: int) -> tuple[int, int]:
        """Posição da cabeça neste quadro, em pixels de deslocamento."""
        parametros = self.parametros
        if not parametros.movimento_px:
            return (0, 0)
        desloca = parametros.movimento_px * np.sin(
            2.0 * np.pi * parametros.movimento_hz * self._tempos[indice]
        )
        return (int(round(desloca)), int(round(desloca * 0.4)))

    def quadro_em(self, indice: int) -> Quadro:
        """Renderiza um quadro específico."""
        quadro = self._renderizador.desenhar(
            modulacao=self.modulacao_em(indice),
            deslocamento=self.deslocamento_em(indice),
            ruido=self.parametros.ruido_sensor,
            semente=self.parametros.semente + indice,
        )
        return quadro, float(self._tempos[indice])

    def quadros(self) -> Iterator[Quadro]:
        for indice in range(self.parametros.total_quadros):
            yield self.quadro_em(indice)

    def fechar(self) -> None:
        """Não há recurso a liberar; existe para cumprir o contrato da fonte."""
        return None
