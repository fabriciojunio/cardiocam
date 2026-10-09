"""A exportação preserva tempo, recusas e mensagens com acentuação."""

import csv

from cardiocam.pipeline.analisador import EstadoQuadro, RelatorioSessao
from cardiocam.pipeline.registros import RegistroMedicao
from cardiocam.ui.app import salvar_serie
from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade, aplicar_veredito
from cardiocam.pipeline.analisador import estimar_de_serie
from tests.conftest import serie_de
from dataclasses import replace
import pytest
from cardiocam.cli import _resumir, construir_analisador, main
from cardiocam.dominio.estimativa import EstimativaBPM


def test_csv_inclui_recusa_e_tempo_sem_inventar_bpm(tmp_path):
    estado = EstadoQuadro(instante=10.5, codigo_falha="video_congelado",
                         mensagem='Vídeo congelado, "aguarde".')
    relatorio = RelatorioSessao(registros=[RegistroMedicao.do_estado(estado)])
    destino = tmp_path / "medições.csv"
    salvar_serie(str(destino), relatorio)
    with destino.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 1
    assert linhas[0]["instante_s"] == "10.5"
    assert linhas[0]["bpm"] == ""
    assert linhas[0]["aceita"] == "False"
    assert linhas[0]["codigo_falha"] == "video_congelado"
    assert linhas[0]["mensagem"] == estado.mensagem


def test_recusa_tem_mesma_politica_nas_interfaces():
    analise = estimar_de_serie(serie_de(72)).desempacotar()
    juiz = JuizDeQualidade(100)
    juiz.modelo = replace(juiz.modelo, calibracao_viavel=False)
    estado = EstadoQuadro(analise=analise, bpm_exibido=72, instante=10, instante_analise=10)
    aplicar_veredito(juiz, estado)
    registro = RegistroMedicao.do_estado(estado)
    assert not registro.aceita
    assert registro.estimativa.bpm == analise.estimativa.bpm
    assert estado.bpm_exibido is None
    assert registro.codigo_falha == "qualidade_recusada"
    assert "calibração viável" in registro.mensagem


def test_resumo_nao_publica_bpm_de_janelas_recusadas():
    estimativa = EstimativaBPM.criar(1.2, 20, "pos", 10)
    registro = RegistroMedicao(10, estimativa, False, .01, "qualidade_recusada", "Qualidade insuficiente.", 0)
    resumo = _resumir(RelatorioSessao(estimativas=[estimativa], registros=[registro]))
    assert "Nenhuma leitura foi aceita" in resumo
    assert "Qualidade insuficiente" in resumo
    assert "Frequência cardíaca:" not in resumo


def test_resumo_exclui_estimativas_brutas_recusadas():
    boa = EstimativaBPM.criar(1.2, 20, "pos", 10)
    ruim = EstimativaBPM.criar(2, 20, "pos", 10)
    registros = [RegistroMedicao(10, boa, True, .95, None, "", 0),
                 RegistroMedicao(11, ruim, False, .01, "qualidade_recusada", "", 0)]
    resumo = _resumir(RelatorioSessao(estimativas=[boa, ruim], registros=registros))
    assert "Frequência cardíaca: 72.0 bpm" in resumo
    assert "Leituras aceitas: 1" in resumo


def test_limite_de_erro_falha_sem_janela(capsys):
    assert main(["simular", "--duracao", "1", "--janela", "10", "--erro-maximo", "3"]) == 1
    assert "limite de erro" in capsys.readouterr().err


@pytest.mark.parametrize("limite", ["nan", "inf", "-1"])
def test_limite_de_erro_invalido(limite):
    with pytest.raises(SystemExit):
        construir_analisador().parse_args(["simular", "--erro-maximo", limite])


@pytest.mark.parametrize("probabilidade", [float("nan"), float("inf"), -0.1, 1.1])
def test_probabilidade_invalida_nao_publica_leitura(probabilidade, monkeypatch):
    analise = estimar_de_serie(serie_de(72)).desempacotar()
    juiz = JuizDeQualidade(100)
    monkeypatch.setattr(type(juiz.modelo), "probabilidade", lambda *a: probabilidade)
    estado = EstadoQuadro(analise=analise, bpm_exibido=72)
    aplicar_veredito(juiz, estado)
    assert estado.bpm_exibido is None
    assert estado.recusada
    assert estado.qualidade is None
    assert estado.codigo_falha == "qualidade_indisponivel"


def test_falha_de_extracao_de_qualidade_nao_publica_leitura(monkeypatch):
    analise = estimar_de_serie(serie_de(72)).desempacotar()
    juiz = JuizDeQualidade(100)

    def falhar(*args):
        raise ValueError("característica inválida")

    monkeypatch.setattr(juiz, "caracteristicas", falhar)
    estado = EstadoQuadro(analise=analise, bpm_exibido=72)
    aplicar_veredito(juiz, estado)
    assert estado.bpm_exibido is None
    assert estado.codigo_falha == "qualidade_indisponivel"


def test_registro_preserva_taxa_temporal_e_diagnostico_da_pele(tmp_path):
    from types import SimpleNamespace
    import numpy as np

    analise = estimar_de_serie(serie_de(72)).desempacotar()
    analise = replace(analise, instantes_originais=np.array([0.0, .05, .15]))
    amostra = SimpleNamespace(luminancia_p05=11, luminancia_mediana=45, luminancia_p95=150,
                             proporcao_pele=.7, fracao_saturada=.1)
    estado = EstadoQuadro(analise=analise, amostra=amostra, bpm_exibido=72, instante=10)
    registro = RegistroMedicao.do_estado(estado)
    destino = tmp_path / "diagnóstico.csv"
    salvar_serie(str(destino), RelatorioSessao(registros=[registro]))
    with destino.open(encoding="utf-8", newline="") as arquivo:
        linha = next(csv.DictReader(arquivo))
    assert float(linha["fps_janela"]) == pytest.approx(2 / .15)
    assert float(linha["jitter_intervalos_s"]) == pytest.approx(.025)
    assert float(linha["luminancia_pele_mediana_quadro"]) == 45
    assert float(linha["fracao_pele_quadro"]) == .7


def test_arquivo_e_fechado_quando_a_analise_falha(monkeypatch):
    from types import SimpleNamespace
    from cardiocam.dominio.resultado import Ok

    fechamentos = []
    fonte = SimpleNamespace(fps=30, fechar=lambda: fechamentos.append(True))
    monkeypatch.setattr("cardiocam.cli.abrir_arquivo", lambda *a: Ok(fonte))

    def falhar(*args):
        raise ValueError("falha controlada")

    monkeypatch.setattr("cardiocam.cli.analisar_fonte", falhar)
    with pytest.raises(ValueError, match="falha controlada"):
        main(["arquivo", "sessão.mp4"])
    assert fechamentos == [True]
