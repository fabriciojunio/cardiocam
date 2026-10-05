/**
 * Pipeline de medição: do quadro de vídeo ao número.
 *
 * Diferença deliberada em relação à versão em Python: aqui não há detecção
 * automática de rosto. A cascata de Haar não existe no navegador, e trazer um
 * modelo de rede neural custaria alguns megabytes de download.
 *
 * A saída foi pedir que a pessoa encaixe o rosto num contorno na tela. Parece
 * um retrocesso e não é: com o rosto ancorado num lugar fixo, a região medida
 * para de tremer entre quadros, e esse tremor é justamente o que mais estraga
 * a medição na versão automática. Quem posiciona o rosto está, de graça,
 * fazendo o trabalho do estabilizador.
 */

import {
  desvioPadrao,
  espectroPotencia,
  estimarFrequencia,
  media,
  passaFaixa,
  refinarPico,
  relacaoSinalRuido,
  removerReferencia,
} from './dsp.js';

/**
 * Filtragem do sinal do dedo. O sinal é forte o bastante para dispensar
 * qualquer combinação de canais; basta tirar a tendência e a banda.
 */
function passaFaixaDedo(canal, fps) {
  return passaFaixa(canal.map((x) => -x), fps, BANDA.minHz, BANDA.maxHz);
}
import { classificarPele, construirSelecao, mediaDaPele, mediaPorSelecao } from './pele.js';
import { extrairPulso } from './rppg.js';

export const BANDA = { minHz: 0.75, maxHz: 3.3 };

/**
 * Peso do espectro novo na média corrida de espectros.
 *
 * Promediar o espectro de janelas sucessivas, em vez de estimar cada janela
 * isoladamente e suavizar o número, é a técnica de Welch (1967): a variância do
 * espectro estimado cai com o número de segmentos promediados. Duas
 * consequências, e as duas foram medidas aqui:
 *
 * - o número exibido **varia menos**, porque a estimativa vem de um espectro
 *   menos ruidoso e não de uma média de estimativas ruidosas;
 * - o pico do pulso **emerge em condição pior**, o que é o mesmo que dizer que
 *   funciona com menos luz.
 *
 * O valor de 0,15 saiu de medição, e não de palpite. Somar os espectros sem
 * esquecer nada dá a média da sessão inteira: ficou com o menor desvio antes de
 * uma mudança de frequência, e **60 segundos** para acompanhar uma mudança de
 * 60 para 90 bpm, com 5,4 bpm de dispersão depois dela. Inutilizável.
 *
 * Com esquecimento, comparado à média exponencial que havia antes:
 *
 * | estratégia        | desvio antes | desvio depois | tempo para acompanhar |
 * | ----------------- | -----------: | ------------: | --------------------: |
 * | exponencial 0,30  |        0,036 |         0,042 |                  19 s |
 * | **espectro 0,15** |    **0,030** |     **0,031** |              **17 s** |
 * | espectro 0,25     |        0,034 |         0,041 |                  15 s |
 * | espectro 0,40     |        0,038 |         0,049 |                  14 s |
 *
 * 0,15 é o único que ganha da exponencial **nos dois eixos ao mesmo tempo**:
 * mais estável e mais rápido para acompanhar. Em sinal mais fraco a vantagem
 * cresce: com amplitude de 0,2% o desvio do número caiu pela metade.
 */
const PESO_DO_ESPECTRO_NOVO = 0.15;
export const BPM_MINIMO = BANDA.minHz * 60;
export const BPM_MAXIMO = BANDA.maxHz * 60;

/**
 * Onde o contorno desenhado na tela fica dentro do quadro. É a caixa que o
 * rosto deve preencher, e faz o papel que a cascata de Haar faz na versão em
 * Python: definir a referência a partir da qual as sub-regiões são calculadas.
 */
export const CAIXA_ROSTO = { x: 0.27, y: 0.12, largura: 0.46, altura: 0.76 };

