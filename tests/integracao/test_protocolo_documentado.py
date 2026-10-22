"""O exemplo publicado precisa ser executável e ter métricas conhecidas."""

from pathlib import Path
import re

import pytest

from cardiocam.avaliacao.referencia import avaliar_manifesto


def test_manifesto_documentado_tem_resultado_reproduzivel():
    origem = Path(__file__).resolve().parents[2] / "docs" / "exemplos" / "manifesto-sintetico.json"
    resultado = avaliar_manifesto(origem)
    assert resultado["participantes"] == 1
    sessao = resultado["sessoes"][0]
    assert "sintético" in sessao["condicao"]
    assert sessao["metricas"]["mae_bpm"] == 2
    assert sessao["metricas"]["rmse_bpm"] == 2
    assert sessao["metricas"]["vies_bpm"] == 0
    assert sessao["metricas"]["cobertura_registros"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("nome", ["README.md", "docs/validacao-e-plano.md",
                                  "docs/protocolo-validacao-real.md", "docs/fontes-de-pesquisa.md"])
def test_documentos_revisados_tem_utf8_e_links_locais_validos(nome):
    caminho = Path(__file__).resolve().parents[2] / nome
    texto = caminho.read_bytes().decode("utf-8")
    assert "\ufffd" not in texto
    assert not re.search(r"Ã[\u0080-¿]|Â[\u0080-¿]", texto)
    for link in re.findall(r"\]\(([^)]+)\)", texto):
        if not link.startswith(("http://", "https://", "#")):
            assert (caminho.parent / link.split("#")[0]).exists(), link
