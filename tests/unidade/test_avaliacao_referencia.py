"""A avaliação preserva recusas e não inventa uma referência em lacunas."""

import json

import pytest

from cardiocam.avaliacao.referencia import avaliar_csv, avaliar_manifesto


@pytest.fixture
def arquivos(tmp_path):
    ref = tmp_path / "referencia.csv"
    ref.write_text("instante_s,bpm\n0,60\n1,60\n2,60\n3,60\n", encoding="utf-8")
    leituras = tmp_path / "leituras.csv"
    leituras.write_text("instante_s,bpm,aceita\n0,62,True\n1,58,True\n2,,False\n", encoding="utf-8")
    return leituras, ref


def test_erro_cobertura_e_limites_sao_calculados(arquivos):
    resultado = avaliar_csv(*arquivos)
    assert resultado.registros == 3
    assert resultado.aceitas == 2
    assert resultado.cobertura_registros == pytest.approx(2 / 3)
    assert resultado.mae_bpm == 2
    assert resultado.rmse_bpm == 2
    assert resultado.vies_bpm == 0
    assert resultado.limite_superior_bpm == pytest.approx(1.96 * 8 ** .5)
    assert resultado.proporcao_dentro_5_bpm == 1
    assert resultado.proporcao_aceitas_com_erro_acima_5_bpm == 0


def test_lacuna_na_referencia_nao_e_interpolada(arquivos):
    leituras, ref = arquivos
    ref.write_text("instante_s,bpm\n0,60\n10,60\n", encoding="utf-8")
    resultado = avaliar_csv(leituras, ref, offset_s=1)
    assert resultado.com_referencia == 0
    assert resultado.aceitas == 0
    assert resultado.mae_bpm is None
    assert resultado.cobertura_registros == 0


@pytest.mark.parametrize("conteudo", ["0,60\n0,60", "0,nan\n1,60", "0,60\n1,-5"])
def test_referencia_invalida_e_recusada(arquivos, conteudo):
    leituras, ref = arquivos
    ref.write_text("instante_s,bpm\n" + conteudo, encoding="utf-8")
    with pytest.raises(ValueError):
        avaliar_csv(leituras, ref)


def test_manifesto_mantem_participantes_e_procedencia(arquivos, tmp_path):
    sessao = {"participante": "p01", "dispositivo": "camera01", "condicao": "repouso",
              "dataset": "teste sintético", "licenca": "dados de teste",
              "leituras": "leituras.csv", "referencia": "referencia.csv"}
    manifesto = tmp_path / "manifesto.json"
    manifesto.write_text(json.dumps({"sessoes": [sessao, sessao]}), encoding="utf-8")
    relatorio = avaliar_manifesto(manifesto)
    assert relatorio["participantes"] == 1
    assert len(relatorio["sessoes"]) == 2
    assert "não equivale" in relatorio["aviso"]
    sessao.pop("licenca")
    manifesto.write_text(json.dumps({"sessoes": [sessao]}), encoding="utf-8")
    with pytest.raises(ValueError, match="licenca"):
        avaliar_manifesto(manifesto)


def test_comando_grava_json_com_acentuacao_e_sem_nan(arquivos, tmp_path, monkeypatch):
    from cardiocam.avaliacao.referencia import principal
    sessao = {"participante": "p01", "dispositivo": "câmera", "condicao": "repouso",
              "dataset": "teste sintético", "licenca": "dados de teste",
              "leituras": "leituras.csv", "referencia": "referencia.csv"}
    manifesto = tmp_path / "manifesto.json"
    manifesto.write_text(json.dumps({"sessoes": [sessao]}), encoding="utf-8")
    destino = tmp_path / "resultado.json"
    monkeypatch.setattr("sys.argv", ["avaliar", str(manifesto), "--saida", str(destino)])
    principal()
    texto = destino.read_text(encoding="utf-8")
    assert "câmera" in texto
    assert "NaN" not in texto
    assert json.loads(texto)["participantes"] == 1


@pytest.mark.parametrize("bpm,aceita", [("nan", "True"), ("60", "talvez")])
def test_leitura_invalida_e_recusada_mesmo_fora_da_referencia(arquivos, bpm, aceita):
    leituras, ref = arquivos
    leituras.write_text(f"instante_s,bpm,aceita\n99,{bpm},{aceita}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        avaliar_csv(leituras, ref)


def test_proporcao_de_erro_acima_da_tolerancia(arquivos):
    leituras, ref = arquivos
    leituras.write_text("instante_s,bpm,aceita\n0,60,True\n1,66,True\n2,200,False\n", encoding="utf-8")
    resultado = avaliar_csv(leituras, ref)
    assert resultado.proporcao_dentro_5_bpm == .5
    assert resultado.proporcao_aceitas_com_erro_acima_5_bpm == .5