/**
 * Testa e bochechas, em frações da caixa do rosto. São as mesmas proporções da
 * versão em Python, então as duas implementações medem a mesma coisa.
 *
 * Boca e olhos ficam de fora de propósito: piscar e falar produzem movimento
 * exatamente na banda de frequência do coração, e esse é o tipo de artefato que
 * nenhuma filtragem posterior remove.
 */
export const REGIOES_NA_CAIXA = [
  { x: 0.24, y: 0.12, largura: 0.52, altura: 0.20 },
  { x: 0.08, y: 0.50, largura: 0.30, altura: 0.30 },
  { x: 0.62, y: 0.50, largura: 0.30, altura: 0.30 },
];

/** Regiões já convertidas para frações do quadro inteiro. */
export const REGIOES = REGIOES_NA_CAIXA.map((r) => ({
  x: CAIXA_ROSTO.x + r.x * CAIXA_ROSTO.largura,
  y: CAIXA_ROSTO.y + r.y * CAIXA_ROSTO.altura,
  largura: r.largura * CAIXA_ROSTO.largura,
  altura: r.altura * CAIXA_ROSTO.altura,
}));

/**
 * Faixas laterais usadas como referência de iluminação. Ficam fora da caixa do
 * rosto, então não têm pulso: o que oscila nelas é a luz do ambiente ou o ganho
 * da câmera se ajustando.
 */
/*
  As faixas laterais fixas que ficavam aqui foram removidas.

  Elas eram a referência de iluminação de quando o rosto estava sempre no meio
  do quadro, preso num contorno. Com o rosto rastreado, a referência passou a
  ser o quadro inteiro menos a caixa do rosto, que dá milhares de pixels em
  qualquer enquadramento. Ver `medirFundo`.
*/

/**
 * Média RGB do fundo: tudo que não é o rosto e não parece pele.
 *
 * ## Por que o quadro inteiro, e não duas faixas laterais
 *
 * A versão anterior media duas faixas fixas nas bordas, e devolvia `null` com
 * menos de 100 pixels úteis. Isso se tornou frágil quando o rosto passou a ser
 * rastreado: as faixas que não encostam no rosto são escolhidas conforme a
 * posição dele, e com o rosto perto de uma borda sobrava faixa pequena ou
 * nenhuma.
 *
 * E o preço de um `null` é desproporcional. A rectificação exige fundo em
 * **todas** as amostras da janela, porque interpolar buraco na referência
 * introduziria justamente o artefato lento que ela existe para remover. Com
 * janela de 25 segundos a 60 quadros, **um único quadro sem fundo descarta a
 * correção de 1.500 quadros**, e em silêncio.
 *
 * Isso importa muito aqui. Medido na câmera do usuário, o ruído dominante não é
 * do sensor: com a captura em 1080p reduzida para 320, o ruído de leitura já
 * está dividido por mais de duzentos, e ainda assim a relação sinal-ruído fica
 * perto de zero. O que sobra é ruído **correlacionado**, e a maior fonte dele é
 * o controle automático da câmera, que nem sempre dá para travar. A
 * rectificação por fundo é precisamente o que cobre esse caso, então deixá-la
 * cair em silêncio é perder a defesa principal.
 *
 * Usar o quadro inteiro menos o rosto dá milhares de pixels em qualquer
 * enquadramento, e torna o `null` praticamente impossível.
 *
 * `caixaRosto` é excluída com margem, porque a borda do rosto tem pele que a
 * classificação por cor deixa passar, e pele tem pulso: contaminar a referência
 * com pulso faria a correção remover justamente o que se quer medir.
 */
