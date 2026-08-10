"""Testes dos algoritmos rPPG sobre séries RGB fisicamente modeladas.

Aqui a entrada não é uma senoide abstrata: é a média de cor que sairia de uma
pele iluminada, com o pulso modulando cada canal com o peso que a hemoglobina
impõe. É o teste que verifica o mérito de cada algoritmo, isolado da parte de
imagem.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.erros import SinalSemQualidade
from cardiocam.dominio.sinal import SerieRGB
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo
from tests.conftest import serie_de

BPMS = (45.0, 52.0, 60.0, 68.0, 75.0, 84.0, 92.0, 105.0, 120.0, 140.0, 165.0, 190.0)
CROMATICOS = ("chrom", "pos")
TOLERANCIA = 2.5


def estimar(serie: SerieRGB, algoritmo: str) -> float:
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    resultado = estimar_de_serie(serie, config, criar_algoritmo(algoritmo))
    assert resultado.ok, f"{algoritmo} falhou: {getattr(resultado, 'erro', None)}"
    return resultado.desempacotar().estimativa.bpm


# --------------------------------------------------------------------------
# Condições em que todos os métodos devem funcionar
# --------------------------------------------------------------------------
@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", BPMS)
def test_condicao_ideal(algoritmo: str, bpm: float) -> None:
    estimado = estimar(serie_de(bpm, amplitude_pulso=0.02, ruido_sensor=1.0), algoritmo)
    assert abs(estimado - bpm) < TOLERANCIA


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", BPMS)
def test_com_ruido_de_sensor(algoritmo: str, bpm: float) -> None:
    serie = serie_de(bpm, amplitude_pulso=0.015, ruido_sensor=8.0, duracao_s=18.0)
    assert abs(estimar(serie, algoritmo) - bpm) < TOLERANCIA


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", BPMS)
def test_com_deriva_lenta_de_iluminacao(algoritmo: str, bpm: float) -> None:
    """Rampa de iluminação: o detrend e o passa-faixa resolvem para todos."""
    serie = serie_de(bpm, amplitude_pulso=0.015, deriva_iluminacao=0.3)
    assert abs(estimar(serie, algoritmo) - bpm) < TOLERANCIA


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", BPMS)
def test_com_captura_irregular(algoritmo: str, bpm: float) -> None:
    serie = serie_de(bpm, amplitude_pulso=0.015, jitter_fps=0.012, duracao_s=18.0)
    assert abs(estimar(serie, algoritmo) - bpm) < 3.5


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("tom", ((170, 195, 225), (130, 155, 185), (85, 105, 135), (48, 65, 88)))
def test_independe_do_tom_de_pele(algoritmo: str, tom: tuple) -> None:
    """A normalização pela média temporal remove o nível de cor da pele.

    O sistema precisa medir igualmente bem qualquer pessoa.
    """
    serie = serie_de(78.0, tom_pele=tom, amplitude_pulso=0.02)
    assert abs(estimar(serie, algoritmo) - 78.0) < TOLERANCIA


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("fps", (15.0, 20.0, 25.0, 30.0, 50.0, 60.0))
def test_diferentes_taxas_de_quadros(algoritmo: str, fps: float) -> None:
    serie = serie_de(90.0, fps=fps, duracao_s=16.0, amplitude_pulso=0.02)
    assert abs(estimar(serie, algoritmo) - 90.0) < TOLERANCIA


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("amplitude", (0.004, 0.006, 0.01, 0.02, 0.04))
def test_diferentes_amplitudes_de_pulso(algoritmo: str, amplitude: float) -> None:
    serie = serie_de(72.0, amplitude_pulso=amplitude, ruido_sensor=2.0, duracao_s=18.0)
    assert abs(estimar(serie, algoritmo) - 72.0) < TOLERANCIA


# --------------------------------------------------------------------------
# Interferência dentro da banda: aqui os métodos se separam
# --------------------------------------------------------------------------
@pytest.mark.parametrize("algoritmo", CROMATICOS)
@pytest.mark.parametrize("bpm", BPMS)
def test_metodos_cromaticos_rejeitam_interferencia_na_banda(
    algoritmo: str, bpm: float
) -> None:
    """CHROM e POS separam pulso de iluminação porque o pulso muda a cor e a
    iluminação muda só o brilho."""
    interferencia = bpm / 60.0 + 0.7
    if interferencia > 3.8:
        interferencia = bpm / 60.0 - 0.7
    serie = serie_de(
        bpm,
        amplitude_pulso=0.015,
        amplitude_tremor=0.05,
        tremor_iluminacao_hz=interferencia,
        duracao_s=18.0,
    )
    assert abs(estimar(serie, algoritmo) - bpm) < TOLERANCIA


@pytest.mark.parametrize("bpm", BPMS)
def test_canal_verde_se_perde_com_interferencia_na_banda(bpm: float) -> None:
    """Documenta a limitação do método mais simples.

    O canal verde sozinho não distingue uma variação de brilho de uma variação
    de volume sanguíneo. Quando a interferência cai dentro da banda cardíaca, a
    filtragem não ajuda e o método trava na frequência errada. É exatamente esse
    o problema que CHROM e POS foram criados para resolver, e é a justificativa
    de existirem no projeto.
    """
    interferencia_hz = bpm / 60.0 + 0.7
    if interferencia_hz > 3.8:
        interferencia_hz = bpm / 60.0 - 0.7
    serie = serie_de(
        bpm,
        amplitude_pulso=0.012,
        amplitude_tremor=0.06,
        tremor_iluminacao_hz=interferencia_hz,
        duracao_s=18.0,
    )
    estimado = estimar(serie, "verde")
    esperado_errado = interferencia_hz * 60.0
    assert abs(estimado - esperado_errado) < abs(estimado - bpm), (
        "o canal verde deveria travar na interferência, e não no pulso"
    )


@pytest.mark.parametrize("algoritmo", CROMATICOS)
@pytest.mark.parametrize("intensidade", (0.02, 0.04, 0.06, 0.08, 0.12))
def test_robustez_cresce_com_a_intensidade_da_interferencia(
    algoritmo: str, intensidade: float
) -> None:
    serie = serie_de(
        84.0,
        amplitude_pulso=0.015,
        amplitude_tremor=intensidade,
        tremor_iluminacao_hz=2.1,
        duracao_s=18.0,
    )
    assert abs(estimar(serie, algoritmo) - 84.0) < TOLERANCIA


# --------------------------------------------------------------------------
# Propriedades estruturais da saída
# --------------------------------------------------------------------------
@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("duracao", (8.0, 12.0, 16.0, 20.0))
def test_saida_tem_o_comprimento_da_entrada(algoritmo: str, duracao: float) -> None:
    serie = serie_de(72.0, duracao_s=duracao)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    resultado = criar_algoritmo(algoritmo).extrair(serie, config)
    assert resultado.ok
    assert len(resultado.desempacotar()) == len(serie)


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_saida_registra_o_nome_do_algoritmo(algoritmo: str) -> None:
    serie = serie_de(72.0)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    pulso = criar_algoritmo(algoritmo).extrair(serie, config).desempacotar()
    assert pulso.origem == algoritmo


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_saida_e_finita(algoritmo: str) -> None:
    serie = serie_de(72.0, ruido_sensor=15.0)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    pulso = criar_algoritmo(algoritmo).extrair(serie, config).desempacotar()
    assert np.all(np.isfinite(pulso.amostras))


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_janela_curta_demais_devolve_falha(algoritmo: str) -> None:
    serie = serie_de(72.0, duracao_s=0.5)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    assert criar_algoritmo(algoritmo).extrair(serie, config).falhou


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_sinal_constante_e_recusado(algoritmo: str) -> None:
    """Uma parede lisa no lugar de um rosto não pode virar batimento.

    Sem a guarda de sinal degenerado, o resíduo numérico da filtragem produz um
    espectro com pico bem definido e o sistema reportaria um valor com confiança
    máxima. Recusar é a resposta certa.
    """
    constante = np.full(400, 150.0)
    serie = SerieRGB(constante, constante * 1.1, constante * 0.9, 30.0)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    resultado = estimar_de_serie(serie, config, criar_algoritmo(algoritmo))
    assert resultado.falhou
    assert isinstance(resultado.erro, SinalSemQualidade)


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("nivel", (0.0, 255.0))
def test_imagem_saturada_ou_apagada_e_recusada(algoritmo: str, nivel: float) -> None:
    """Câmera estourada ou totalmente escura: sem variação, sem medida."""
    plano = np.full(400, nivel)
    serie = SerieRGB(plano, plano, plano, 30.0)
    config = ConfiguracaoAnalise(algoritmo=algoritmo)
    assert estimar_de_serie(serie, config, criar_algoritmo(algoritmo)).falhou


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_relacao_sinal_ruido_nunca_e_infinita(algoritmo: str) -> None:
    """Valor infinito contaminaria as médias e prometeria certeza absoluta."""
    serie = serie_de(72.0, amplitude_pulso=0.05, ruido_sensor=0.0)
    resultado = estimar_de_serie(
        serie, ConfiguracaoAnalise(algoritmo=algoritmo), criar_algoritmo(algoritmo)
    )
    assert resultado.ok
    assert np.isfinite(resultado.desempacotar().estimativa.snr_db)


# --------------------------------------------------------------------------
# Registro de algoritmos
# --------------------------------------------------------------------------
@pytest.mark.parametrize("nome", ALGORITMOS_DISPONIVEIS)
def test_criacao_pelo_nome(nome: str) -> None:
    assert criar_algoritmo(nome).nome == nome


@pytest.mark.parametrize("nome", ("VERDE", "Chrom", "  pos  ", "ICA"))
def test_nome_e_normalizado(nome: str) -> None:
    assert criar_algoritmo(nome).nome == nome.strip().lower()


@pytest.mark.parametrize("nome", ("inexistente", "", "fft", "deep"))
def test_nome_desconhecido_e_rejeitado_com_dica(nome: str) -> None:
    with pytest.raises(ValueError, match="Disponíveis"):
        criar_algoritmo(nome)
