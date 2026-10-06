"""O que descreve uma janela sem olhar a resposta certa.

Esta é a restrição que organiza o módulo inteiro, e vale escrever em voz alta:
**nenhuma característica aqui pode depender da frequência verdadeira.** Em
produção ela não existe, e uma característica que a use produziria um modelo que
funciona lindamente na avaliação e não funciona em uso. É o vazamento de
informação clássico, e num trabalho de medição ele é fatal porque o número
publicado fica alto e errado.

Por isso tudo aqui sai de três lugares que existem em tempo de execução: o
sinal de pulso da janela, o espectro dela, e o contexto que o rastreador e a
máscara de pele já computam de qualquer jeito.

As características estão agrupadas pelo mecanismo de falha que cada uma pega,
porque é isso que as torna defensáveis uma a uma em vez de uma lista arbitrária:

**Forma do espectro**, que pega "o pulso não emerge do ruído":
`snr_db`, `proeminencia`, `entropia_espectral`, `razao_harmonica`.

**Coerência no tempo**, que pega "o pico existe mas pula de lugar":
`dispersao_do_pico_bpm`.

**Condição da imagem**, que pega "não havia pele suficiente para medir":
`fracao_de_pele`, `fracao_saturada`.

**Perturbação externa**, que pega "o que oscila não é sangue":
`deslocamento_roi`, `correlacao_com_fundo`, `jitter_temporal`.

A quarta família é a que liga diretamente às hipóteses H1 e H2 do projeto, e é
por isso que ela existe mesmo quando o contexto não está disponível: quando não
está, o valor vai como neutro e isso fica registrado, em vez de a característica
sumir e mudar a dimensão do vetor sem avisar.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass, fields

import numpy as np

from cardiocam.dominio.estimativa import Espectro
from cardiocam.dominio.sinal import SinalPulso

# Largura em torno da fundamental considerada "o pico", em Hz. Mesmo valor que
# a relação sinal-ruído do módulo de espectro usa, de propósito: duas
# definições diferentes de pico no mesmo sistema é fonte de confusão garantida.
LARGURA_DO_PICO_HZ = 0.1

# Número de subjanelas para medir se o pico fica parado. Quatro é o maior valor
# que ainda deixa cada subjanela com resolução espectral suficiente numa janela
# de 10 segundos: 2,5 s dão 0,4 Hz de resolução bruta, que o zero-padding
# refina. Com oito, a subjanela fica curta demais e a dispersão medida vira
# ruído de estimação em vez de instabilidade do sinal.
SUBJANELAS = 4


@dataclass(frozen=True, slots=True)
class Caracteristicas:
    """Descrição de uma janela, toda ela disponível em tempo de execução."""

    snr_db: float
    """Relação sinal-ruído do espectro, em decibéis."""

    proeminencia: float
    """Logaritmo da potência do pico dividida pela mediana da banda.

    Em logaritmo porque a razão crua varia por cinco ordens de grandeza entre
    uma janela de parede lisa e uma de pulso forte: medido, o desvio da coluna
    deu 376 mil. Padronizar isso faz a média e o desvio serem ditados por dois
    ou três valores extremos, e o resto das janelas colapsa num ponto só.
    Decibel seria equivalente; `log1p` evita o caso de razão zero.
    """

    entropia_espectral: float
    """Entropia de Shannon do espectro normalizado, dividida pelo máximo
    possível. Vai de 0, toda energia num bin só, a 1, espectro plano. Pega um
    caso que a relação sinal-ruído não pega: espectro com dois picos iguais,
    em que há sinal forte e nenhuma frequência confiável."""

    razao_harmonica: float
    """Energia perto de 2f dividida pela energia perto de f. Pulso de verdade
    tem harmônico, porque a onda sobe rápido e desce devagar; interferência
    senoidal de luz não tem. É a característica que separa os dois casos em que
    o ICA erra."""

    dispersao_do_pico_bpm: float
    """Desvio padrão da frequência de pico entre subjanelas. Um pico firme é
    sinal; um que passeia é artefato que por acaso teve energia."""

    fracao_de_pele: float
    """Fração dos pixels da região que a máscara aceitou como pele."""

    fracao_saturada: float
    """Fração de pixels em 0 ou 255. Pixel saturado não carrega pulso: a
    informação foi cortada antes de virar número."""

    deslocamento_roi: float
    """Desvio padrão da posição da região ao longo da janela, em fração da
    largura do quadro. É o indicador de movimento."""

    correlacao_com_fundo: float
    """Correlação absoluta entre o sinal do rosto e o do fundo. O fundo não tem
    pulso: o que for comum aos dois é iluminação."""

    jitter_temporal: float
    """Desvio padrão do intervalo entre quadros, dividido pelo intervalo médio."""

    desvio_cromatico: float
    """Quanto a direção da variação RGB foge da direção esperada do pulso.

    Zero quer dizer que a oscilação dominante aponta exatamente para onde o
    sangue a empurraria; um, que aponta para o lado oposto. É a característica
    que ataca o mecanismo da hipótese H1 de frente, em vez de atacar o sintoma.

    O raciocínio é físico. O pulso modula os canais na proporção em que a
    hemoglobina absorve, que é muito mais no verde que no vermelho. A reflexão
    especular modula os três na cor do iluminante, dividida pela intensidade
    média de cada canal. São duas direções diferentes no espaço de cor, e uma
    janela dominada por iluminação aponta para a segunda.

    Duas tentativas anteriores foram medidas e descartadas, e vale registrar
    porque as duas pareciam boas no papel. A **razão harmônica** não sustentou o
    próprio peso: o espectro chega recortado na banda cardíaca, então acima de
    120 bpm o primeiro harmônico cai fora e a característica deixa de ser
    observável justo onde seria útil. A **assimetria da onda** deu exatamente
    zero para pulso e para senoide, porque o gerador sintético soma os
    harmônicos todos com a mesma fase e a onda dele é simétrica; em dado real
    ela voltaria a fazer sentido, e é por isso que está anotada aqui em vez de
    esquecida.
    """

    @classmethod
    def nomes(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))

    def vetor(self) -> np.ndarray:
        return np.array(astuple(self), dtype=float)


def _banda_em_torno(frequencias: np.ndarray, centro: float, largura: float) -> np.ndarray:
    return np.abs(frequencias - centro) <= largura


def entropia_espectral(potencias: np.ndarray) -> float:
    """Entropia de Shannon normalizada do espectro.

    Normalizar pelo logaritmo do número de bins é o que torna o número
    comparável entre janelas de comprimento diferente. Sem isso, janela mais
    longa daria entropia maior só por ter mais bins, e o modelo aprenderia a
    ler comprimento de janela em vez de qualidade.
    """
    p = np.asarray(potencias, dtype=float)
    p = p[np.isfinite(p)]
    if p.size < 2:
        return 1.0

    total = float(np.sum(p[p > 0]))
    if total <= 0:
        # Sem energia nenhuma não há distribuição. Devolver 1,0 é a escolha
        # conservadora: o modelo lê como "espectro sem estrutura", que é o que
        # de fato se sabe.
        return 1.0

    # A soma percorre só os bins positivos, pela convenção 0·log0 = 0, mas a
    # normalização usa o número TOTAL de bins. Normalizar pelo número de bins
    # positivos foi a primeira versão e invertia o resultado no caso que mais
    # importa: espectro com toda a energia num bin só tem um bin positivo,
    # caía no guarda de tamanho e devolvia 1,0, que é "espalhado", quando a
    # resposta certa é 0,0, "concentrado". Um teste pegou.
    positivos = p[p > 0]
    distribuicao = positivos / total
    entropia = -float(np.sum(distribuicao * np.log(distribuicao)))
    return float(entropia / np.log(p.size))


def razao_harmonica(
    frequencias: np.ndarray,
    potencias: np.ndarray,
    frequencia_hz: float,
    largura_hz: float = LARGURA_DO_PICO_HZ,
) -> float:
    """Energia no primeiro harmônico contra energia na fundamental.

    Devolve 0 quando o harmônico cai fora do espectro disponível, que é o caso
    de frequência alta com banda curta. Zero aqui quer dizer "não observável",
    e não "não tem harmônico" — a distinção some no número, e é por isso que
    esta característica nunca deve ser lida sozinha.
    """
    f = np.asarray(frequencias, dtype=float)
    p = np.asarray(potencias, dtype=float)
    if f.size == 0:
        return 0.0
    fundamental = _banda_em_torno(f, frequencia_hz, largura_hz)
    harmonico = _banda_em_torno(f, 2.0 * frequencia_hz, 2.0 * largura_hz)
    energia_fundamental = float(np.sum(p[fundamental]))
    if energia_fundamental <= 1e-20:
        return 0.0
    return float(np.sum(p[harmonico]) / energia_fundamental)


def proeminencia(potencias: np.ndarray) -> float:
    """Pico dividido pela mediana da banda.

    A mediana, e não a média: a média já contém o próprio pico e encolhe o
    número justamente quando o pico é alto, que é quando ele deveria crescer.
    """
    p = np.asarray(potencias, dtype=float)
    p = p[np.isfinite(p)]
    if p.size == 0:
        return 0.0
    mediana = float(np.median(p))
    if mediana <= 1e-20:
        return 0.0
    return float(np.log1p(np.max(p) / mediana))


def dispersao_do_pico(
    pulso: SinalPulso,
    subjanelas: int = SUBJANELAS,
) -> float:
    """Desvio padrão da frequência de pico entre pedaços da janela.

    Mede coerência temporal, que o espectro da janela inteira apaga: um sinal
    que é 60 bpm na primeira metade e 90 na segunda produz um espectro com dois
    picos e uma estimativa qualquer entre eles, sem nada que denuncie o
    problema. Aqui ele aparece como dispersão alta.
    """
    # Importação local: `analisar` vive em sinais.espectro, que não depende
    # deste módulo. Importar no topo criaria um ciclo quando o pipeline passar
    # a usar qualidade.
    from cardiocam.dominio.resultado import Ok
    from cardiocam.sinais.espectro import analisar

    if subjanelas < 2:
        raise ValueError("Precisa de ao menos duas subjanelas para medir dispersão.")
    tamanho = len(pulso) // subjanelas
    if tamanho < 8:
        return float("nan")

    frequencias: list[float] = []
    for i in range(subjanelas):
        pedaco = pulso.amostras[i * tamanho : (i + 1) * tamanho]
        resultado = analisar(SinalPulso(pedaco, pulso.fps, pulso.origem))
        if isinstance(resultado, Ok):
            frequencias.append(resultado.valor.bpm)

    if len(frequencias) < 2:
        return float("nan")
    return float(np.std(frequencias))


def correlacao(a: np.ndarray, b: np.ndarray) -> float:
    """Correlação de Pearson em módulo, tolerante a sinal constante.

    Devolve 0 quando um dos dois não varia. Constante não tem correlação
    definida, e `np.corrcoef` devolveria `nan` com um aviso; aqui o caso vira
    "sem evidência de acoplamento", que é a leitura correta para esta
    característica.
    """
    x = np.asarray(a, dtype=float).ravel()
    y = np.asarray(b, dtype=float).ravel()
    if x.size != y.size or x.size < 2:
        return 0.0
    if float(np.std(x)) < 1e-12 or float(np.std(y)) < 1e-12:
        return 0.0
    return float(abs(np.corrcoef(x, y)[0, 1]))


# Direção esperada da modulação do pulso nos canais, na ordem vermelho, verde,
# azul. São os mesmos ganhos que o simulador usa, e vêm de onde a hemoglobina
# absorve: muito no verde, pouco no vermelho. Repetir o número aqui seria pedir
# para os dois divergirem, então ele é importado.
def _direcao_do_pulso() -> np.ndarray:
    from cardiocam.fontes.sintetica import GANHO_CANAL

    direcao = np.array(
        [GANHO_CANAL["vermelho"], GANHO_CANAL["verde"], GANHO_CANAL["azul"]],
        dtype=float,
    )
    return direcao / np.linalg.norm(direcao)


def desvio_cromatico(serie_rgb: np.ndarray) -> float:
    """Distância angular entre a oscilação dominante e a direção do pulso.

    Recebe uma matriz 3xN na ordem vermelho, verde, azul. Cada canal é dividido
    pela própria média antes de qualquer coisa: é essa normalização que põe os
    três na mesma escala relativa e torna a direção comparável, e é também o
    primeiro passo do CHROM e do POS, o que mantém a característica no mesmo
    espaço em que os algoritmos trabalham.

    A direção dominante sai do maior autovetor da covariância. O sinal dele é
    arbitrário, então a comparação usa o cosseno em módulo: inverter a
    polaridade não muda em que eixo a energia está.

    Devolve 0 quando não há variação para medir, que é "sem evidência de
    desvio" e não "perfeitamente alinhado". A distinção importa, e some no
    número; por isso está escrita.
    """
    m = np.asarray(serie_rgb, dtype=float)
    if m.ndim != 2 or m.shape[0] != 3 or m.shape[1] < 3:
        return 0.0

    medias = np.mean(m, axis=1, keepdims=True)
    if np.any(np.abs(medias) < 1e-12):
        return 0.0
    normalizada = m / medias
    centrada = normalizada - np.mean(normalizada, axis=1, keepdims=True)
    if float(np.max(np.std(centrada, axis=1))) < 1e-12:
        return 0.0

    covariancia = np.cov(centrada)
    valores, vetores = np.linalg.eigh(covariancia)
    dominante = vetores[:, int(np.argmax(valores))]
    norma = float(np.linalg.norm(dominante))
    if norma < 1e-12:
        return 0.0

    cosseno = float(abs(np.dot(dominante / norma, _direcao_do_pulso())))
    return float(1.0 - min(1.0, cosseno))


def extrair(
    pulso: SinalPulso,
    espectro: Espectro,
    frequencia_hz: float,
    snr_db: float,
    *,
    fracao_de_pele: float = 1.0,
    fracao_saturada: float = 0.0,
    posicoes_roi: np.ndarray | None = None,
    sinal_do_fundo: np.ndarray | None = None,
    instantes: np.ndarray | None = None,
    serie_rgb: np.ndarray | None = None,
) -> Caracteristicas:
    """Monta o vetor de uma janela.

    O contexto é opcional e cada ausência tem um valor neutro declarado, não um
    zero conveniente. Isso é deliberado: o pipeline em modo simples não tem
    fundo nem rastreador, e a alternativa seria um vetor de tamanho variável,
    que quebraria o modelo em silêncio. Neutro e documentado é pior que medido
    e melhor que ausente.

    `snr_db` chega pronto de fora porque quem calcula é o módulo de espectro, e
    recalcular aqui abriria a porta para duas definições divergirem.
    """
    # O infinito negativo aparece quando não há energia nenhuma na banda. Como
    # valor de entrada de um modelo linear ele envenena todo o ajuste, então
    # vira um piso. 60 dB abaixo é mais do que qualquer medição real alcança.
    snr = float(snr_db) if np.isfinite(snr_db) else -60.0

    return Caracteristicas(
        snr_db=snr,
        proeminencia=proeminencia(espectro.potencias),
        entropia_espectral=entropia_espectral(espectro.potencias),
        razao_harmonica=razao_harmonica(
            espectro.frequencias_hz, espectro.potencias, frequencia_hz
        ),
        dispersao_do_pico_bpm=dispersao_do_pico(pulso),
        fracao_de_pele=float(fracao_de_pele),
        fracao_saturada=float(fracao_saturada),
        deslocamento_roi=(
            float(np.std(np.asarray(posicoes_roi, dtype=float)))
            if posicoes_roi is not None and np.asarray(posicoes_roi).size >= 2
            else 0.0
        ),
        correlacao_com_fundo=(
            correlacao(pulso.amostras, sinal_do_fundo)
            if sinal_do_fundo is not None
            else 0.0
        ),
        jitter_temporal=_jitter(instantes),
        desvio_cromatico=(
            desvio_cromatico(serie_rgb) if serie_rgb is not None else 0.0
        ),
    )


def _jitter(instantes: np.ndarray | None) -> float:
    if instantes is None:
        return 0.0
    t = np.asarray(instantes, dtype=float).ravel()
    if t.size < 3:
        return 0.0
    intervalos = np.diff(t)
    medio = float(np.mean(intervalos))
    if medio <= 1e-12:
        return 0.0
    return float(np.std(intervalos) / medio)


@dataclass(frozen=True, slots=True)
class Padronizador:
    """Média e desvio por característica, aprendidos no treino.

    Padronizar não é cosmético aqui. A priori do modelo bayesiano é a mesma
    para todos os pesos, e isso só é uma hipótese razoável se as
    características estiverem na mesma escala. Sem padronizar, `snr_db` na casa
    das dezenas e `fracao_saturada` na casa dos milésimos recebem a mesma
    regularização, e a segunda é esmagada por um motivo que não tem nada a ver
    com o quanto ela informa.

    Os parâmetros vêm **só do treino** e são aplicados ao teste. Ajustar no
    conjunto inteiro vaza a distribuição do teste para dentro do modelo; é um
    vazamento pequeno e é vazamento.
    """

    media: np.ndarray
    desvio: np.ndarray
    nomes: tuple[str, ...]

    @classmethod
    def ajustar(cls, matriz: np.ndarray, nomes: tuple[str, ...]) -> "Padronizador":
        m = np.asarray(matriz, dtype=float)
        if m.ndim != 2:
            raise ValueError("A matriz precisa ser bidimensional.")
        media = np.nanmean(m, axis=0)
        desvio = np.nanstd(m, axis=0)
        # Característica constante no treino: desvio 1 em vez de 0. Dividir por
        # zero produziria nan, e a coluna vira zero depois de subtrair a média,
        # que é o comportamento correto: ela não informa nada.
        desvio = np.where(desvio < 1e-12, 1.0, desvio)
        return cls(media=media, desvio=desvio, nomes=tuple(nomes))

    def aplicar(self, matriz: np.ndarray) -> np.ndarray:
        m = np.asarray(matriz, dtype=float)
        padronizada = (m - self.media) / self.desvio
        # `nan` aparece quando a dispersão do pico não pôde ser medida por
        # janela curta. Vira zero, que depois de padronizar é "a média do
        # treino": a leitura correta de ausência é "nada de anormal observado",
        # e não "valor extremo".
        return np.nan_to_num(padronizada, nan=0.0, posinf=0.0, neginf=0.0)