export function medirFundo(contexto, largura, altura, passo = 4, caixaRosto = null) {
  let somaR = 0;
  let somaG = 0;
  let somaB = 0;
  let usados = 0;

  // Retângulo do rosto a excluir, com 15% de margem em cada lado.
  let ex0 = -1;
  let ey0 = -1;
  let ex1 = -1;
  let ey1 = -1;
  if (caixaRosto) {
    const mx = caixaRosto.largura * 0.15;
    const my = caixaRosto.altura * 0.15;
    ex0 = Math.floor((caixaRosto.x - mx) * largura);
    ey0 = Math.floor((caixaRosto.y - my) * altura);
    ex1 = Math.ceil((caixaRosto.x + caixaRosto.largura + mx) * largura);
    ey1 = Math.ceil((caixaRosto.y + caixaRosto.altura + my) * altura);
  }

  const dados = contexto.getImageData(0, 0, largura, altura).data;

  for (let y = 0; y < altura; y += passo) {
    const dentroVertical = y >= ey0 && y < ey1;
    for (let x = 0; x < largura; x += passo) {
      if (dentroVertical && x >= ex0 && x < ex1) continue;

      const i = (y * largura + x) * 4;
      const r = dados[i];
      const g = dados[i + 1];
      const b = dados[i + 2];
      // Pele fora da caixa do rosto é pescoço, mão ou outra pessoa, e tem
      // pulso. Entra como contaminação, não como referência.
      if (classificarPele(r, g, b)) continue;
      somaR += r;
      somaG += g;
      somaB += b;
      usados++;
    }
  }

  if (usados < 100) return null;
  return { vermelho: somaR / usados, verde: somaG / usados, azul: somaB / usados };
}

/**
 * Retira de cada canal do rosto a parte explicável pelo mesmo canal do fundo.
 * A média original é reposta porque os algoritmos cromáticos normalizam pela
 * média temporal e precisam do nível de partida.
 */
export function rectificarPeloFundo(serie, fundo) {
  if (!fundo || !fundo.verde || fundo.verde.length !== serie.verde.length) return serie;
  const limpar = (canal, referencia) => {
    const m = media(canal);
    return removerReferencia(canal, referencia).map((x) => x + m);
  };
  return {
    vermelho: limpar(serie.vermelho, fundo.vermelho),
    verde: limpar(serie.verde, fundo.verde),
    azul: limpar(serie.azul, fundo.azul),
  };
}

/**
 * Região central usada no modo dedo. O dedo encostado cobre a lente inteira,
 * então basta evitar as bordas, onde entra luz que vazou por fora.
 */
export const REGIAO_DEDO = { x: 0.3, y: 0.3, largura: 0.4, altura: 0.4 };

/**
 * Média dos canais no modo dedo, sem classificar pele.
 *
 * Com o dedo sobre a lente e a lanterna acesa, a imagem inteira é tecido
 * iluminado por transiluminação, e o classificador de pele não serve: a cor
 * fica vermelha saturada, fora da faixa de crominância de pele vista à luz
 * ambiente. Medir tudo é o certo aqui.
 *
 * Também informa se o dedo está bem posicionado. Cobertura ruim deixa entrar
 * luz do ambiente pela borda, e aí o que se mede é a luz da sala e não o
 * sangue.
 */
export function medirDedo(contexto, largura, altura, passo = 4) {
  const rx = Math.round(REGIAO_DEDO.x * largura);
  const ry = Math.round(REGIAO_DEDO.y * altura);
  const rl = Math.max(1, Math.round(REGIAO_DEDO.largura * largura));
  const ra = Math.max(1, Math.round(REGIAO_DEDO.altura * altura));
  const dados = contexto.getImageData(rx, ry, rl, ra).data;

  let somaR = 0;
  let somaG = 0;
  let somaB = 0;
  let n = 0;
  for (let y = 0; y < ra; y += passo) {
    for (let x = 0; x < rl; x += passo) {
      const i = (y * rl + x) * 4;
      somaR += dados[i];
      somaG += dados[i + 1];
      somaB += dados[i + 2];
      n++;
    }
  }
  if (!n) return null;

  const vermelho = somaR / n;
  const verde = somaG / n;
  const azul = somaB / n;

  // O dedo iluminado por trás fica muito mais vermelho que verde e azul.
  // Sem essa dominância, não há dedo cobrindo a lente.
  const cobreALente = vermelho > 60 && vermelho > 1.6 * verde && vermelho > 1.6 * azul;
  return { vermelho, verde, azul, pixels: n, cobreALente };
}

