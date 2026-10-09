"""A exportação preserva tempo, recusas e mensagens com acentuação."""

import csv

from cardiocam.pipeline.analisador import EstadoQuadro, RelatorioSessao
from cardiocam.pipeline.registros import RegistroMedicao
from cardiocam.ui.app import salvar_serie
from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade, aplicar_veredito
from cardiocam.pipeline.analisador import estimar_de_serie
from tests.conftest import serie_de
from dataclasses import replace


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
