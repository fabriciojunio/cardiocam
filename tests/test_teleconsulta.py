"""Transmissão HTTP real em loopback e rejeição de sessões inválidas."""

from urllib.error import HTTPError
import json
from urllib.request import Request, urlopen

import pytest

from cardiocam.teleconsulta.transporte import SessaoTelemetria, enviar, receptor_local, validar_leitura

TOKEN = "token-de-teste-publico-sem-valor-real-123456"


def leitura(**alteracoes):
    return {"sessao": "participante-01", "sequencia": 0, "instante_s": 1,
            "bpm": 72, "qualidade": .9, "aceita": True, **alteracoes}


def test_transmissao_real_e_revogacao():
    sessao = SessaoTelemetria("participante-01", TOKEN, True)
    with receptor_local(sessao) as url:
        enviar(url, TOKEN, leitura(), True)
        enviar(url, TOKEN, leitura(sequencia=1, instante_s=2, bpm=None, aceita=False), True)
        assert len(sessao.leituras()) == 2 and sessao.leituras()[-1]["bpm"] is None
        with pytest.raises(HTTPError) as erro:
            enviar(url, TOKEN, leitura(), True)
        assert erro.value.code == 400
        with pytest.raises(HTTPError) as erro:
            enviar(url, TOKEN+"x", leitura(sequencia=3, instante_s=3), True)
        assert erro.value.code == 401
    assert sessao.leituras() == []


@pytest.mark.parametrize("alteracoes", [{"bpm": float("nan")}, {"aceita": "true"}, {"qualidade": 2},
                                       {"instante_s": -1}, {"sequencia": True}, {"aceita": False},
                                       {"bpm": None}, {"imagem": "conteudo"}])
def test_telemetria_invalida_nao_sai_da_maquina(alteracoes):
    with pytest.raises(ValueError): validar_leitura(leitura(**alteracoes))


@pytest.mark.parametrize("url", ["http://example.com/leituras", "http://localhost.evil/leituras",
                                "https://user:pass@example.com/leituras", "https://example.com/outro",
                                "https://example.com/leituras?token=abc"])
def test_destinos_inseguros_ou_sem_consentimento_recusados(url):
    with pytest.raises(ValueError): enviar(url, TOKEN, leitura(), True)
    with pytest.raises(ValueError): enviar("http://127.0.0.1/leituras", TOKEN, leitura(), False)


def test_sessao_expira_e_apaga_dados():
    tempo = [0.]
    s = SessaoTelemetria("participante-01", TOKEN, True, 10, lambda: tempo[0])
    s.receber(TOKEN, leitura())
    tempo[0] = 11
    assert s.leituras() == []
    with pytest.raises(PermissionError): s.receber(TOKEN, leitura(sequencia=1, instante_s=2))
    with pytest.raises(ValueError): SessaoTelemetria("p", TOKEN, False)


def test_http_rejeita_corpo_grande_tipo_errado_e_rota():
    s = SessaoTelemetria("participante-01", TOKEN, True)
    with receptor_local(s) as url:
        for corpo, tipo, destino, status in ((b"x"*3000, "application/json", url, 400),
                                             (b"{}", "text/plain", url, 400),
                                             (b"{}", "application/json", url+"/outro", 404)):
            req = Request(destino, data=corpo, headers={"Content-Type": tipo, "Authorization": "Bearer "+TOKEN})
            with pytest.raises(HTTPError) as erro: urlopen(req, timeout=3)
            assert erro.value.code == status


def test_transmissor_assincrono_nao_acumula_leituras_antigas():
    import threading
    from cardiocam.teleconsulta.medicao_local import Transmissor
    entrou, liberar = threading.Event(), threading.Event()
    recebidas = []
    def rede_lenta(url, token, dados, consentimento):
        entrou.set()
        assert liberar.wait(3)
        recebidas.append(dados["sequencia"])
    t = Transmissor("http://127.0.0.1/leituras", TOKEN, True, rede_lenta)
    try:
        t.publicar(leitura())
        assert entrou.wait(3)
        for i in range(1, 10): t.publicar(leitura(sequencia=i, instante_s=i+1))
    finally:
        liberar.set()
        t.fechar()
    assert recebidas == [0, 9] and t.descartadas == 8
    with pytest.raises(RuntimeError): t.publicar(leitura())


def test_camera_local_publica_recusas_sem_imagens():
    from cardiocam.teleconsulta.medicao_local import medir_e_transmitir
    from cardiocam.dominio.config import ConfiguracaoAnalise
    from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao
    class Coletor:
        def __init__(self): self.leituras = []
        def publicar(self, leitura): self.leituras.append(leitura)
    coletor = Coletor()
    fonte = FonteSintetica(ParametrosSimulacao(bpm=84, duracao_s=12, fps=20))
    r = medir_e_transmitir(fonte, coletor, "participante-01", 12, ConfiguracaoAnalise(janela_s=8))
    assert r["publicadas"] >= 10 and coletor.leituras
    assert any(not l["aceita"] and l["bpm"] is None for l in coletor.leituras)
    for l in coletor.leituras: validar_leitura(l)


def test_cli_transmite_csv_a_receptor_real(tmp_path, monkeypatch):
    from cardiocam.cli import main
    arquivo = tmp_path / "leituras.csv"
    arquivo.write_text("instante_s,bpm,qualidade,aceita\n1,72,0.9,True\n2,,,False\n", encoding="utf-8")
    monkeypatch.setenv("CARDIOCAM_TOKEN", TOKEN)
    s = SessaoTelemetria("participante-01", TOKEN, True)
    with receptor_local(s) as url:
        assert main(["teleconsulta", "transmitir", str(arquivo), "--url", url,
                     "--sessao", "participante-01", "--consentimento"]) == 0
        assert len(s.leituras()) == 2
    assert main(["teleconsulta", "receber", "--sessao", "participante-01", "--duracao", "0.01",
                 "--porta", "0", "--consentimento"]) == 0
    assert main(["teleconsulta", "transmitir", str(arquivo), "--url", "http://example.com/leituras", "--sessao", "p"]) == 1
