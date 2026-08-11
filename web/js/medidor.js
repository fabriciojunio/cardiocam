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

import { desvioPadrao, estimarFrequencia, media, removerReferencia } from './dsp.js';
import { classificarPele, construirSelecao, mediaDaPele, mediaPorSelecao } from './pele.js';
import { extrairPulso } from './rppg.js';

export const BANDA = { minHz: 0.75, maxHz: 3.3 };
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
export const REGIOES_FUNDO = [
  { x: 0.0, y: 0.0, largura: 0.13, altura: 1.0 },
  { x: 0.87, y: 0.0, largura: 0.13, altura: 1.0 },
];

/**
 * Média RGB dos pixels de fundo, descartando qualquer coisa que pareça pele.
 * Se um braço ou outra pessoa entrar na faixa lateral, esses pixels teriam
 * pulso e contaminariam a referência.
 */
export function medirFundo(contexto, largura, altura, passo = 3) {
  let somaR = 0;
  let somaG = 0;
  let somaB = 0;
  let usados = 0;

  for (const regiao of REGIOES_FUNDO) {
    const rx = Math.round(regiao.x * largura);
    const ry = Math.round(regiao.y * altura);
    const rl = Math.max(1, Math.round(regiao.largura * largura));
    const ra = Math.max(1, Math.round(regiao.altura * altura));
    if (rx + rl > largura || ry + ra > altura) continue;

    const dados = contexto.getImageData(rx, ry, rl, ra).data;
    for (let y = 0; y < ra; y += passo) {
      for (let x = 0; x < rl; x += passo) {
        const i = (y * rl + x) * 4;
        const r = dados[i];
        const g = dados[i + 1];
        const b = dados[i + 2];
        if (classificarPele(r, g, b)) continue;
        somaR += r;
        somaG += g;
        somaB += b;
        usados++;
      }
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

export class Medidor {
  /**
   * @param {object} opcoes
   * @param {number} opcoes.janelaS  segundos acumulados antes de estimar
   * @param {string} opcoes.algoritmo  pos, chrom ou verde
   */
  constructor({ janelaS = 15, algoritmo = 'pos', usarFundo = true } = {}) {
    this.janelaS = janelaS;
    this.algoritmo = algoritmo;
    this.usarFundo = usarFundo;
    this.reiniciar();
  }

  reiniciar() {
    this.amostras = [];
    this.ultimaAnalise = null;
    this.bpmSuavizado = null;
    this.historico = [];
    this.quadrosSemPele = 0;
    this.inicio = null;
  }

  get duracaoAcumulada() {
    if (this.amostras.length < 2) return 0;
    return this.amostras[this.amostras.length - 1].t - this.amostras[0].t;
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
   * @returns {object} estado para a interface
   */
  processarQuadro(contexto, largura, altura, instanteS) {
    if (this.inicio === null) this.inicio = instanteS;

    let somaR = 0;
    let somaG = 0;
    let somaB = 0;
    let pesoTotal = 0;
    let proporcaoPele = 0;

    for (const regiao of REGIOES) {
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
      return { temPele: false, mensagem: 'Encaixe o rosto no contorno.', progresso: this.progresso };
    }

    this.quadrosSemPele = 0;
    const fundo = this.usarFundo ? medirFundo(contexto, largura, altura) : null;
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

    // A rectificação vem antes do algoritmo de propósito: o balanço de branco
    // automático age sobre cada canal separadamente, então é aí que a correção
    // pertence. Depois da combinação cromática já não há como desfazer.
    if (this.usarFundo && this.amostras.every((a) => a.fundo)) {
      serie = rectificarPeloFundo(serie, {
        vermelho: this.amostras.map((a) => a.fundo.vermelho),
        verde: this.amostras.map((a) => a.fundo.verde),
        azul: this.amostras.map((a) => a.fundo.azul),
      });
    }

    const pulso = extrairPulso(serie, fps, this.algoritmo, BANDA.minHz, BANDA.maxHz);
    const resultado = estimarFrequencia(pulso, fps, BANDA.minHz, BANDA.maxHz);
    if (!resultado) return null;

    // Média exponencial do valor exibido. Sem isso o número oscila alguns
    // batimentos a cada atualização e passa impressão de instabilidade mesmo
    // quando a medição está correta.
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