export class Medidor {
  /**
   * @param {object} opcoes
   * @param {number} opcoes.janelaS  segundos acumulados antes de estimar
   * @param {string} opcoes.algoritmo  pos, chrom ou verde
   */
  constructor({ janelaS = 15, algoritmo = 'pos', usarFundo = true, modo = 'rosto' } = {}) {
    this.janelaS = janelaS;
    this.algoritmo = algoritmo;
    this.usarFundo = usarFundo;
    this.modo = modo;
    this.reiniciar();
  }

  reiniciar() {
    this.amostras = [];
    this.ultimaAnalise = null;
    this.bpmSuavizado = null;
    this.historico = [];
    this.quadrosSemPele = 0;
    this.inicio = null;
    this.espectroMedio = null;
    this.frequenciasDoEspectro = null;
    this.quadrosSemFundo = 0;
  }

  get duracaoAcumulada() {
    if (this.amostras.length < 2) return 0;
    return this.amostras[this.amostras.length - 1].t - this.amostras[0].t;
  }

  /**
   * Luminância média da pele medida, de 0 a 255.
   *
   * Serve para a interface avisar quando a imagem está escura demais para a
   * medição ter chance. Não é estética: a variação que carrega o pulso é de
   * 0,1% a 1% da intensidade, então numa região com luminância 20 o pulso vale
   * entre 0,02 e 0,2 níveis, e o sensor quantiza em números inteiros. O sinal
   * fica abaixo do passo de quantização, e só sobrevive porque a média
   * espacial sobre milhares de pixels recupera parte dele. Dobrar a
   * luminância dobra o sinal antes de qualquer processamento, e é a
   * providência mais eficaz que existe do lado de quem mede.
   *
   * Usa os coeficientes de luminância da recomendação BT.601, que são os
   * mesmos usados na conversão para YCrCb da segmentação de pele.
   */
  get luminanciaMedia() {
    if (this.amostras.length === 0) return NaN;
    let soma = 0;
    for (const a of this.amostras) {
      soma += 0.299 * a.r + 0.587 * a.g + 0.114 * a.b;
    }
    return soma / this.amostras.length;
  }

  get progresso() {
    return Math.min(1, this.duracaoAcumulada / this.janelaS);
  }

  /** Taxa real de quadros, medida pelos carimbos de tempo e não pela nominal. */
  get fpsEfetivo() {
    if (this.amostras.length < 10) return 30;
    const intervalos = [];
    for (let i = 1; i < this.amostras.length; i++) {
      const d = this.amostras[i].t - this.amostras[i - 1].t;
      if (d > 0) intervalos.push(d);
    }
    if (!intervalos.length) return 30;
    intervalos.sort((a, b) => a - b);
    const mediana = intervalos[Math.floor(intervalos.length / 2)];
    return mediana > 0 ? 1 / mediana : 30;
  }

