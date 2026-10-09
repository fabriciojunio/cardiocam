"""Compara métodos experimentais sem mudar o algoritmo do aplicativo."""

from cardiocam.avaliacao.benchmark import ResultadoAlgoritmo, cenarios_padrao, formatar_tabela
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import gerar_serie_rgb
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.rppg.experimentais import ALGORITMOS_EXPERIMENTAIS


def avaliar_experimentais(cenarios=None):
    cenarios = cenarios_padrao() if cenarios is None else cenarios
    resultados = {}
    for classe in ALGORITMOS_EXPERIMENTAIS:
        algoritmo = classe()
        relatorio = ResultadoAlgoritmo(algoritmo.nome)
        for cenario in cenarios:
            resultado = estimar_de_serie(gerar_serie_rgb(cenario.parametros),
                                        ConfiguracaoAnalise(), algoritmo)
            if resultado.falhou:
                relatorio.falhas += 1
            else:
                estimativa = resultado.desempacotar().estimativa
                relatorio.erros.append(abs(estimativa.bpm - cenario.bpm_verdadeiro))
                relatorio.snrs.append(estimativa.snr_db)
        resultados[algoritmo.nome] = relatorio
    return resultados


def principal(cenarios=None):
    print("Avaliação experimental em dados sintéticos; sem validação em pessoas reais.")
    print(formatar_tabela(avaliar_experimentais(cenarios)))


if __name__ == "__main__":
    principal()
