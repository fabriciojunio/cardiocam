/**
 * Processamento de sinais no navegador.
 *
 * Porte da mesma matemática da versão em Python, com uma diferença de
 * implementação: em vez de um Butterworth aplicado nos dois sentidos, a
 * filtragem passa-faixa é feita no domínio da frequência, zerando os
 * coeficientes fora da banda. Como a janela já precisa de uma FFT para a
 * estimativa, filtrar assim sai praticamente de graça e a fase fica exatamente
 * preservada, sem depender de acertar os coeficientes de um IIR à mão.
 *
 * O preço é o toque de Gibbs nas bordas da banda, que não atrapalha porque só
 * usamos o resultado para localizar um pico, não para reconstruir a forma de
 * onda com fidelidade.
 */

export function proximaPotenciaDeDois(n) {
  let p = 1;
  while (p < n) p *= 2;
  return p;
}

/**
 * FFT iterativa radix-2, no lugar. Espera comprimento potência de dois.
 * Modifica os arrays re e im recebidos.
 */
export function fft(re, im, inversa = false) {
  const n = re.length;
  if (n <= 1) return;

  // Reordenação por inversão de bits.
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }

  for (let tamanho = 2; tamanho <= n; tamanho <<= 1) {
    const angulo = (inversa ? 2 : -2) * Math.PI / tamanho;
    const passoRe = Math.cos(angulo);
    const passoIm = Math.sin(angulo);
    for (let bloco = 0; bloco < n; bloco += tamanho) {
      let wRe = 1;
      let wIm = 0;
      for (let k = 0; k < tamanho / 2; k++) {
        const parRe = re[bloco + k];
        const parIm = im[bloco + k];
        const imparRe = re[bloco + k + tamanho / 2] * wRe - im[bloco + k + tamanho / 2] * wIm;
        const imparIm = re[bloco + k + tamanho / 2] * wIm + im[bloco + k + tamanho / 2] * wRe;

        re[bloco + k] = parRe + imparRe;
        im[bloco + k] = parIm + imparIm;
        re[bloco + k + tamanho / 2] = parRe - imparRe;
        im[bloco + k + tamanho / 2] = parIm - imparIm;

        const proxRe = wRe * passoRe - wIm * passoIm;
        wIm = wRe * passoIm + wIm * passoRe;
        wRe = proxRe;
      }
    }
  }

  if (inversa) {
    for (let i = 0; i < n; i++) {
      re[i] /= n;
      im[i] /= n;
    }
  }
}

export function media(v) {
  if (!v.length) return 0;
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i];
  return s / v.length;
}

export function desvioPadrao(v) {
  if (v.length < 2) return 0;
  const m = media(v);
  let s = 0;
  for (let i = 0; i < v.length; i++) s += (v[i] - m) ** 2;
  return Math.sqrt(s / v.length);
}

export function removerMedia(v) {
  const m = media(v);
  return v.map((x) => x - m);
}

/** Escore z; devolve zeros se o sinal for constante. */
export function normalizar(v) {
  const d = desvioPadrao(v);
  if (d < 1e-12) return v.map(() => 0);
  const m = media(v);
  return v.map((x) => (x - m) / d);
}

/**
 * Passa-faixa de fase zero por mascaramento no domínio da frequência.
 * Devolve um novo array do mesmo comprimento.
 */
export function passaFaixa(sinal, fps, minHz, maxHz) {
  const n = sinal.length;
  if (n < 4) return sinal.slice();

  const tamanho = proximaPotenciaDeDois(n);
  const re = new Float64Array(tamanho);
  const im = new Float64Array(tamanho);
  const m = media(sinal);
  for (let i = 0; i < n; i++) re[i] = sinal[i] - m;

  fft(re, im, false);

  const resolucao = fps / tamanho;
  for (let k = 0; k <= tamanho / 2; k++) {
    const f = k * resolucao;
    if (f < minHz || f > maxHz) {
      re[k] = 0;
      im[k] = 0;
      // O espectro de um sinal real é simétrico; zerar só metade produziria
      // um resultado complexo na volta.
      const espelho = (tamanho - k) % tamanho;
      re[espelho] = 0;
      im[espelho] = 0;
    }
  }

  fft(re, im, true);
  return Array.from(re.slice(0, n));
}

/** Janela de Hann, para reduzir o vazamento espectral. */
export function hann(n) {
  const w = new Float64Array(n);
  for (let i = 0; i < n; i++) w[i] = 0.5 * (1 - Math.cos((2 * Math.PI * i) / (n - 1)));
  return w;
}

/**
 * Densidade espectral de potência com apodização de Hann e preenchimento com
 * zeros. O preenchimento não cria informação, apenas interpola o espectro numa
 * grade fina o bastante para o refino parabólico funcionar.
 */
