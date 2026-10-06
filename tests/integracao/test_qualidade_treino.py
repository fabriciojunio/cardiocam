"""Testes do treino, da partição e do caminho completo com dado real.

O teste que mais importa aqui é o de vazamento de grupo. Ele é barato e
silencioso: se a partição deixar janelas da mesma condição dos dois lados, tudo
continua passando e o número final fica otimista sem nenhum sintoma. É o tipo
de defeito que só aparece quando alguém tenta reproduzir o resultado com dado
de verdade e não chega perto.

A classe final roda a bateria sintética inteira pelo pipeline real, treina e
cobra que a abstenção de fato reduza o erro. É o teste mais lento do módulo e é
o único que prova que as peças funcionam juntas.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import cenarios_de_robustez, cenarios_padrao
from cardiocam.qualidade.calibracao import Temperatura, aferir
from cardiocam.qualidade.caracteristicas import Caracteristicas
from cardiocam.qualidade.coleta import coletar
from cardiocam.qualidade.treino import Amostra, particionar, treinar


def _amostra(valor: float, erro: float, grupo: str) -> Amostra:
    """Amostra sintética em que só o SNR varia, para testar a mecânica."""
    return Amostra(
        caracteristicas=Caracteristicas(
            snr_db=valor,
            proeminencia=valor / 10.0,
            entropia_espectral=0.5,
            razao_harmonica=0.3,
            dispersao_do_pico_bpm=1.0,
            fracao_de_pele=1.0,
            fracao_saturada=0.0,
            deslocamento_roi=0.0,
            correlacao_com_fundo=0.0,
            jitter_temporal=0.0,
            desvio_cromatico=0.0,
        ),
        erro_bpm=erro,
        grupo=grupo,
    )


class TestParticao:
    def test_nenhum_grupo_aparece_em_duas_particoes(self):
        """O teste que impede o número final de medir memorização."""
        grupos = [f"g{i % 10}" for i in range(500)]
        particao = particionar(grupos, semente=3)
        array = np.array(grupos)
        de_treino = set(array[particao.treino])
        de_calibracao = set(array[particao.calibracao])
        de_teste = set(array[particao.teste])
        assert de_treino & de_calibracao == set()
        assert de_treino & de_teste == set()
        assert de_calibracao & de_teste == set()

    def test_cobre_todos_os_indices_sem_repetir(self):
        grupos = [f"g{i % 7}" for i in range(140)]
        particao = particionar(grupos)
        juntos = np.concatenate(
            [particao.treino, particao.calibracao, particao.teste]
        )
        assert sorted(juntos.tolist()) == list(range(140))

    def test_e_reprodutivel_por_semente(self):
        grupos = [f"g{i % 9}" for i in range(90)]
        a = particionar(grupos, semente=5)
        b = particionar(grupos, semente=5)
        assert np.array_equal(a.treino, b.treino)
        assert np.array_equal(a.teste, b.teste)

    def test_sementes_diferentes_mudam_a_divisao(self):
        grupos = [f"g{i % 9}" for i in range(90)]
        a = particionar(grupos, semente=1)
        b = particionar(grupos, semente=2)
        assert not np.array_equal(a.treino, b.treino)

    def test_o_teste_nunca_fica_vazio(self):
        """Com poucos grupos o arredondamento poderia engolir o teste."""
        for quantidade in (3, 4, 5, 6, 7):
            grupos = [f"g{i % quantidade}" for i in range(quantidade * 4)]
            particao = particionar(grupos)
            assert particao.teste.size > 0, f"{quantidade} grupos deixou teste vazio"

    def test_exige_ao_menos_tres_grupos(self):
        with pytest.raises(ValueError, match="ao menos 3"):
            particionar(["a", "a", "b", "b"])

    def test_rejeita_fracoes_que_nao_deixam_teste(self):
        with pytest.raises(ValueError, match="espaço para o teste"):
            particionar(
                [f"g{i}" for i in range(10)],
                fracao_treino=0.9,
                fracao_calibracao=0.2,
            )


class TestTemperatura:
    def test_recupera_uma_distorcao_conhecida(self):
        """Gera previsões exageradas por um fator conhecido e o reencontra."""
        gerador = np.random.default_rng(1)
        verdadeiras = gerador.uniform(0.05, 0.95, 4000)
        rotulos = (gerador.uniform(0.0, 1.0, 4000) < verdadeiras).astype(float)
        logitos = np.log(verdadeiras / (1.0 - verdadeiras))
        exageradas = 1.0 / (1.0 + np.exp(-logitos * 2.2))
        encontrada = Temperatura.ajustar(exageradas, rotulos)
        assert encontrada.valor == pytest.approx(2.2, rel=0.15)

    def test_melhora_a_calibracao_que_distorceu(self):
        gerador = np.random.default_rng(2)
        verdadeiras = gerador.uniform(0.05, 0.95, 4000)
        rotulos = (gerador.uniform(0.0, 1.0, 4000) < verdadeiras).astype(float)
        logitos = np.log(verdadeiras / (1.0 - verdadeiras))
        exageradas = 1.0 / (1.0 + np.exp(-logitos * 2.5))
        antes = aferir(exageradas, rotulos).ece
        temperatura = Temperatura.ajustar(exageradas, rotulos)
        depois = aferir(temperatura.aplicar(exageradas), rotulos).ece
        assert depois < antes / 2.0

    def test_nao_altera_a_ordenacao(self):
        """É a propriedade que mantém a curva de abstenção intacta."""
        probabilidades = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        ajustadas = Temperatura(2.7).aplicar(probabilidades)
        assert list(np.argsort(ajustadas)) == list(np.argsort(probabilidades))

    def test_temperatura_um_nao_muda_nada(self):
        probabilidades = np.array([0.1, 0.44, 0.9])
        assert Temperatura(1.0).aplicar(probabilidades) == pytest.approx(
            probabilidades
        )


class TestTreino:
    @staticmethod
    def _mistura(n_grupos: int = 8, por_grupo: int = 20) -> list[Amostra]:
        """Grupos que contêm janelas boas E ruins, com o SNR separando as duas.

        A primeira versão deste conjunto punha as boas num grupo e as ruins
        noutro, e o treino caía com "uma classe só" sempre que a partição
        isolava um tipo. Além de frágil, era irreal: nenhuma condição de
        gravação produz só janela boa ou só janela ruim.
        """
        amostras: list[Amostra] = []
        for g in range(n_grupos):
            for i in range(por_grupo):
                boa = i % 2 == 0
                amostras.append(
                    _amostra(
                        25.0 + i if boa else -8.0 + i,
                        0.5 if boa else 30.0,
                        f"g{g}",
                    )
                )
        return amostras

    def test_a_abstencao_reduz_o_erro_quando_ha_o_que_reduzir(self):
        relatorio = treinar(self._mistura(), cobertura_minima=0.3, erro_alvo_bpm=5.0)
        assert (
            relatorio.ponto_adotado.erro_medio
            < relatorio.curva_no_teste.erro_sem_abstencao
        )

    def test_recusa_treinar_com_uma_classe_so(self):
        """Sem contraste não há o que aprender, e é melhor dizer."""
        amostras = [_amostra(20.0 + i, 0.1, f"g{i % 5}") for i in range(50)]
        with pytest.raises(ValueError, match="uma classe só"):
            treinar(amostras)

    def test_recusa_conjunto_minusculo(self):
        amostras = [_amostra(20.0, 0.1, f"g{i}") for i in range(5)]
        with pytest.raises(ValueError, match="Abaixo de uma dezena"):
            treinar(amostras)

    def test_sem_limiar_viavel_adota_responder_sempre(self):
        """O limiar 0 é resultado, não falha: nenhum ponto atendeu ao pedido.

        Pede cobertura de 90% com erro de 0,1 bpm, que o conjunto não entrega
        em limiar nenhum.
        """
        relatorio = treinar(
            self._mistura(), cobertura_minima=0.9, erro_alvo_bpm=0.1
        )
        assert relatorio.modelo.limiar == 0.0
        assert relatorio.ponto_adotado.cobertura == 1.0

    def test_o_rotulo_segue_a_tolerancia_pedida(self):
        amostra = _amostra(10.0, 2.5, "g")
        assert amostra.rotulo(tolerancia_bpm=3.0) == 1.0
        assert amostra.rotulo(tolerancia_bpm=2.0) == 0.0


@pytest.mark.lento
class TestCaminhoCompleto:
    """Bateria real, pipeline real, do vídeo sintético até a decisão de recusar."""

    @pytest.fixture(scope="class")
    @classmethod
    def treinado(cls):
        amostras, falhas = coletar(cenarios_padrao() + cenarios_de_robustez())
        return treinar(amostras, cobertura_minima=0.4, erro_alvo_bpm=2.0), falhas

    def test_a_coleta_produz_uma_amostra_por_janela_bem_sucedida(self, treinado):
        relatorio, falhas = treinado
        total = (
            relatorio.quantidade_treino
            + relatorio.quantidade_calibracao
            + relatorio.quantidade_teste
        )
        # 56 cenários padrão mais 28 de robustez, vezes quatro algoritmos.
        assert total + falhas == (56 + 28) * 4

    def test_a_bateria_tem_erro_para_a_abstencao_atacar(self, treinado):
        """Controle do próprio experimento.

        A bateria padrão sozinha não serve: cinco das suas sete condições
        acertam 100%. Se este teste passar a falhar, quer dizer que os cenários
        de robustez pararam de produzir erro, e o resto do módulo passa a medir
        ruído.
        """
        relatorio, _ = treinado
        assert relatorio.curva_no_teste.erro_sem_abstencao > 1.0

    def test_recusar_reduz_o_erro(self, treinado):
        relatorio, _ = treinado
        melhor = min(
            (p for p in relatorio.curva_no_teste.pontos if p.quantidade > 0),
            key=lambda p: p.erro_medio,
        )
        assert melhor.erro_medio < relatorio.curva_no_teste.erro_sem_abstencao * 0.8

    def test_as_caracteristicas_de_sinal_sustentam_os_proprios_pesos(self, treinado):
        """Ao menos a relação sinal-ruído precisa ter peso acima do seu desvio.

        Se nem ela sustentar, o modelo não aprendeu nada e a redução de erro
        observada seria coincidência da partição.
        """
        relatorio, _ = treinado
        regressao = relatorio.modelo.regressao
        assert abs(regressao.pesos["snr_db"]) > regressao.desvios_dos_pesos["snr_db"]

    def test_caracteristica_sem_variacao_fica_com_a_priori(self, treinado):
        """O modelo precisa dizer "não sei" sobre o que não observou.

        No caminho analítico não há imagem, então fração de pele é constante. O
        peso tem que ficar em zero com o desvio da priori, e não num valor
        qualquer que depois seria lido como informação.
        """
        relatorio, _ = treinado
        regressao = relatorio.modelo.regressao
        assert regressao.pesos["fracao_de_pele"] == pytest.approx(0.0, abs=1e-6)
        assert regressao.desvios_dos_pesos["fracao_de_pele"] == pytest.approx(
            2.0, abs=1e-6
        )

    def test_o_modelo_decide_sobre_uma_janela_isolada(self, treinado):
        """A interface que o sistema usa em produção."""
        relatorio, _ = treinado
        boa = _amostra(30.0, 0.1, "x").caracteristicas
        probabilidade = relatorio.modelo.probabilidade(boa)
        assert 0.0 <= probabilidade <= 1.0
        assert isinstance(relatorio.modelo.aceita(boa), bool)

    def test_o_resumo_sai_sem_quebrar(self, treinado):
        relatorio, _ = treinado
        texto = relatorio.resumo()
        assert "cobertura" in texto
        assert "ECE" in texto
