"""Testes da gravação e leitura do modelo de qualidade.

O modelo decide se o sistema responde ou recusa. Ele sair do treino e entrar num
arquivo é o que o faz existir em produção, e é também onde mora um erro
silencioso específico: o vetor de características e os pesos precisam estar na
**mesma ordem**, e nada no formato impede que deixem de estar.

Se alguém acrescentar uma característica ao extrator e esquecer de retreinar, o
vetor novo tem doze posições e os pesos têm onze. O melhor caso é quebrar. O pior
é alinhar errado e devolver uma probabilidade plausível calculada a partir de
colunas trocadas, que é indistinguível de uma probabilidade correta e decide
recusar ou responder com base em nada.

Por isso os nomes vão gravados no arquivo e são conferidos na leitura, e por isso
o teste mais importante aqui é o que corrompe os nomes de propósito.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from cardiocam.qualidade.bayes import RegressaoLogisticaBayesiana
from cardiocam.qualidade.calibracao import Temperatura
from cardiocam.qualidade.caracteristicas import Caracteristicas, Padronizador
from cardiocam.qualidade.persistencia import (
    CAMINHO_PADRAO,
    Procedencia,
    agora_em_texto,
    carregar,
    carregar_se_houver,
    salvar,
)
from cardiocam.qualidade.treino import ModeloDeQualidade


def _modelo() -> ModeloDeQualidade:
    nomes = tuple(Caracteristicas.nomes())
    n = len(nomes)
    gerador = np.random.default_rng(3)
    media = gerador.normal(size=n + 1)
    # Covariância positiva definida, como a aproximação de Laplace produz.
    base = gerador.normal(size=(n + 1, n + 1))
    covariancia = base @ base.T + np.eye(n + 1)
    return ModeloDeQualidade(
        regressao=RegressaoLogisticaBayesiana(
            media=media, covariancia=covariancia, nomes=nomes
        ),
        padronizador=Padronizador(
            media=gerador.normal(size=n), desvio=np.abs(gerador.normal(size=n)) + 0.5,
            nomes=nomes,
        ),
        limiar=0.65,
        tolerancia_bpm=3.0,
        temperatura=Temperatura(0.514),
    )


def _procedencia() -> Procedencia:
    return Procedencia(
        treinado_em=agora_em_texto(),
        janelas=349,
        bateria="88 cenários",
        erro_respondendo_sempre=8.16,
        erro_com_abstencao=5.39,
        cobertura=0.492,
    )


class TestIdaEVolta:
    def test_calibracao_inviavel_continua_recusando_apos_carregar(self, tmp_path):
        modelo = replace(_modelo(), calibracao_viavel=False)
        lido, _ = carregar(salvar(modelo, _procedencia(), tmp_path / "inviavel.json"))
        assert not lido.calibracao_viavel
        valores = dict.fromkeys(Caracteristicas.nomes(), 0.0)
        assert not lido.aceita(Caracteristicas(**valores))

    def test_a_probabilidade_sobrevive_ao_arquivo(self, tmp_path):
        """O que importa não é o arquivo bater campo a campo: é o modelo lido
        decidir **a mesma coisa** que o gravado, sobre a mesma janela."""
        original = _modelo()
        caminho = salvar(original, _procedencia(), tmp_path / "m.json")
        lido, _ = carregar(caminho)

        gerador = np.random.default_rng(11)
        for _ in range(20):
            valores = dict(zip(Caracteristicas.nomes(), gerador.normal(size=11)))
            janela = Caracteristicas(**valores)
            assert lido.probabilidade(janela) == pytest.approx(
                original.probabilidade(janela), abs=1e-12
            )

    def test_os_escalares_voltam_iguais(self, tmp_path):
        original = _modelo()
        lido, _ = carregar(salvar(original, _procedencia(), tmp_path / "m.json"))
        assert lido.limiar == original.limiar
        assert lido.tolerancia_bpm == original.tolerancia_bpm
        assert lido.temperatura.valor == original.temperatura.valor

    def test_a_procedencia_volta(self, tmp_path):
        """Modelo que decide recusar sem dizer de onde veio é modelo que
        ninguém pode defender."""
        _, procedencia = carregar(salvar(_modelo(), _procedencia(), tmp_path / "m.json"))
        assert procedencia.janelas == 349
        assert procedencia.erro_respondendo_sempre == pytest.approx(8.16)
        assert procedencia.cobertura == pytest.approx(0.492)


class TestRecusaOArquivoErrado:
    def test_caracteristica_trocada_e_recusada(self, tmp_path):
        """O erro silencioso que este formato poderia ter.

        Com os nomes fora de ordem, o vetor e os pesos continuam com o mesmo
        tamanho e a conta roda. O resultado é uma probabilidade plausível
        calculada sobre colunas trocadas, e nada no número denuncia isso.
        """
        caminho = salvar(_modelo(), _procedencia(), tmp_path / "m.json")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["nomes"][0], dados["nomes"][1] = dados["nomes"][1], dados["nomes"][0]
        caminho.write_text(json.dumps(dados), encoding="utf-8")

        with pytest.raises(ValueError, match="não são as que o extrator produz"):
            carregar(caminho)

    def test_caracteristica_a_mais_e_recusada(self, tmp_path):
        caminho = salvar(_modelo(), _procedencia(), tmp_path / "m.json")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["nomes"].append("inventada")
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        with pytest.raises(ValueError):
            carregar(caminho)

    def test_versao_diferente_e_recusada(self, tmp_path):
        caminho = salvar(_modelo(), _procedencia(), tmp_path / "m.json")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["versao"] = 99
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        with pytest.raises(ValueError, match="versão"):
            carregar(caminho)


class TestFaltaDeModeloNaoEErro:
    def test_arquivo_ausente_devolve_nada(self, tmp_path):
        """O programa funciona sem modelo, voltando à regra fixa. Falta de
        arquivo é situação prevista, não falha."""
        assert carregar_se_houver(tmp_path / "nao_existe.json") is None

    def test_arquivo_corrompido_devolve_nada(self, tmp_path):
        ruim = tmp_path / "m.json"
        ruim.write_text("isto não é json", encoding="utf-8")
        assert carregar_se_houver(ruim) is None

    def test_arquivo_invalido_devolve_nada(self, tmp_path):
        caminho = salvar(_modelo(), _procedencia(), tmp_path / "m.json")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["nomes"] = ["so_uma"]
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        assert carregar_se_houver(caminho) is None


class TestModeloQueAcompanhaOPrograma:
    def test_o_modelo_distribuido_carrega(self):
        """O arquivo que vai junto com o executável precisa estar válido.

        Sem este teste, uma mudança no extrator passaria no resto da suíte e o
        programa sairia para o usuário decidindo pela regra fixa, em silêncio,
        com o modelo no disco e sem ser usado.
        """
        if not CAMINHO_PADRAO.exists():
            pytest.skip("o modelo ainda não foi treinado neste repositório")
        modelo, procedencia = carregar(CAMINHO_PADRAO)
        assert 0.0 <= modelo.limiar <= 1.0
        assert modelo.tolerancia_bpm > 0
        assert modelo.temperatura.valor > 0
        assert procedencia.janelas > 0
        assert tuple(modelo.regressao.nomes) == tuple(Caracteristicas.nomes())

    def test_o_modelo_distribuido_decide_dentro_de_zero_e_um(self):
        if not CAMINHO_PADRAO.exists():
            pytest.skip("o modelo ainda não foi treinado neste repositório")
        modelo, _ = carregar(CAMINHO_PADRAO)
        gerador = np.random.default_rng(5)
        for _ in range(30):
            valores = dict(zip(Caracteristicas.nomes(), gerador.normal(size=11) * 3))
            p = modelo.probabilidade(Caracteristicas(**valores))
            assert 0.0 <= p <= 1.0