  /**
   * Consome um quadro já desenhado num canvas.
   *
   * `regioes` e `faixasDeFundo` são opcionais e, quando omitidos, caem nas
   * constantes do contorno fixo. É assim que as duas formas de medir convivem
   * no mesmo medidor: com o rastreador de rosto ligado, quem chama passa as
   * regiões ancoradas nos olhos e elas acompanham a pessoa; sem ele, valem as
   * posições fixas e a pessoa é que se encaixa no contorno.
   *
   * O padrão continua sendo o fixo de propósito. Assim o medidor não depende
   * de rede nem de modelo baixado para funcionar, e o modo automático é um
   * acréscimo em cima de algo que já funciona sozinho.
   *
   * @returns {object} estado para a interface
   */
  processarQuadro(
    contexto,
    largura,
    altura,
    instanteS,
    regioes = REGIOES,
    caixaRosto = null,
  ) {
    if (this.inicio === null) this.inicio = instanteS;

    if (this.modo === 'dedo') return this._processarDedo(contexto, largura, altura, instanteS);

    let somaR = 0;
    let somaG = 0;
    let somaB = 0;
    let pesoTotal = 0;
    let proporcaoPele = 0;

    for (const regiao of regioes) {
      const rx = Math.round(regiao.x * largura);
      const ry = Math.round(regiao.y * altura);
      const rl = Math.max(1, Math.round(regiao.largura * largura));
      const ra = Math.max(1, Math.round(regiao.altura * altura));
      if (rx + rl > largura || ry + ra > altura) continue;

      const dados = contexto.getImageData(rx, ry, rl, ra).data;
      const medida = mediaDaPele(dados, rl, ra, 2);
      if (!medida) continue;

      somaR += medida.vermelho * medida.pixels;
      somaG += medida.verde * medida.pixels;
      somaB += medida.azul * medida.pixels;
      pesoTotal += medida.pixels;
      proporcaoPele = Math.max(proporcaoPele, medida.proporcao);
    }

    if (!pesoTotal) {
      this.quadrosSemPele++;
      // Uma ausência breve não invalida o que já foi acumulado: a pessoa pode
      // ter piscado ou virado de leve. Só descartamos depois de insistir.
      if (this.quadrosSemPele > 45) {
        this.amostras = [];
        this.bpmSuavizado = null;
        this.ultimaAnalise = null;
      }
      // A mensagem depende de quem escolheu a região: no modo automático pedir
      // para "encaixar no contorno" confunde, porque não há contorno na tela.
      const automatico = regioes !== REGIOES;
      return {
        temPele: false,
        mensagem: automatico
          ? 'Rosto não localizado. Olhe para a câmera.'
          : 'Encaixe o rosto no contorno.',
        progresso: this.progresso,
      };
    }

    this.quadrosSemPele = 0;
    const fundo = this.usarFundo
      ? medirFundo(contexto, largura, altura, 4, caixaRosto)
      : null;
    if (!fundo) this.quadrosSemFundo += 1;
    this.amostras.push({
      t: instanteS,
      r: somaR / pesoTotal,
      g: somaG / pesoTotal,
      b: somaB / pesoTotal,
      fundo,
    });

    // Mantém só o necessário para a janela, com folga.
    const limite = this.janelaS * 1.3;
    while (this.amostras.length > 2 && instanteS - this.amostras[0].t > limite) {
      this.amostras.shift();
    }

    return {
      temPele: true,
      proporcaoPele,
      progresso: this.progresso,
      mensagem: this.progresso < 1
        ? `Coletando sinal, faltam ${Math.ceil(this.janelaS - this.duracaoAcumulada)} s.`
        : 'Medindo.',
    };
  }

  _processarDedo(contexto, largura, altura, instanteS) {
    const medida = medirDedo(contexto, largura, altura);

    if (!medida || !medida.cobreALente) {
      this.quadrosSemPele++;
      if (this.quadrosSemPele > 45) {
        this.amostras = [];
        this.bpmSuavizado = null;
        this.ultimaAnalise = null;
      }
      return {
        temPele: false,
        progresso: this.progresso,
        mensagem: 'Cubra a lente com a ponta do dedo, sem apertar.',
      };
    }

    this.quadrosSemPele = 0;
    this.amostras.push({
      t: instanteS,
      r: medida.vermelho,
      g: medida.verde,
      b: medida.azul,
      fundo: null,
    });

    const limite = this.janelaS * 1.3;
    while (this.amostras.length > 2 && instanteS - this.amostras[0].t > limite) {
      this.amostras.shift();
    }

    return {
      temPele: true,
      progresso: this.progresso,
      mensagem: this.progresso < 1
        ? `Segure assim, faltam ${Math.ceil(this.janelaS - this.duracaoAcumulada)} s.`
        : 'Medindo.',
    };
  }