export function espectroPotencia(sinal, fps, fatorZeroPadding = 8) {
  const n = sinal.length;
  if (n < 4) return { frequencias: [], potencias: [] };

  const janela = hann(n);
  const tamanho = proximaPotenciaDeDois(n * fatorZeroPadding);
  const re = new Float64Array(tamanho);
  const im = new Float64Array(tamanho);
  const m = media(sinal);

  let ganho = 0;
  for (let i = 0; i < n; i++) {
    re[i] = (sinal[i] - m) * janela[i];
    ganho += janela[i] * janela[i];
  }

  fft(re, im, false);

  const metade = Math.floor(tamanho / 2) + 1;
  const frequencias = new Array(metade);
  const potencias = new Array(metade);
  for (let k = 0; k < metade; k++) {
    frequencias[k] = (k * fps) / tamanho;
    potencias[k] = (re[k] * re[k] + im[k] * im[k]) / (ganho * fps);
  }
  return { frequencias, potencias };
}

/**
 * Interpolação parabólica em escala logarítmica em torno do bin de pico.
 * Como a janela de Hann tem lóbulo principal simétrico, o vértice da parábola
 * cai praticamente sobre a frequência verdadeira.
 */
export function refinarPico(frequencias, potencias, indice) {
  if (indice <= 0 || indice >= potencias.length - 1) return frequencias[indice];
  const [a, b, c] = [potencias[indice - 1], potencias[indice], potencias[indice + 1]];
  if (a <= 0 || b <= 0 || c <= 0) return frequencias[indice];

  const e = Math.log(a);
  const meio = Math.log(b);
  const d = Math.log(c);
  const denominador = e - 2 * meio + d;
  if (Math.abs(denominador) < 1e-18) return frequencias[indice];

  let deslocamento = (0.5 * (e - d)) / denominador;
  deslocamento = Math.max(-0.5, Math.min(0.5, deslocamento));
  const passo = frequencias[indice + 1] - frequencias[indice];
  return frequencias[indice] + deslocamento * passo;
}

const SNR_MAXIMO_DB = 60;

/**
 * Relação sinal-ruído no espectro. Considera sinal a energia perto da
 * fundamental e do primeiro harmônico, e ruído todo o resto da banda. O
 * harmônico entra porque a onda de pulso não é senoidal: a subida é rápida e a
 * descida lenta, o que sempre deposita energia em 2f.
 */
export function relacaoSinalRuido(frequencias, potencias, alvoHz, minHz, maxHz, largura = 0.1) {
  let pSinal = 0;
  let pRuido = 0;
  for (let k = 0; k < frequencias.length; k++) {
    const f = frequencias[k];
    if (f < minHz || f > maxHz) continue;
    const naFundamental = Math.abs(f - alvoHz) <= largura;
    const noHarmonico = Math.abs(f - 2 * alvoHz) <= 2 * largura;
    if (naFundamental || noHarmonico) pSinal += potencias[k];
    else pRuido += potencias[k];
  }
  if (pSinal <= 1e-20) return -Infinity;
  if (pRuido <= 1e-20) return SNR_MAXIMO_DB;
  return Math.min(SNR_MAXIMO_DB, 10 * Math.log10(pSinal / pRuido));
}

/**
 * Encontra a frequência dominante dentro da banda cardíaca.
 * Devolve null quando o sinal é numericamente indistinguível de zero, que é o
 * caso de uma imagem saturada ou de uma parede lisa no lugar do rosto. Um
 * medidor que não sabe dizer "não sei" é pior que inútil.
 */
export function estimarFrequencia(sinal, fps, minHz = 0.75, maxHz = 3.3) {
  if (sinal.length < 32) return null;
  if (desvioPadrao(sinal) < 1e-9) return null;

  const { frequencias, potencias } = espectroPotencia(sinal, fps);
  if (!frequencias.length) return null;

  let indicePico = -1;
  let maior = -Infinity;
  for (let k = 0; k < frequencias.length; k++) {
    const f = frequencias[k];
    if (f < minHz || f > maxHz) continue;
    if (potencias[k] > maior) {
      maior = potencias[k];
      indicePico = k;
    }
  }
  if (indicePico < 0) return null;

  let hz = refinarPico(frequencias, potencias, indicePico);
  hz = Math.max(minHz, Math.min(maxHz, hz));
  const snrDb = relacaoSinalRuido(frequencias, potencias, hz, minHz, maxHz);

  const daBanda = [];
  for (let k = 0; k < frequencias.length; k++) {
    if (frequencias[k] >= minHz && frequencias[k] <= maxHz) {
      daBanda.push({ hz: frequencias[k], potencia: potencias[k] });
    }
  }

  return { hz, bpm: hz * 60, snrDb, espectro: daBanda };
}

/** Classificação legível da qualidade, igual à da versão em Python. */
export function confiancaDe(snrDb) {
  if (snrDb >= 6) return 'alta';
  if (snrDb >= 2) return 'média';
  if (snrDb >= 0) return 'baixa';
  return 'descartada';
}
