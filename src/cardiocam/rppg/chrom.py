"""CHROM: combinação cromática robusta a movimento.

De Haan e Jeanne (2013) partem de um modelo físico da reflexão da pele. A luz
que volta ao sensor tem duas parcelas: a reflexão especular, que é a cor da
fonte de luz e não carrega informação de sangue, e a reflexão difusa, que
atravessa o tecido e traz a modulação do volume sanguíneo.

O movimento e a variação de iluminação afetam principalmente a componente
especular, e o fazem de forma proporcional em todos os canais. A ideia do CHROM
é montar duas projeções cromáticas X e Y nas quais essa distorção comum aparece
de forma conhecida, e então combinar X e Y com um peso que a cancela.

Os coeficientes 3R-2G e 1,5R+G-1,5B saem da suposição de um tom de pele padrão
sob iluminação branca. É por isso que o método é sensível a luz muito colorida,
limitação que o POS resolve.
"""

from __future__ import annotations

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.rppg.base import finalizar
from cardiocam.sinais.filtros import aplicar_passa_faixa
from cardiocam.sinais.preprocessamento import normalizar_pela_media


class Chrom:
    """Extração de pulso pelo método da crominância."""

    nome = "chrom"

    def extrair(
        self, serie: SerieRGB, config: ConfiguracaoAnalise
    ) -> Resultado[SinalPulso]:
        matriz = normalizar_pela_media(serie.como_matriz())
        vermelho, verde, azul = matriz[0], matriz[1], matriz[2]

        x_bruto = 3.0 * vermelho - 2.0 * verde
        y_bruto = 1.5 * vermelho + verde - 1.5 * azul

        # As duas projeções precisam ser filtradas antes de calcular alfa: o
        # peso tem que refletir a energia dentro da banda cardíaca, não a
        # energia total, que seria dominada pela tendência de iluminação.
        filtrado = aplicar_passa_faixa(
            np.vstack([x_bruto, y_bruto]),
            serie.fps,
            config.banda,
            config.ordem_filtro,
        )
        if filtrado.falhou:
            return Falha(filtrado.erro)

        x_filtrado, y_filtrado = filtrado.desempacotar()
        desvio_y = float(np.std(y_filtrado))
        alfa = float(np.std(x_filtrado)) / desvio_y if desvio_y > 1e-12 else 0.0

        pulso = x_filtrado - alfa * y_filtrado
        return finalizar(pulso, serie, config, self.nome)