  /** Roda a análise sobre o que já foi acumulado. Devolve null se não der. */
  analisar() {
    if (this.progresso < 1 || this.amostras.length < 64) return null;

    const fps = this.fpsEfetivo;
    let serie = {
      vermelho: this.amostras.map((a) => a.r),
      verde: this.amostras.map((a) => a.g),
      azul: this.amostras.map((a) => a.b),
    };

    if (desvioPadrao(serie.verde) < 1e-6) return null;

    // No modo dedo o algoritmo é sempre o do canal verde. Os métodos
    // cromáticos existem para separar pulso de variação de iluminação, e aqui
    // não há iluminação ambiente para separar: a lanterna é fixa e o dedo tapa
    // a lente. Combinar canais só acrescentaria o ruído do vermelho, que está
    // saturado, e do azul, que quase não recebe luz através do tecido.
    if (this.modo === 'dedo') {
      const pulso = passaFaixaDedo(serie.verde, fps);
      const resultado = estimarFrequencia(pulso, fps, BANDA.minHz, BANDA.maxHz);
      if (!resultado) return null;
      this.bpmSuavizado = this.bpmSuavizado === null
        ? resultado.bpm
        : 0.7 * this.bpmSuavizado + 0.3 * resultado.bpm;
      this.historico.push(resultado.bpm);
      if (this.historico.length > 60) this.historico.shift();
      this.ultimaAnalise = {
        ...resultado,
        bpmExibido: this.bpmSuavizado,
        pulso,
        fps,
        duracaoS: this.duracaoAcumulada,
        janelas: this.historico.length,
      };
      return this.ultimaAnalise;
    }

    // A rectificação vem antes do algoritmo de propósito: o balanço de branco
    // automático age sobre cada canal separadamente, então é aí que a correção
    // pertence. Depois da combinação cromática já não há como desfazer.
    // A rectificação exige fundo em **todas** as amostras da janela, porque
    // interpolar buraco na referência introduziria o artefato lento que ela
    // existe para remover. O custo de um buraco é alto, e por isso o resultado
    // passou a dizer se ela foi aplicada: antes, uma janela sem correção era
    // indistinguível de uma com, e a diferença entre as duas foi medida em
    // 1 acerto em 16 contra 16 em 16 sob balanço de branco oscilante.
    this.fundoAplicado = this.usarFundo && this.amostras.every((a) => a.fundo);
    if (this.fundoAplicado) {
      serie = rectificarPeloFundo(serie, {
        vermelho: this.amostras.map((a) => a.fundo.vermelho),
        verde: this.amostras.map((a) => a.fundo.verde),
        azul: this.amostras.map((a) => a.fundo.azul),
      });
    }

    const pulso = extrairPulso(serie, fps, this.algoritmo, BANDA.minHz, BANDA.maxHz);
    const resultado = estimarFrequencia(pulso, fps, BANDA.minHz, BANDA.maxHz);
    if (!resultado) return null;

    // O número exibido vem do espectro médio, não de suavizar estimativas. A
    // diferença está documentada em PESO_DO_ESPECTRO_NOVO, com os números.
    const doEspectroMedio = this._acumularEspectro(pulso, fps);

    // O histórico guarda a estimativa **por janela**, crua. É de propósito: a
    // dispersão entre janelas é um indicador de qualidade, e calculá-la sobre
    // valores já suavizados daria uma estabilidade que não existe.
    this.historico.push(resultado.bpm);
    if (this.historico.length > 60) this.historico.shift();

    this.bpmSuavizado = doEspectroMedio ? doEspectroMedio.bpm : resultado.bpm;

    this.ultimaAnalise = {
      ...resultado,
      // A relação sinal-ruído do espectro médio é a honesta para exibir: é a do
      // espectro de que o número saiu.
      snrDb: doEspectroMedio ? doEspectroMedio.snrDb : resultado.snrDb,
      snrDaJanela: resultado.snrDb,
      bpmExibido: this.bpmSuavizado,
      pulso,
      fps,
      duracaoS: this.duracaoAcumulada,
      janelas: this.historico.length,
      fundoAplicado: this.fundoAplicado,
      quadrosSemFundo: this.quadrosSemFundo,
    };
    return this.ultimaAnalise;
  }

