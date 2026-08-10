"""GREEN: usar só o canal verde.

Verkruysse, Svaasand e Nelson mostraram em 2008 que dá para ver o pulso num
vídeo comum, e que o canal verde é o melhor dos três. A razão é óptica: a
hemoglobina absorve fortemente em torno de 540 nm, bem no meio da resposta do
filtro verde do sensor, enquanto o vermelho penetra fundo demais na pele e
carrega pouco contraste pulsátil, e o azul é dominado por ruído e por reflexão
na superfície.

É a linha de base contra a qual os outros métodos se justificam. Funciona bem
com a pessoa parada e iluminação estável, e desmonta com movimento, porque
qualquer mudança de iluminação entra inteira no sinal.
"""

from __future__ import annotations

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.resultado import Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.rppg.base import finalizar


class Verde:
    """Extrai o pulso a partir do canal verde."""

    nome = "verde"

    def extrair(
        self, serie: SerieRGB, config: ConfiguracaoAnalise
    ) -> Resultado[SinalPulso]:
        # O sinal é invertido porque mais sangue significa mais absorção e,
        # portanto, menos luz verde refletida. Invertendo, os picos do sinal
        # passam a coincidir com a sístole, o que deixa a forma de onda
        # exibida coerente com o que se espera de um pletismograma.
        return finalizar(-serie.verde, serie, config, self.nome)
