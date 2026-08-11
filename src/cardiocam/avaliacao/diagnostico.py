"""Diagnóstico sobre captura real.

Todo o resto do projeto é validado contra simulação, o que permite medir erro
com exatidão mas tem um limite claro: valida contra o modelo, não contra a
realidade. Quando a medição real não bate com a esperada, é preciso olhar o
sinal que a câmera de fato entregou.

Este módulo grava, de uma única captura, as séries de várias configurações ao
mesmo tempo, e depois compara todas sobre exatamente os mesmos quadros. Assim a
comparação é justa: não há diferença de iluminação, de postura ou de momento
entre uma configuração e outra.

Nada de imagem é gravado. O arquivo tem apenas números: instante, médias de cor
por região, contagem de pixels e posição da caixa do rosto.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import BandaCardiaca, SerieRGB
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo
from cardiocam.visao.detector_face import DetectorHaar
from cardiocam.visao.extrator import ExtratorRGB
from cardiocam.visao.fundo import media_do_fundo
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.rastreador import RastreadorRosto
from cardiocam.visao.roi import RegiaoInteresse

# Conjuntos de regiões testados lado a lado. O objetivo é descobrir, no rosto
# real, se a região ampliada realmente ajuda ou se ela passa a incluir cabelo e
# fundo, cuja fronteira redesenhada a cada quadro injeta ruído.
VARIANTES_ROI: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "testa_pequena": ((0.32, 0.16, 0.68, 0.30),),
    "testa_grande": ((0.24, 0.12, 0.76, 0.32),),
    "bochechas": ((0.10, 0.52, 0.36, 0.78), (0.64, 0.52, 0.90, 0.78)),
    "conjunto_pequeno": (
        (0.32, 0.16, 0.68, 0.30),
        (0.13, 0.55, 0.35, 0.75),
        (0.65, 0.55, 0.87, 0.75),
    ),
    "conjunto_grande": (
        (0.24, 0.12, 0.76, 0.32),
        (0.08, 0.50, 0.38, 0.80),
        (0.62, 0.50, 0.92, 0.80),
    ),
}


@dataclass
class Captura:
    """Séries brutas coletadas de uma sessão real."""

    instantes: list[float] = field(default_factory=list)
    por_variante: dict[str, list[tuple[float, float, float]]] = field(default_factory=dict)
    pixels_por_variante: dict[str, list[int]] = field(default_factory=dict)
    fundo: list[tuple[float, float, float] | None] = field(default_factory=list)
    caixas: list[tuple[int, int, int, int]] = field(default_factory=list)
    quadros_sem_rosto: int = 0

    @property
    def total(self) -> int:
        return len(self.instantes)

    @property
    def fps(self) -> float:
        if self.total < 2:
            return 0.0
        intervalos = np.diff(np.asarray(self.instantes))
        intervalos = intervalos[intervalos > 0]
        return float(1.0 / np.median(intervalos)) if intervalos.size else 0.0

    def tremor_da_caixa(self) -> tuple[float, float]:
        """Desvio padrão da posição e do tamanho da caixa do rosto, em pixels.

        Tremor alto significa que a região medida muda de lugar entre quadros, e
        isso entra no sinal como artefato de amplitude muito maior que o pulso.
        """
        if len(self.caixas) < 2:
            return 0.0, 0.0
        matriz = np.asarray(self.caixas, dtype=float)
        centro_x = matriz[:, 0] + matriz[:, 2] / 2
        centro_y = matriz[:, 1] + matriz[:, 3] / 2
        posicao = float(np.hypot(np.std(centro_x), np.std(centro_y)))
        return posicao, float(np.std(matriz[:, 2]))


def capturar(
    fonte,
    duracao_s: float = 45.0,
    ao_progredir=None,
) -> Captura:
    """Coleta as séries de todas as variantes a partir de uma fonte de vídeo."""
    detector = DetectorHaar()
    rastreador = RastreadorRosto(detector, intervalo_deteccao=2)
    extratores = {
        nome: ExtratorRGB(medir_fundo=False) for nome in VARIANTES_ROI
    }
    captura = Captura()
    captura.por_variante = {nome: [] for nome in VARIANTES_ROI}
    captura.pixels_por_variante = {nome: [] for nome in VARIANTES_ROI}

    inicio = None
    for quadro, instante in fonte.quadros():
        if inicio is None:
            inicio = instante
        decorrido = instante - inicio
        if decorrido > duracao_s:
            break
        if ao_progredir:
            ao_progredir(decorrido / duracao_s)

        deteccao = rastreador.atualizar(quadro)
        if deteccao.falhou:
            captura.quadros_sem_rosto += 1
            continue
        caixa = deteccao.desempacotar()

        medidas: dict[str, tuple[float, float, float]] = {}
        contagens: dict[str, int] = {}
        completo = True
        for nome, fracoes in VARIANTES_ROI.items():
            regioes = [caixa.fracao(*f) for f in fracoes]
            resultado = _media_das_regioes(quadro, regioes, extratores[nome])
            if resultado is None:
                completo = False
                break
            medidas[nome], contagens[nome] = resultado

        if not completo:
            captura.quadros_sem_rosto += 1
            continue

        captura.instantes.append(instante)
        captura.caixas.append(caixa.como_tupla())
        captura.fundo.append(media_do_fundo(quadro, caixa))
        for nome in VARIANTES_ROI:
            captura.por_variante[nome].append(medidas[nome])
            captura.pixels_por_variante[nome].append(contagens[nome])

    fonte.fechar()
    return captura


def _media_das_regioes(
    quadro: np.ndarray, regioes: list[Retangulo], extrator: ExtratorRGB
) -> tuple[tuple[float, float, float], int] | None:
    """Média RGB da pele sobre uma lista de regiões arbitrárias."""
    altura, largura = quadro.shape[:2]
    acumulado = []
    for regiao in regioes:
        recorte = regiao.limitar(largura, altura).recortar(quadro)
        if recorte.size == 0:
            continue
        pixels = extrator._selecionar_pixels(recorte)
        if pixels.shape[0] > 0:
            acumulado.append(pixels)
    if not acumulado:
        return None
    juntos = np.vstack(acumulado)
    if juntos.shape[0] < 50:
        return None
    azul, verde, vermelho = juntos.mean(axis=0)
    return (float(vermelho), float(verde), float(azul)), int(juntos.shape[0])


@dataclass
class Resultado:
    """Desempenho de uma configuração sobre a captura real."""

    variante: str
    algoritmo: str
    com_fundo: bool
    bpm_mediano: float
    dispersao: float
    snr_mediano: float
    janelas: int

    @property
    def rotulo(self) -> str:
        fundo = "com fundo" if self.com_fundo else "sem fundo"
        return f"{self.variante} / {self.algoritmo} / {fundo}"


def avaliar_captura(
    captura: Captura,
    janela_s: float = 15.0,
    passo_s: float = 1.0,
    banda: BandaCardiaca | None = None,
) -> list[Resultado]:
    """Roda todas as combinações sobre exatamente os mesmos quadros."""
    banda = banda or BandaCardiaca(0.75, 3.3)
    fps = captura.fps
    if captura.total < 64 or fps <= 0:
        return []

    tem_fundo = all(f is not None for f in captura.fundo) and len(captura.fundo) == captura.total
    matriz_fundo = (
        np.asarray(captura.fundo, dtype=float).T if tem_fundo else None
    )
    instantes = np.asarray(captura.instantes, dtype=float)
    por_janela = max(64, int(round(janela_s * fps)))
    passo = max(1, int(round(passo_s * fps)))

    resultados: list[Resultado] = []
    for variante, amostras in captura.por_variante.items():
        matriz = np.asarray(amostras, dtype=float).T
        for algoritmo in ("pos", "chrom", "verde"):
            for com_fundo in (True, False):
                if com_fundo and matriz_fundo is None:
                    continue
                bpms: list[float] = []
                snrs: list[float] = []
                for inicio in range(0, matriz.shape[1] - por_janela + 1, passo):
                    fim = inicio + por_janela
                    serie = SerieRGB(
                        matriz[0, inicio:fim],
                        matriz[1, inicio:fim],
                        matriz[2, inicio:fim],
                        fps,
                        instantes[inicio:fim],
                        matriz_fundo[:, inicio:fim] if com_fundo else None,
                    )
                    config = ConfiguracaoAnalise(
                        janela_s=janela_s,
                        banda=banda,
                        algoritmo=algoritmo,
                        usar_fundo=com_fundo,
                    )
                    analise = estimar_de_serie(serie, config, criar_algoritmo(algoritmo))
                    if analise.ok:
                        completa = analise.desempacotar()
                        bpms.append(completa.estimativa.bpm)
                        snrs.append(completa.estimativa.snr_db)

                if not bpms:
                    continue
                resultados.append(
                    Resultado(
                        variante=variante,
                        algoritmo=algoritmo,
                        com_fundo=com_fundo,
                        bpm_mediano=float(np.median(bpms)),
                        dispersao=float(np.std(bpms)),
                        snr_mediano=float(np.median(snrs)),
                        janelas=len(bpms),
                    )
                )

    # Ordena pelo que mais importa numa medição real: consistência entre
    # janelas. Uma configuração que devolve sempre o mesmo número é mais
    # confiável que uma com relação sinal-ruído alta e resultado instável.
    resultados.sort(key=lambda r: (r.dispersao, -r.snr_mediano))
    return resultados


def gravar_csv(captura: Captura, caminho: str) -> None:
    """Grava as séries em CSV. Somente números, nenhuma imagem."""
    colunas = ["instante"]
    for nome in VARIANTES_ROI:
        colunas += [f"{nome}_r", f"{nome}_g", f"{nome}_b", f"{nome}_px"]
    colunas += ["fundo_r", "fundo_g", "fundo_b", "caixa_x", "caixa_y", "caixa_l", "caixa_a"]

    linhas = [";".join(colunas)]
    for i in range(captura.total):
        valores = [f"{captura.instantes[i]:.5f}"]
        for nome in VARIANTES_ROI:
            r, g, b = captura.por_variante[nome][i]
            valores += [f"{r:.4f}", f"{g:.4f}", f"{b:.4f}", str(captura.pixels_por_variante[nome][i])]
        fundo = captura.fundo[i]
        valores += (
            [f"{fundo[0]:.4f}", f"{fundo[1]:.4f}", f"{fundo[2]:.4f}"] if fundo else ["", "", ""]
        )
        valores += [str(v) for v in captura.caixas[i]]
        linhas.append(";".join(valores))

    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")


def formatar_relatorio(captura: Captura, resultados: list[Resultado]) -> str:
    """Relatório legível, com o que foi capturado e o que funcionou melhor."""
    tremor_posicao, tremor_tamanho = captura.tremor_da_caixa()
    aproveitados = captura.total
    perdidos = captura.quadros_sem_rosto

    linhas = [
        "CAPTURA",
        f"  Quadros aproveitados: {aproveitados}",
        f"  Quadros descartados:  {perdidos}",
        f"  Taxa efetiva:         {captura.fps:.1f} quadros por segundo",
        f"  Duração:              {captura.instantes[-1] - captura.instantes[0]:.1f} s"
        if aproveitados > 1
        else "  Duração:              0 s",
        f"  Tremor da caixa:      {tremor_posicao:.1f} px de posição, "
        f"{tremor_tamanho:.1f} px de tamanho",
    ]

    if aproveitados:
        for nome in VARIANTES_ROI:
            pixels = captura.pixels_por_variante[nome]
            linhas.append(
                f"  Pixels em {nome:18s} {int(np.median(pixels)):6d} "
                f"(variação {float(np.std(pixels)) / max(1.0, float(np.mean(pixels))) * 100:.1f}%)"
            )

    if not resultados:
        linhas += [
            "",
            "Não houve dados suficientes para comparar configurações.",
            "Verifique se o rosto ficou enquadrado durante toda a captura.",
        ]
        return "\n".join(linhas)

    linhas += [
        "",
        "CONFIGURAÇÕES, DA MAIS ESTÁVEL PARA A MENOS",
        "",
        f"  {'configuração':46s} {'bpm':>7} {'dispersão':>10} {'SNR':>8} {'janelas':>8}",
        f"  {'-' * 46} {'-' * 7} {'-' * 10} {'-' * 8} {'-' * 8}",
    ]
    for r in resultados[:14]:
        linhas.append(
            f"  {r.rotulo:46s} {r.bpm_mediano:7.1f} {r.dispersao:10.2f} "
            f"{r.snr_mediano:8.1f} {r.janelas:8d}"
        )

    melhor = resultados[0]
    linhas += [
        "",
        "LEITURA DO RESULTADO",
        f"  Configuração mais estável: {melhor.rotulo}",
        f"  Valor: {melhor.bpm_mediano:.0f} bpm, variando {melhor.dispersao:.1f} bpm entre janelas.",
    ]

    if melhor.dispersao > 6:
        linhas.append(
            "  Dispersão alta. O sinal não está sustentando uma frequência estável;\n"
            "  trate o número como não confiável."
        )
    elif melhor.dispersao > 2.5:
        linhas.append("  Dispersão moderada. O valor é indicativo.")
    else:
        linhas.append("  Dispersão baixa. O valor é consistente entre janelas.")

    if tremor_posicao > 3.0:
        linhas.append(
            f"  O tremor de {tremor_posicao:.1f} px na caixa do rosto é alto e provavelmente\n"
            "  está contaminando a medição. Apoie a cabeça em algo firme."
        )

    return "\n".join(linhas)