  /**
   * Acumula o espectro desta janela no espectro médio e estima a partir dele.
   *
   * Devolve `null` enquanto não houver espectro utilizável, e nesse caso quem
   * chama cai na estimativa da janela isolada.
   */
  _acumularEspectro(pulso, fps) {
    const { frequencias, potencias } = espectroPotencia(pulso, fps);
    if (!frequencias.length) return null;

    if (!this.espectroMedio || this.espectroMedio.length !== potencias.length) {
      // Primeira janela, ou a taxa de quadros mudou o bastante para mudar o
      // tamanho da transformada. Recomeçar é o certo: promediar espectros de
      // grades de frequência diferentes somaria coisas que não se
      // correspondem.
      this.frequenciasDoEspectro = frequencias;
      this.espectroMedio = Array.from(potencias);
    } else {
      const a = PESO_DO_ESPECTRO_NOVO;
      for (let k = 0; k < potencias.length; k++) {
        this.espectroMedio[k] = (1 - a) * this.espectroMedio[k] + a * potencias[k];
      }
    }

    const f = this.frequenciasDoEspectro;
    const p = this.espectroMedio;

    let indice = -1;
    let maior = -Infinity;
    for (let k = 0; k < f.length; k++) {
      if (f[k] < BANDA.minHz || f[k] > BANDA.maxHz) continue;
      if (p[k] > maior) {
        maior = p[k];
        indice = k;
      }
    }
    if (indice < 0) return null;

    const refinada = refinarPico(f, p, indice);
    if (!Number.isFinite(refinada) || refinada <= 0) return null;

    return {
      bpm: refinada * 60,
      snrDb: relacaoSinalRuido(f, p, refinada, BANDA.minHz, BANDA.maxHz),
    };
  }

  /**
   * Valor final da sessão: a mediana das janelas.
   * Preferimos a mediana à média porque uma única janela contaminada por
   * movimento pode ir parar longe, e a mediana ignora esse tipo de excursão.
   */
  resultadoFinal() {
    if (this.historico.length < 3) return null;
    const ordenado = [...this.historico].sort((a, b) => a - b);
    const meio = Math.floor(ordenado.length / 2);
    const mediana = ordenado.length % 2
      ? ordenado[meio]
      : (ordenado[meio - 1] + ordenado[meio]) / 2;
    return {
      bpm: mediana,
      dispersao: desvioPadrao(this.historico),
      janelas: this.historico.length,
      snrDb: this.ultimaAnalise?.snrDb ?? -Infinity,
    };
  }
}

/**
 * Analisa um vídeo já gravado, do começo ao fim, o mais rápido que o navegador
 * conseguir decodificar.
 */
