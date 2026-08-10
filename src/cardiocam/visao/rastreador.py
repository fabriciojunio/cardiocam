"""Estabilização da caixa do rosto ao longo do tempo.

Este módulo existe por causa de um detalhe que decide se o sistema funciona ou
não com gente de verdade: a cascata de Haar redetecta o rosto do zero a cada
quadro, e a caixa resultante oscila alguns pixels mesmo com a pessoa imóvel.
Como medimos a média de cor dentro dessa caixa, o tremor faz a região incluir
ora mais pele, ora mais cabelo ou fundo. Isso injeta no sinal uma variação de
amplitude muito maior que a do pulso, e na banda errada.

A correção tem duas partes: suavizar a caixa com média exponencial e ignorar
detecções que saltam demais em relação à anterior.
"""

from __future__ import annotations

import numpy as np

from cardiocam.dominio.erros import RostoNaoEncontrado
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.visao.detector_face import DetectorFace
from cardiocam.visao.geometria import Retangulo


class RastreadorRosto:
    """Envolve um detector e entrega uma caixa estável quadro a quadro."""

    def __init__(
        self,
        detector: DetectorFace,
        suavizacao: float = 0.25,
        tolerancia_quadros: int = 15,
        salto_maximo: float = 0.35,
        intervalo_deteccao: int = 1,
    ) -> None:
        """
        `suavizacao` é o peso da detecção nova na média exponencial: 1,0 desliga
        a suavização e 0,1 deixa a caixa bem lenta.

        `tolerancia_quadros` é por quantos quadros seguidos mantemos a última
        caixa conhecida quando o detector falha. Piscar, virar o rosto de leve ou
        uma sombra passageira não deveriam zerar a medição.

        `salto_maximo` rejeita detecções cujo centro pula mais que essa fração do
        tamanho do rosto, tratando-as como falso positivo.

        `intervalo_deteccao` roda o detector a cada N quadros; nos demais, a
        última caixa é reaproveitada. Serve para aliviar a CPU em máquinas
        modestas.
        """
        if not 0.0 < suavizacao <= 1.0:
            raise ValueError("A suavização precisa estar entre 0 (exclusivo) e 1.")
        if intervalo_deteccao < 1:
            raise ValueError("O intervalo de detecção precisa ser pelo menos 1.")

        self.detector = detector
        self.suavizacao = suavizacao
        self.tolerancia_quadros = tolerancia_quadros
        self.salto_maximo = salto_maximo
        self.intervalo_deteccao = intervalo_deteccao

        self._caixa: Retangulo | None = None
        self._quadros_sem_rosto = 0
        self._contador = 0
        self._deteccoes_rejeitadas = 0

    @property
    def caixa_atual(self) -> Retangulo | None:
        return self._caixa

    @property
    def quadros_sem_rosto(self) -> int:
        return self._quadros_sem_rosto

    @property
    def deteccoes_rejeitadas(self) -> int:
        return self._deteccoes_rejeitadas

    @property
    def perdeu_o_rosto(self) -> bool:
        """Verdadeiro quando a ausência já passou da tolerância.

        O pipeline usa isso para decidir que o sinal acumulado ficou inválido.
        """
        return self._quadros_sem_rosto > self.tolerancia_quadros

    def reiniciar(self) -> None:
        self._caixa = None
        self._quadros_sem_rosto = 0
        self._contador = 0

    def _e_salto_absurdo(self, nova: Retangulo) -> bool:
        if self._caixa is None:
            return False
        cx_antigo, cy_antigo = self._caixa.centro
        cx_novo, cy_novo = nova.centro
        distancia = float(np.hypot(cx_novo - cx_antigo, cy_novo - cy_antigo))
        referencia = max(1.0, float(self._caixa.largura))
        if distancia > self.salto_maximo * referencia:
            return True
        # Mudança brusca de escala também costuma ser detecção errada.
        razao = nova.largura / max(1.0, float(self._caixa.largura))
        return razao > 1.6 or razao < 0.625

    def atualizar(self, quadro: np.ndarray) -> Resultado[Retangulo]:
        """Processa mais um quadro e devolve a caixa estabilizada."""
        rodar_detector = (self._contador % self.intervalo_deteccao == 0) or self._caixa is None
        self._contador += 1

        if not rodar_detector and self._caixa is not None:
            return Ok(self._caixa)

        deteccao = self.detector.detectar(quadro)

        if deteccao.falhou:
            self._quadros_sem_rosto += 1
            if self._caixa is not None and not self.perdeu_o_rosto:
                return Ok(self._caixa)
            self._caixa = None
            return Falha(RostoNaoEncontrado())

        nova = deteccao.desempacotar()

        if self._e_salto_absurdo(nova):
            self._deteccoes_rejeitadas += 1
            self._quadros_sem_rosto += 1
            if self._caixa is not None and not self.perdeu_o_rosto:
                return Ok(self._caixa)

        self._quadros_sem_rosto = 0
        if self._caixa is None:
            self._caixa = nova
        else:
            self._caixa = self._caixa.interpolar(nova, self.suavizacao)
        return Ok(self._caixa)
