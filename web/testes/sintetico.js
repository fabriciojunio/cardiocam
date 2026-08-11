/**
 * Gerador de séries RGB sintéticas, espelhando o modelo físico usado nos
 * testes da versão em Python. É o que permite verificar o porte para
 * JavaScript: a frequência verdadeira é escolhida por nós, então o erro é
 * mensurável com exatidão.
 */

// Sensibilidade relativa de cada canal ao volume sanguíneo. O verde domina
// porque a absorção da hemoglobina tem máximo perto de 540 nm.
export const GANHO_CANAL = { vermelho: 0.3, verde: 1.0, azul: 0.55 };

/** Gerador pseudoaleatório determinístico, para os testes serem reprodutíveis. */
export function geradorAleatorio(semente) {
  let estado = semente >>> 0;
  return function () {
    estado |= 0;
    estado = (estado + 0x6d2b79f5) | 0;
    let t = Math.imul(estado ^ (estado >>> 15), 1 | estado);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Ruído gaussiano por Box-Muller. */
export function ruidoNormal(aleatorio) {
  let u = 0;
  let v = 0;
  while (u === 0) u = aleatorio();
  while (v === 0) v = aleatorio();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/**
 * Onda de pulso com harmônicos, normalizada para amplitude máxima unitária.
 * Os harmônicos existem porque a onda real tem subida rápida e descida lenta.
 */
export function ondaDePulso(tempos, hz, harmonicos = [1.0, 0.35, 0.12]) {
  const onda = tempos.map((t) => {
    let s = 0;
    harmonicos.forEach((amplitude, indice) => {
      s += amplitude * Math.sin(2 * Math.PI * (indice + 1) * hz * t);
    });
    return s;
  });
  const maximo = Math.max(...onda.map(Math.abs));
  return maximo > 1e-12 ? onda.map((x) => x / maximo) : onda;
}

/**
 * Série RGB com pulso de frequência conhecida.
 *
 * `derivaIluminacao` é uma rampa lenta e `tremorAmplitude` uma oscilação, ambas
 * comuns aos três canais. É essa a distorção que CHROM e POS cancelam e que o
 * canal verde sozinho não tem como distinguir do pulso.
 */
export function gerarSerieRGB({
  bpm = 72,
  duracaoS = 20,
  fps = 30,
  amplitudePulso = 0.02,
  ruidoSensor = 0.05,
  derivaIluminacao = 0,
  tremorAmplitude = 0,
  tremorHz = 0.2,
  tomPele = { azul: 150, verde: 175, vermelho: 205 },
  semente = 1,
} = {}) {
  const total = Math.max(2, Math.round(duracaoS * fps));
  const tempos = Array.from({ length: total }, (_, i) => i / fps);
  const hz = bpm / 60;
  const pulso = ondaDePulso(tempos, hz);
  const aleatorio = geradorAleatorio(semente);

  const iluminacao = tempos.map((t) => {
    let fator = 1;
    if (derivaIluminacao) fator += (derivaIluminacao * t) / Math.max(1e-9, tempos[total - 1]);
    if (tremorAmplitude) fator += tremorAmplitude * Math.sin(2 * Math.PI * tremorHz * t);
    return fator;
  });

  const canal = (base, ganho) =>
    tempos.map((_, i) =>
      base * iluminacao[i] * (1 + amplitudePulso * ganho * pulso[i]) +
      ruidoNormal(aleatorio) * ruidoSensor,
    );

  return {
    vermelho: canal(tomPele.vermelho, GANHO_CANAL.vermelho),
    verde: canal(tomPele.verde, GANHO_CANAL.verde),
    azul: canal(tomPele.azul, GANHO_CANAL.azul),
    fps,
    bpmVerdadeiro: bpm,
  };
}