export async function analisarVideo(video, { algoritmo = 'pos', janelaS = 15, aoProgredir } = {}) {
  const largura = 320;
  const altura = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * largura)) || 240;
  const canvas = document.createElement('canvas');
  canvas.width = largura;
  canvas.height = altura;
  const contexto = canvas.getContext('2d', { willReadFrequently: true });

  const duracao = video.duration;
  if (!Number.isFinite(duracao) || duracao <= 0) {
    throw new Error('Não foi possível ler a duração do vídeo.');
  }

  const fpsAlvo = 20;
  const passo = 1 / fpsAlvo;
  const amostras = [];

  const irPara = (tempo) => new Promise((resolve, reject) => {
    const aoBuscar = () => {
      video.removeEventListener('seeked', aoBuscar);
      resolve();
    };
    video.addEventListener('seeked', aoBuscar, { once: true });
    video.addEventListener('error', reject, { once: true });
    video.currentTime = Math.min(tempo, duracao - 1e-3);
  });

  for (let t = 0; t < duracao; t += passo) {
    await irPara(t);
    contexto.drawImage(video, 0, 0, largura, altura);

    let somaR = 0;
    let somaG = 0;
    let somaB = 0;
    let peso = 0;
    for (const regiao of REGIOES) {
      const rx = Math.round(regiao.x * largura);
      const ry = Math.round(regiao.y * altura);
      const rl = Math.max(1, Math.round(regiao.largura * largura));
      const ra = Math.max(1, Math.round(regiao.altura * altura));
      if (rx + rl > largura || ry + ra > altura) continue;
      const medida = mediaDaPele(contexto.getImageData(rx, ry, rl, ra).data, rl, ra, 1);
      if (!medida) continue;
      somaR += medida.vermelho * medida.pixels;
      somaG += medida.verde * medida.pixels;
      somaB += medida.azul * medida.pixels;
      peso += medida.pixels;
    }
    if (peso) amostras.push({ t, r: somaR / peso, g: somaG / peso, b: somaB / peso });
    if (aoProgredir) aoProgredir(t / duracao);
  }

  if (amostras.length < 64) {
    throw new Error(
      'Não foi encontrada pele suficiente no vídeo. O rosto precisa estar ' +
      'enquadrado onde o contorno indica, ocupando boa parte da imagem.',
    );
  }

  const fps = 1 / ((amostras[amostras.length - 1].t - amostras[0].t) / (amostras.length - 1));
  const serie = {
    vermelho: amostras.map((a) => a.r),
    verde: amostras.map((a) => a.g),
    azul: amostras.map((a) => a.b),
  };

  // Percorre o sinal em janelas deslizantes e usa a mediana, como no modo ao
  // vivo, para que uma janela ruim não determine o resultado.
  const porJanela = Math.round(janelaS * fps);
  const bpms = [];
  let ultimo = null;
  const passoJanela = Math.max(1, Math.round(fps));

  for (let inicio = 0; inicio + porJanela <= serie.verde.length; inicio += passoJanela) {
    const fatia = {
      vermelho: serie.vermelho.slice(inicio, inicio + porJanela),
      verde: serie.verde.slice(inicio, inicio + porJanela),
      azul: serie.azul.slice(inicio, inicio + porJanela),
    };
    const pulso = extrairPulso(fatia, fps, algoritmo, BANDA.minHz, BANDA.maxHz);
    const r = estimarFrequencia(pulso, fps, BANDA.minHz, BANDA.maxHz);
    if (r) {
      bpms.push(r.bpm);
      ultimo = { ...r, pulso };
    }
  }

  if (!bpms.length) {
    // Vídeo curto: tenta uma única janela com tudo que existe.
    const pulso = extrairPulso(serie, fps, algoritmo, BANDA.minHz, BANDA.maxHz);
    const r = estimarFrequencia(pulso, fps, BANDA.minHz, BANDA.maxHz);
    if (!r) throw new Error('O sinal não tem qualidade suficiente para uma estimativa.');
    return { bpm: r.bpm, snrDb: r.snrDb, dispersao: 0, janelas: 1, fps, espectro: r.espectro, pulso, duracaoS: duracao };
  }

  const ordenado = [...bpms].sort((a, b) => a - b);
  const meio = Math.floor(ordenado.length / 2);
  const mediana = ordenado.length % 2 ? ordenado[meio] : (ordenado[meio - 1] + ordenado[meio]) / 2;

  return {
    bpm: mediana,
    snrDb: ultimo?.snrDb ?? -Infinity,
    dispersao: desvioPadrao(bpms),
    janelas: bpms.length,
    fps,
    espectro: ultimo?.espectro ?? [],
    pulso: ultimo?.pulso ?? [],
    duracaoS: duracao,
  };
}
