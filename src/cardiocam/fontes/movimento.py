"""Física do artefato de movimento, separada do resto do simulador.

Movimento é a limitação mais citada de qualquer medidor de pulso por câmera, e
até aqui o simulador do projeto deslocava a cabeça por uma senoide e nada mais.
Isso não produz artefato nenhum, e a razão é instrutiva: o rastreador segue o
deslocamento, as regiões de interesse acompanham, e a média de cor sai idêntica
à do rosto parado. Medimos e confirmamos: com `movimento_px=8` e nada mais, o
erro do POS não muda na terceira casa.

Quer dizer que o simulador estava otimista, não errado. Deslocar o desenho
reproduz só uma das quatro coisas que o movimento real faz, e justamente a mais
fácil de compensar. As outras três são as que derrubam a medição:

1. **Sombreado por pose.** Virar a cabeça muda o ângulo entre a pele e a luz, e
   o componente difuso escala com o cosseno desse ângulo. Isso multiplica a cor
   da pele nos três canais na mesma proporção, que é exatamente a distorção que
   CHROM e POS cancelam por construção. Entra aqui porque é o maior em
   amplitude, e porque é o controle do experimento: se o erro subisse só com
   ele, a conclusão seria que os métodos cromáticos não servem, e não é isso.

2. **Reflexo especular por pose.** O brilho que a pele devolve sem penetrar tem
   a cor da *luz*, não a cor da pele. Ele entra somado, não multiplicado, e com
   a cromaticidade do iluminante. É o termo que quebra a hipótese de tom de pele
   padronizado em que CHROM e POS se apoiam, e por isso é o que de fato
   degrada os dois.

3. **Desregistro da região.** O rastreador suaviza a caixa por média
   exponencial, o que por definição a deixa atrasada em relação ao rosto. Com
   movimento rápido o atraso faz a região medir borda de rosto, cabelo e fundo.
   O simulador já tem a máquina para isso; faltava acioná-la forte o bastante.

4. **Movimento da câmera.** Diferente do movimento da cabeça num ponto que
   importa muito: ele arrasta o fundo junto. O projeto usa o fundo como
   referência de iluminação, e essa referência só é válida se o trecho de fundo
   for o mesmo trecho ao longo do tempo. Câmera tremendo troca o trecho, e a
   correção passa a injetar o ruído que deveria remover.

Mais o desfoque por movimento e a resposta do ganho automático, que são de
segunda ordem mas aparecem em câmera de notebook.

**Todo parâmetro novo tem padrão neutro.** Com os padrões, as séries saem
bit a bit idênticas às de antes, e os números já publicados no README
continuam valendo. A escolha é deliberada e é a mesma que se fez no Lastro: um
simulador que muda de resposta ao ganhar um recurso invalida toda medição
anterior sem avisar.

Referências do modelo de reflexão: Shafer (1985) para a separação dicromática
entre difuso e especular; Wang et al. (2017) para a formulação do plano
ortogonal ao tom de pele, que é onde a hipótese de cromaticidade fixa aparece
explícita; Verkruysse et al. (2008) para a dominância do canal verde.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Cromaticidade do reflexo especular, em BGR normalizado.
#
# Luz de escritório e tela de computador puxam para o azul em relação à pele,
# que é dominada pelo vermelho. O contraste entre as duas cromaticidades é o
# que torna o termo especular visível para os métodos cromáticos: se o reflexo
# tivesse a mesma cor da pele, ele seria indistinguível de sombreado difuso.
CROMATICIDADE_ESPECULAR = (1.00, 0.98, 0.92)


@dataclass(frozen=True, slots=True)
class ParametrosMovimento:
    """Os termos que transformam deslocamento em erro de medição.

    Separados em dataclass própria para que um cenário possa ser descrito como
    "o movimento tal", e para que a lista de parâmetros da simulação não cresça
    para trinta campos soltos.
    """

    amplitude_px: float = 0.0
    """Deslocamento máximo da cabeça, em pixels."""

    banda_hz: tuple[float, float] = (0.1, 1.2)
    """Faixa do movimento. Movimento humano é de banda larga, não senoidal.

    O limite superior invade de propósito a banda do pulso (0,7 a 4 Hz): é essa
    sobreposição que impede o passa-faixa de resolver o problema, e é por isso
    que movimento não se conserta com filtro.
    """

    sombreado_por_pose: float = 0.0
    """Quanto o componente difuso varia por pixel de deslocamento.

    Multiplicativo e igual nos três canais. Em 0,004 por pixel, um deslocamento
    de 10 px dá 4% de variação de intensidade, que é duas ordens de grandeza
    acima do pulso.
    """

    especular_por_pose: float = 0.0
    """Quanto do reflexo especular varia por pixel de deslocamento.

    Aditivo, com a cor do iluminante. É o termo que de fato derruba CHROM e POS.
    """

    desfoque_por_px: float = 0.0
    """Desfoque por movimento, em pixels de núcleo por pixel de deslocamento
    entre quadros."""

    camera_px: float = 0.0
    """Tremor da câmera, em pixels. Arrasta o fundo junto com o rosto."""

    camera_banda_hz: tuple[float, float] = (0.5, 3.0)
    """Tremor de mão é mais rápido que movimento de cabeça."""

    ganho_automatico: float = 0.0
    """Fração da variação de brilho que a câmera compensa sozinha.

    O controle automático de exposição reage com atraso, e essa reação
    atrasada é ela própria uma oscilação de intensidade correlacionada com o
    movimento.
    """

    constante_do_ganho_s: float = 0.6
    """Constante de tempo da resposta do ganho automático."""

    @property
    def ativo(self) -> bool:
        """Verdadeiro quando algum termo sai do padrão neutro.

        O simulador usa isto para pular o caminho novo por completo e garantir
        que o comportamento antigo seja bit a bit o mesmo.
        """
        return any(
            (
                self.amplitude_px,
                self.sombreado_por_pose,
                self.especular_por_pose,
                self.desfoque_por_px,
                self.camera_px,
                self.ganho_automatico,
            )
        )


def _ruido_de_banda(
    tempos: np.ndarray,
    banda_hz: tuple[float, float],
    semente: int,
) -> np.ndarray:
    """Sinal aleatório confinado a uma faixa, com desvio padrão unitário.

    Construído no domínio da frequência em vez de filtrando ruído branco,
    porque assim a banda é exata e não depende da ordem nem da resposta de
    nenhum filtro. Para um simulador isso importa: o cenário tem de ser
    descrito pelo que ele contém, não pelo filtro que o produziu.
    """
    n = tempos.size
    if n < 4:
        return np.zeros(n, dtype=float)

    # Passo médio, porque os instantes podem ter jitter.
    duracao = float(tempos[-1] - tempos[0])
    if duracao <= 0:
        return np.zeros(n, dtype=float)
    passo = duracao / max(1, n - 1)

    frequencias = np.fft.rfftfreq(n, d=passo)
    baixa, alta = banda_hz
    dentro = (frequencias >= baixa) & (frequencias <= alta)
    if not np.any(dentro):
        return np.zeros(n, dtype=float)

    gerador = np.random.default_rng(semente)
    fases = gerador.uniform(0.0, 2.0 * np.pi, frequencias.size)
    espectro = np.zeros(frequencias.size, dtype=complex)
    # Espectro plano dentro da banda: nenhuma frequência da faixa é
    # privilegiada, o que evita que o resultado dependa de onde o pulso caiu.
    espectro[dentro] = np.exp(1j * fases[dentro])
    espectro[0] = 0.0  # sem componente contínua: movimento é em torno do centro

    sinal = np.fft.irfft(espectro, n=n)
    desvio = float(np.std(sinal))
    return sinal / desvio if desvio > 1e-12 else sinal


@dataclass(frozen=True, slots=True)
class TrajetoriaMovimento:
    """O movimento já calculado para todos os quadros do vídeo.

    Pré-calcular é o que mantém a renderização barata: a suíte de testes
    renderiza dezenas de milhares de quadros, e sortear ruído de banda por
    quadro seria o gargalo.
    """

    deslocamento_cabeca: np.ndarray
    """Deslocamento da cabeça por quadro, em pixels (eixo horizontal)."""

    deslocamento_camera: np.ndarray
    """Deslocamento da câmera por quadro, em pixels."""

    fator_difuso: np.ndarray
    """Multiplicador do componente difuso, por quadro."""

    termo_especular: np.ndarray
    """Intensidade do reflexo especular somado, por quadro."""

    desfoque: np.ndarray
    """Tamanho do núcleo de desfoque por quadro, em pixels."""

    @property
    def total_quadros(self) -> int:
        return int(self.deslocamento_cabeca.size)


def trajetoria(
    tempos: np.ndarray,
    parametros: ParametrosMovimento,
    semente: int = 0,
) -> TrajetoriaMovimento:
    """Calcula o movimento e os artefatos que ele causa, quadro a quadro."""
    n = tempos.size
    zeros = np.zeros(n, dtype=float)

    if not parametros.ativo:
        return TrajetoriaMovimento(zeros, zeros, np.ones(n), zeros, zeros)

    cabeca = (
        parametros.amplitude_px
        * _ruido_de_banda(tempos, parametros.banda_hz, semente + 101)
        if parametros.amplitude_px
        else zeros
    )
    camera = (
        parametros.camera_px
        * _ruido_de_banda(tempos, parametros.camera_banda_hz, semente + 211)
        if parametros.camera_px
        else zeros
    )

    # O que muda a iluminação da pele é a pose da cabeça em relação à luz. O
    # tremor da câmera desloca a imagem inteira sem mudar essa pose, então ele
    # não entra no sombreado; entra no desregistro e na referência de fundo.
    pose = np.abs(cabeca)

    fator_difuso = 1.0 + parametros.sombreado_por_pose * (pose - float(np.mean(pose)))
    termo_especular = parametros.especular_por_pose * pose

    if parametros.ganho_automatico:
        # Resposta de primeira ordem ao brilho observado. O ganho persegue a
        # variação com atraso, e é o atraso que faz dele um artefato: se a
        # compensação fosse instantânea, ela cancelaria a variação em vez de
        # criar uma nova.
        passo = (
            float(tempos[-1] - tempos[0]) / max(1, n - 1) if n > 1 else 0.0
        )
        alfa = (
            passo / max(1e-6, parametros.constante_do_ganho_s + passo)
            if passo > 0
            else 1.0
        )
        perseguido = np.empty(n, dtype=float)
        acumulado = float(fator_difuso[0])
        for i in range(n):
            acumulado += alfa * (float(fator_difuso[i]) - acumulado)
            perseguido[i] = acumulado
        # A câmera divide pelo que ela acha que é o brilho da cena.
        compensacao = 1.0 - parametros.ganho_automatico * (perseguido - 1.0)
        fator_difuso = fator_difuso * compensacao

    if parametros.desfoque_por_px:
        total = cabeca + camera
        velocidade = np.abs(np.diff(total, prepend=total[0]))
        desfoque = parametros.desfoque_por_px * velocidade
    else:
        desfoque = zeros

    return TrajetoriaMovimento(
        deslocamento_cabeca=cabeca,
        deslocamento_camera=camera,
        fator_difuso=fator_difuso,
        termo_especular=termo_especular,
        desfoque=desfoque,
    )


def aplicar_especular(
    modulacao_bgr: np.ndarray,
    tom_pele_bgr: tuple[int, int, int],
    intensidade: float,
) -> np.ndarray:
    """Soma o reflexo especular ao multiplicador da pele.

    O simulador compõe cada quadro como `constante + m · camada_de_pele`, com
    `m` em BGR. O reflexo é aditivo em intensidade absoluta, então para entrar
    nesse formato ele é convertido em um acréscimo equivalente de `m`,
    dividindo pela cor base de cada canal.

    É essa divisão que faz o termo mudar a *cromaticidade* e não só o brilho: o
    azul da pele é o canal mais fraco, então o mesmo acréscimo absoluto pesa
    mais nele. A consequência é exatamente a quebra da hipótese de tom de pele
    fixo, e é por isso que este termo derruba CHROM e POS enquanto o sombreado
    difuso não derruba.
    """
    if intensidade <= 0:
        return modulacao_bgr

    base = np.asarray(tom_pele_bgr, dtype=float)
    base = np.where(base > 1.0, base, 1.0)
    acrescimo = intensidade * np.asarray(CROMATICIDADE_ESPECULAR, dtype=float) / base
    return np.asarray(modulacao_bgr, dtype=float) + acrescimo
