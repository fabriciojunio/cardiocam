/**
 * Testes do processamento de sinais no navegador.
 *
 * Rodam em Node com `npm test`, sem navegador e sem dependências. A estratégia
 * é a mesma da suíte em Python: gerar sinal cuja frequência verdadeira foi
 * escolhida por nós, rodar o código real e conferir a saída.
 */

import {
  confiancaDe,
  desvioPadrao,
  espectroPotencia,
  estimarFrequencia,
  fft,
  media,
  normalizar,
  passaFaixa,
  proximaPotenciaDeDois,
  refinarPico,
  relacaoSinalRuido,
  removerReferencia,
} from '../js/dsp.js';
import { extrairPulso } from '../js/rppg.js';
import { classificarPele } from '../js/pele.js';
import { Medidor, medirDedo, rectificarPeloFundo } from '../js/medidor.js';
import { PONTOS, regioesAncoradas, regioesDeFundo } from '../js/rosto.js';
import { avaliarCaptura, identificarPlataforma, LIMIARES } from '../js/tela.js';
import {
  GANHO_CANAL,
  gerarSerieRGB,
  geradorAleatorio,
  ondaDePulso,
  ruidoNormal,
} from './sintetico.js';

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) {
    passaram++;
  } else {
    falharam++;
    falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
  }
}

function proximo(nome, obtido, esperado, tolerancia) {
  verificar(
    nome,
    Number.isFinite(obtido) && Math.abs(obtido - esperado) <= tolerancia,
    `esperado ${esperado} ± ${tolerancia}, obtido ${Number(obtido).toFixed(3)}`,
  );
}

function grupo(titulo) {
  process.stdout.write(`\n${titulo}\n`);
}

const senoide = (bpm, fps, duracao, harmonicos = [1]) => {
  const n = Math.round(fps * duracao);
  return Array.from({ length: n }, (_, i) => {
    const t = i / fps;
    let s = 0;
    harmonicos.forEach((a, k) => {
      s += a * Math.sin(2 * Math.PI * (k + 1) * (bpm / 60) * t);
    });
    return s;
  });
};

// ---------------------------------------------------------------------------
grupo('FFT e utilidades');

for (const n of [1, 2, 7, 8, 100, 1000, 1024, 1025]) {
  const p = proximaPotenciaDeDois(n);
  verificar(`potência de dois >= ${n}`, p >= n && (p & (p - 1)) === 0, `obtido ${p}`);
}

{
  // Ida e volta pela FFT precisa devolver o sinal original.
  const n = 256;
  const original = Array.from({ length: n }, (_, i) => Math.sin(i / 5) + 0.3 * Math.cos(i / 3));
  const re = Float64Array.from(original);
  const im = new Float64Array(n);
  fft(re, im, false);
  fft(re, im, true);
  let maiorErro = 0;
  for (let i = 0; i < n; i++) maiorErro = Math.max(maiorErro, Math.abs(re[i] - original[i]));
  verificar('FFT ida e volta reconstrói o sinal', maiorErro < 1e-9, `erro ${maiorErro}`);
}

for (const bpm of [48, 60, 72, 90, 120, 150, 180]) {
  const { frequencias, potencias } = espectroPotencia(senoide(bpm, 30, 20), 30);
  let melhor = 0;
  for (let k = 1; k < potencias.length; k++) if (potencias[k] > potencias[melhor]) melhor = k;
  proximo(`espectro acha o pico de ${bpm} bpm`, frequencias[melhor] * 60, bpm, 1.5);
}

verificar('média de vetor vazio é zero', media([]) === 0);
verificar('desvio de vetor com um elemento é zero', desvioPadrao([5]) === 0);
verificar('normalizar sinal constante devolve zeros', normalizar([3, 3, 3, 3]).every((x) => x === 0));

{
  const z = normalizar([1, 2, 3, 4, 5, 6, 7, 8]);
  proximo('normalizar dá média nula', media(z), 0, 1e-9);
  proximo('normalizar dá desvio unitário', desvioPadrao(z), 1, 1e-9);
}

for (const deslocamento of [-0.4, -0.2, 0, 0.2, 0.4]) {
  const freqs = [1, 2, 3];
  const pot = [-1, 0, 1].map((x) => Math.exp(-((x - deslocamento) ** 2)));
  proximo(`refino parabólico com deslocamento ${deslocamento}`, refinarPico(freqs, pot, 1), 2 + deslocamento, 0.02);
}

verificar('refino na borda devolve o próprio bin', refinarPico([1, 2, 3], [1, 2, 1], 0) === 1);

// ---------------------------------------------------------------------------
grupo('Filtro passa-faixa');

for (const bpm of [50, 66, 80, 100, 130, 160, 190]) {
  const entrada = senoide(bpm, 30, 20);
  const saida = passaFaixa(entrada, 30, 0.75, 3.3);
  const miolo = (v) => v.slice(60, -60);
  const razao = desvioPadrao(miolo(saida)) / desvioPadrao(miolo(entrada));
  verificar(`passa-faixa preserva ${bpm} bpm`, razao > 0.7 && razao < 1.3, `razão ${razao.toFixed(3)}`);
}

for (const hz of [0.05, 0.15, 0.3, 6, 8, 10]) {
  const n = 600;
  const entrada = Array.from({ length: n }, (_, i) => Math.sin(2 * Math.PI * hz * (i / 30)));
  const saida = passaFaixa(entrada, 30, 0.75, 3.3);
  const miolo = (v) => v.slice(60, -60);
  const razao = desvioPadrao(miolo(saida)) / desvioPadrao(miolo(entrada));
  verificar(`passa-faixa rejeita ${hz} Hz`, razao < 0.2, `razão ${razao.toFixed(3)}`);
}

verificar('passa-faixa preserva o comprimento', passaFaixa(senoide(72, 30, 10), 30, 0.75, 3.3).length === 300);
verificar('passa-faixa aceita sinal curto', passaFaixa([1, 2], 30, 0.75, 3.3).length === 2);

// ---------------------------------------------------------------------------
grupo('Estimativa de frequência');

for (let bpm = 46; bpm <= 196; bpm += 2) {
  const r = estimarFrequencia(senoide(bpm, 30, 20), 30);
  proximo(`senoide pura de ${bpm} bpm`, r?.bpm, bpm, 1.0);
}

for (const bpm of [55, 70, 85, 100, 130]) {
  const r = estimarFrequencia(senoide(bpm, 30, 20, [1, 0.5, 0.2]), 30);
  proximo(`onda com harmônicos de ${bpm} bpm não pula para 2f`, r?.bpm, bpm, 1.5);
}

for (const fps of [15, 20, 24, 25, 30, 60]) {
  const r = estimarFrequencia(senoide(84, fps, 20), fps);
  proximo(`estimativa a ${fps} quadros por segundo`, r?.bpm, 84, 1.5);
}

verificar('sinal constante é recusado', estimarFrequencia(new Array(600).fill(5), 30) === null);
verificar('sinal curto demais é recusado', estimarFrequencia([1, 2, 3], 30) === null);
verificar('sinal todo zero é recusado', estimarFrequencia(new Array(600).fill(0), 30) === null);

for (const bpm of [60, 90, 120]) {
  const r = estimarFrequencia(senoide(bpm, 30, 20), 30);
  verificar(`relação sinal-ruído alta para ${bpm} bpm limpo`, r.snrDb > 5, `${r.snrDb.toFixed(1)} dB`);
  verificar(`relação sinal-ruído é finita para ${bpm} bpm`, Number.isFinite(r.snrDb));
}

{
  const aleatorio = geradorAleatorio(99);
  const ruido = Array.from({ length: 600 }, () => ruidoNormal(aleatorio));
  const r = estimarFrequencia(ruido, 30);
  verificar('ruído branco não produz confiança alta', r.snrDb < 8, `${r.snrDb.toFixed(1)} dB`);
}

verificar('confiança alta acima de 6 dB', confiancaDe(10) === 'alta');
verificar('confiança média entre 2 e 6 dB', confiancaDe(3) === 'média');
verificar('confiança baixa entre 0 e 2 dB', confiancaDe(1) === 'baixa');
verificar('confiança descartada abaixo de 0 dB', confiancaDe(-5) === 'descartada');

// ---------------------------------------------------------------------------
grupo('Algoritmos rPPG sobre série RGB modelada');

const ALGORITMOS = ['pos', 'chrom', 'verde'];
const BPMS = [50, 58, 66, 74, 82, 90, 104, 120, 140, 165];

for (const algoritmo of ALGORITMOS) {
  for (const bpm of BPMS) {
    const serie = gerarSerieRGB({ bpm, duracaoS: 20, semente: bpm });
    const pulso = extrairPulso(serie, serie.fps, algoritmo);
    const r = estimarFrequencia(pulso, serie.fps);
    proximo(`${algoritmo} em condição ideal, ${bpm} bpm`, r?.bpm, bpm, 2.5);
  }
}

for (const algoritmo of ALGORITMOS) {
  for (const bpm of [60, 78, 96, 120]) {
    for (const ruidoSensor of [0.2, 0.6, 1.2]) {
      const serie = gerarSerieRGB({ bpm, duracaoS: 22, ruidoSensor, semente: bpm + ruidoSensor * 10 });
      const r = estimarFrequencia(extrairPulso(serie, serie.fps, algoritmo), serie.fps);
      proximo(`${algoritmo} com ruído ${ruidoSensor}, ${bpm} bpm`, r?.bpm, bpm, 2.5);
    }
  }
}

for (const algoritmo of ALGORITMOS) {
  for (const bpm of [66, 84, 110]) {
    const serie = gerarSerieRGB({ bpm, duracaoS: 20, derivaIluminacao: 0.3, semente: bpm });
    const r = estimarFrequencia(extrairPulso(serie, serie.fps, algoritmo), serie.fps);
    proximo(`${algoritmo} com deriva de iluminação, ${bpm} bpm`, r?.bpm, bpm, 2.5);
  }
}

for (const tomPele of [
  { azul: 200, verde: 215, vermelho: 235 },
  { azul: 150, verde: 175, vermelho: 205 },
  { azul: 95, verde: 120, vermelho: 150 },
  { azul: 55, verde: 72, vermelho: 98 },
]) {
  for (const algoritmo of ['pos', 'chrom']) {
    const serie = gerarSerieRGB({ bpm: 78, duracaoS: 20, tomPele, semente: tomPele.verde });
    const r = estimarFrequencia(extrairPulso(serie, serie.fps, algoritmo), serie.fps);
    proximo(`${algoritmo} com tom de pele ${tomPele.verde}`, r?.bpm, 78, 2.5);
  }
}

// A prova de fogo: interferência de iluminação dentro da banda cardíaca. É o
// único cenário em que os métodos se separam, e reproduz o mesmo resultado da
// versão em Python.
grupo('Interferência dentro da banda cardíaca');

for (const bpm of [66, 78, 90, 108]) {
  const tremorHz = bpm / 60 + 0.7;
  const opcoes = { bpm, duracaoS: 22, amplitudePulso: 0.015, tremorAmplitude: 0.05, tremorHz, semente: bpm };

  for (const algoritmo of ['pos', 'chrom']) {
    const r = estimarFrequencia(extrairPulso(gerarSerieRGB(opcoes), 30, algoritmo), 30);
    proximo(`${algoritmo} rejeita interferência, ${bpm} bpm`, r?.bpm, bpm, 2.5);
  }

  const rVerde = estimarFrequencia(extrairPulso(gerarSerieRGB(opcoes), 30, 'verde'), 30);
  const erroNoPulso = Math.abs(rVerde.bpm - bpm);
  const erroNaInterferencia = Math.abs(rVerde.bpm - tremorHz * 60);
  verificar(
    `canal verde trava na interferência em ${bpm} bpm`,
    erroNaInterferencia < erroNoPulso,
    `mediu ${rVerde.bpm.toFixed(1)}, pulso ${bpm}, interferência ${(tremorHz * 60).toFixed(1)}`,
  );
}

// ---------------------------------------------------------------------------
grupo('Pipeline completo do navegador');

/**
 * Contexto de canvas falso: devolve pixels de pele já modulados pelo pulso.
 * Não substitui o código de medição, apenas o hardware. Todo o resto do
 * caminho, incluindo o recorte das regiões, a máscara de pele, a janela e a
 * estimativa, é o código real que roda no navegador.
 */
function contextoDePele(modulacao, aleatorio, tom = { r: 205, g: 175, b: 150 }) {
  return {
    getImageData(_x, _y, largura, altura) {
      const dados = new Uint8ClampedArray(largura * altura * 4);
      for (let i = 0; i < largura * altura; i++) {
        const ruido = ruidoNormal(aleatorio) * 1.5;
        dados[i * 4 + 0] = Math.max(0, Math.min(255, tom.r * modulacao.r + ruido));
        dados[i * 4 + 1] = Math.max(0, Math.min(255, tom.g * modulacao.g + ruido));
        dados[i * 4 + 2] = Math.max(0, Math.min(255, tom.b * modulacao.b + ruido));
        dados[i * 4 + 3] = 255;
      }
      return { data: dados };
    },
  };
}

for (const algoritmo of ['pos', 'chrom']) {
  for (const bpm of [58, 72, 88, 110, 132]) {
    const medidor = new Medidor({ janelaS: 12, algoritmo });
    const fps = 30;
    const total = fps * 20;
    const aleatorio = geradorAleatorio(bpm);
    const tempos = Array.from({ length: total }, (_, i) => i / fps);
    const pulso = ondaDePulso(tempos, bpm / 60);

    for (let i = 0; i < total; i++) {
      const amplitude = 0.02;
      const modulacao = {
        r: 1 + amplitude * GANHO_CANAL.vermelho * pulso[i],
        g: 1 + amplitude * GANHO_CANAL.verde * pulso[i],
        b: 1 + amplitude * GANHO_CANAL.azul * pulso[i],
      };
      medidor.processarQuadro(contextoDePele(modulacao, aleatorio), 320, 240, tempos[i]);
    }

    const analise = medidor.analisar();
    proximo(`Medidor com ${algoritmo}, ${bpm} bpm`, analise?.bpm, bpm, 3);
    verificar(`Medidor com ${algoritmo} reporta fps plausível`, analise && Math.abs(analise.fps - fps) < 3);
  }
}

{
  // Sem pele no quadro não pode sair medida.
  const medidor = new Medidor({ janelaS: 8 });
  const vazio = {
    getImageData(_x, _y, largura, altura) {
      const dados = new Uint8ClampedArray(largura * altura * 4);
      for (let i = 0; i < largura * altura; i++) {
        dados[i * 4 + 0] = 20; dados[i * 4 + 1] = 90; dados[i * 4 + 2] = 200; dados[i * 4 + 3] = 255;
      }
      return { data: dados };
    },
  };
  let ultimoEstado = null;
  for (let i = 0; i < 300; i++) ultimoEstado = medidor.processarQuadro(vazio, 320, 240, i / 30);
  verificar('quadro sem pele não é aceito', ultimoEstado.temPele === false);
  verificar('sem pele não produz análise', medidor.analisar() === null);
}

{
  // Pele perfeitamente constante: sem variação, sem medida.
  const medidor = new Medidor({ janelaS: 8 });
  const constante = contextoDePele({ r: 1, g: 1, b: 1 }, () => 0.5);
  for (let i = 0; i < 400; i++) medidor.processarQuadro(constante, 320, 240, i / 30);
  const analise = medidor.analisar();
  verificar('pele sem variação não vira batimento', analise === null || analise.snrDb < 6);
}

{
  // Progresso precisa crescer e a janela precisa encher.
  const medidor = new Medidor({ janelaS: 10 });
  const aleatorio = geradorAleatorio(5);
  const ctx = contextoDePele({ r: 1, g: 1, b: 1 }, aleatorio);
  const meio = medidor.processarQuadro(ctx, 320, 240, 0);
  verificar('progresso começa em zero', meio.progresso === 0);
  // 301 quadros a 30 quadros por segundo cobrem 10,0 s entre o primeiro e o
  // último instante, que é o que a janela exige.
  for (let i = 1; i <= 300; i++) medidor.processarQuadro(ctx, 320, 240, i / 30);
  verificar('progresso chega a um', medidor.progresso === 1, `obtido ${medidor.progresso}`);
}

// ---------------------------------------------------------------------------
grupo('Modo dedo (fotopletismografia de contato)');

/**
 * Dedo sobre a lente com a lanterna acesa: a imagem fica vermelha saturada e o
 * pulso é ordens de grandeza mais forte que no rosto, porque a luz atravessa o
 * tecido em vez de refletir na superfície.
 */
function contextoDeDedo(fatorPulso, aleatorio, cobrindo = true) {
  const base = cobrindo ? { r: 210, g: 60, b: 45 } : { r: 90, g: 95, b: 100 };
  return {
    getImageData(_x, _y, largura, altura) {
      const dados = new Uint8ClampedArray(largura * altura * 4);
      for (let i = 0; i < largura * altura; i++) {
        const ruido = ruidoNormal(aleatorio) * 1.2;
        dados[i * 4 + 0] = Math.max(0, Math.min(255, base.r + ruido));
        dados[i * 4 + 1] = Math.max(0, Math.min(255, base.g * fatorPulso + ruido));
        dados[i * 4 + 2] = Math.max(0, Math.min(255, base.b + ruido));
        dados[i * 4 + 3] = 255;
      }
      return { data: dados };
    },
  };
}

for (const bpm of [52, 64, 76, 88, 104, 128]) {
  const medidor = new Medidor({ janelaS: 10, modo: 'dedo' });
  const fps = 30;
  const total = fps * 16;
  const aleatorio = geradorAleatorio(bpm);
  const tempos = Array.from({ length: total }, (_, i) => i / fps);
  const pulso = ondaDePulso(tempos, bpm / 60);

  for (let i = 0; i < total; i++) {
    // Amplitude de 4%: no dedo o sinal é muito maior que no rosto.
    const ctx = contextoDeDedo(1 + 0.04 * pulso[i], aleatorio);
    medidor.processarQuadro(ctx, 320, 240, tempos[i]);
  }
  const analise = medidor.analisar();
  proximo(`modo dedo recupera ${bpm} bpm`, analise?.bpm, bpm, 2.5);
  verificar(`modo dedo tem boa confiança em ${bpm} bpm`, analise && analise.snrDb > 3,
    `snr ${analise ? analise.snrDb.toFixed(1) : 'nulo'} dB`);
}

{
  // Sem dedo cobrindo, a medição precisa recusar em vez de medir a sala.
  const medidor = new Medidor({ janelaS: 8, modo: 'dedo' });
  const aleatorio = geradorAleatorio(11);
  let estado = null;
  for (let i = 0; i < 300; i++) {
    estado = medidor.processarQuadro(contextoDeDedo(1, aleatorio, false), 320, 240, i / 30);
  }
  verificar('sem dedo na lente a medição é recusada', estado.temPele === false);
  verificar('sem dedo não há análise', medidor.analisar() === null);
  verificar('a mensagem orienta cobrir a lente', /cubra a lente/i.test(estado.mensagem));
}

{
  const aleatorio = geradorAleatorio(3);
  const ctx = contextoDeDedo(1.0, aleatorio);
  const m = medirDedo(ctx, 320, 240);
  verificar('dedo vermelho é reconhecido como cobrindo a lente', m.cobreALente);
  const semDedo = medirDedo(contextoDeDedo(1.0, aleatorio, false), 320, 240);
  verificar('cena cinza não é confundida com dedo', !semDedo.cobreALente);
}

// ---------------------------------------------------------------------------
grupo('Rectificação por referência de fundo');

for (const ganho of [0.5, 1, 2, 4]) {
  const interferencia = senoide(120, 30, 20);
  const limpo = removerReferencia(interferencia.map((x) => x * ganho), interferencia);
  verificar(
    `interferência pura removida com ganho ${ganho}`,
    desvioPadrao(limpo) < 0.2 * desvioPadrao(interferencia.map((x) => x * ganho)),
  );
}

for (const bpm of [60, 78, 96]) {
  for (const forca of [1, 2, 4]) {
    const pulso = senoide(bpm, 30, 24);
    const interferencia = senoide(bpm + 42, 30, 24);
    const limpo = removerReferencia(
      pulso.map((x, i) => x + forca * interferencia[i]),
      interferencia,
    );
    const correlacao = (a, b) => {
      const ma = media(a);
      const mb = media(b);
      let num = 0;
      let da = 0;
      let db = 0;
      for (let i = 0; i < a.length; i++) {
        num += (a[i] - ma) * (b[i] - mb);
        da += (a[i] - ma) ** 2;
        db += (b[i] - mb) ** 2;
      }
      return num / Math.sqrt(da * db);
    };
    verificar(
      `pulso de ${bpm} bpm sobrevive à remoção (interferência ${forca}x)`,
      correlacao(limpo, pulso) > 0.9,
      `correlação ${correlacao(limpo, pulso).toFixed(3)}`,
    );
    verificar(
      `interferência some com o pulso de ${bpm} bpm (${forca}x)`,
      Math.abs(correlacao(limpo, interferencia)) < 0.2,
    );
  }
}

verificar(
  'referência constante não altera o sinal',
  removerReferencia(senoide(72, 30, 20), new Array(600).fill(1)).every(
    (x, i) => Math.abs(x - senoide(72, 30, 20)[i]) < 1e-9,
  ),
);
verificar(
  'tamanhos incompatíveis devolvem a entrada',
  removerReferencia(senoide(72, 30, 20), [1, 2, 3]).length === 600,
);

// O caso que motivou a rectificação: balanço de branco automático oscilando
// dentro da banda cardíaca, com ganho diferente por canal. CHROM e POS não
// cancelam isso porque não é variação pura de intensidade.
{
  let semFundo = 0;
  let comFundo = 0;
  let total = 0;

  for (const bpm of [60, 72, 84, 96, 108]) {
    const fps = 30;
    const n = fps * 24;
    const hz = bpm / 60;
    let interfHz = hz + 0.7;
    if (interfHz > 3.2) interfHz = hz - 0.7;

    const aleatorio = geradorAleatorio(bpm);
    const tempos = Array.from({ length: n }, (_, i) => i / fps);
    const pulso = ondaDePulso(tempos, hz);
    const osc = tempos.map((t) => Math.sin(2 * Math.PI * interfHz * t + 0.4));
    const ganhos = { vermelho: 0.020, verde: 0.008, azul: 0.030 };
    const base = { vermelho: 205, verde: 175, azul: 150 };

    const rosto = {};
    const fundo = {};
    for (const c of ['vermelho', 'verde', 'azul']) {
      rosto[c] = tempos.map(
        (_, i) =>
          base[c] * (1 + ganhos[c] * osc[i]) * (1 + 0.012 * GANHO_CANAL[c] * pulso[i]) +
          ruidoNormal(aleatorio) * 0.05,
      );
      fundo[c] = tempos.map((_, i) => 120 * (1 + ganhos[c] * osc[i]) + ruidoNormal(aleatorio) * 0.05);
    }

    const semRect = estimarFrequencia(extrairPulso(rosto, fps, 'pos'), fps);
    const comRect = estimarFrequencia(extrairPulso(rectificarPeloFundo(rosto, fundo), fps, 'pos'), fps);

    total++;
    if (Math.abs(semRect.bpm - bpm) < 3) semFundo++;
    if (Math.abs(comRect.bpm - bpm) < 3) comFundo++;
    proximo(`rectificação salva ${bpm} bpm sob balanço de branco oscilante`, comRect?.bpm, bpm, 3);
  }

  verificar(
    'a rectificação é o que viabiliza esse cenário',
    comFundo > semFundo,
    `sem fundo ${semFundo}/${total}, com fundo ${comFundo}/${total}`,
  );
  process.stdout.write(`  (sem rectificação ${semFundo}/${total}, com rectificação ${comFundo}/${total})\n`);
}

// ---------------------------------------------------------------------------
grupo('Segmentação de pele');

const TONS_DE_PELE = [
  [235, 215, 200], [205, 175, 150], [185, 155, 130],
  [160, 130, 105], [135, 105, 85], [110, 85, 65], [88, 65, 48],
];
for (const [r, g, b] of TONS_DE_PELE) {
  verificar(`tom de pele rgb(${r},${g},${b}) reconhecido`, classificarPele(r, g, b));
}

const NAO_PELE = [[0, 0, 255], [0, 255, 0], [255, 0, 0], [20, 20, 20], [250, 250, 250], [120, 200, 90]];
for (const [r, g, b] of NAO_PELE) {
  verificar(`cor rgb(${r},${g},${b}) rejeitada como pele`, !classificarPele(r, g, b));
}

// ---------------------------------------------------------------------------
grupo('Regiões ancoradas nos olhos');

/* Olhos centrados, separados por 20% da largura do quadro. É a geometria de
   alguém sentado a meio metro da câmera, que é o caso de uso. */
const OLHOS_CENTRO = {
  esquerdo: { x: 0.40, y: 0.40 },
  direito: { x: 0.60, y: 0.40 },
};

{
  const regioes = regioesAncoradas(OLHOS_CENTRO);
  verificar('devolve três regiões', regioes?.length === 3);

  const [testa, bochechaE, bochechaD] = regioes;

  verificar('a testa fica acima da linha dos olhos',
    testa.y + testa.altura <= 0.40 + 1e-9,
    `fundo da testa em ${(testa.y + testa.altura).toFixed(3)}`);

  verificar('as bochechas ficam abaixo da linha dos olhos',
    bochechaE.y > 0.40 && bochechaD.y > 0.40);

  verificar('a testa é centrada entre os olhos',
    Math.abs(testa.x + testa.largura / 2 - 0.5) < 0.01);

  verificar('as duas bochechas têm o mesmo tamanho',
    Math.abs(bochechaE.largura - bochechaD.largura) < 1e-9
    && Math.abs(bochechaE.altura - bochechaD.altura) < 1e-9);

  verificar('a bochecha esquerda fica à esquerda da direita',
    bochechaE.x < bochechaD.x);

  /* O que faz a medição funcionar com a pessoa se movendo: as regiões são
     definidas pela distância entre os olhos, não pela posição absoluta. Mover
     o rosto tem de deslocar as regiões sem mudar o tamanho delas. */
  const deslocados = {
    esquerdo: { x: 0.40 + 0.15, y: 0.40 + 0.08 },
    direito: { x: 0.60 + 0.15, y: 0.40 + 0.08 },
  };
  const movidas = regioesAncoradas(deslocados);
  verificar('mover o rosto desloca as regiões sem mudar o tamanho',
    Math.abs(movidas[0].largura - testa.largura) < 1e-9
    && Math.abs(movidas[0].altura - testa.altura) < 1e-9
    && Math.abs(movidas[0].x - (testa.x + 0.15)) < 1e-9
    && Math.abs(movidas[0].y - (testa.y + 0.08)) < 1e-9);

  /* Aproximar o rosto aumenta a distância interocular, e as regiões têm de
     crescer na mesma proporção. Sem isso, a pessoa chegando perto mediria só
     um pedacinho da testa. */
  const perto = {
    esquerdo: { x: 0.30, y: 0.40 },
    direito: { x: 0.70, y: 0.40 },
  };
  const ampliadas = regioesAncoradas(perto);
  verificar('aproximar o rosto dobra o tamanho das regiões',
    Math.abs(ampliadas[0].largura - testa.largura * 2) < 1e-9);

  /* Rosto inclinado: os olhos deixam de estar na mesma altura. A testa tem de
     acompanhar o centro, senão sai do rosto. */
  const inclinado = {
    esquerdo: { x: 0.40, y: 0.36 },
    direito: { x: 0.60, y: 0.44 },
  };
  const giradas = regioesAncoradas(inclinado);
  verificar('rosto inclinado mantém a testa centrada no meio dos olhos',
    Math.abs(giradas[0].x + giradas[0].largura / 2 - 0.5) < 0.01);

  verificar('olhos coincidentes não produzem região',
    regioesAncoradas({ esquerdo: { x: 0.5, y: 0.5 }, direito: { x: 0.5, y: 0.5 } }) === null);

  verificar('sem olhos não produz região', regioesAncoradas(null) === null);

  /* Rosto na borda do quadro: as regiões são recortadas para dentro, e
     nenhuma pode sair dos limites, senão `getImageData` lança. */
  const naBorda = regioesAncoradas({
    esquerdo: { x: 0.02, y: 0.05 },
    direito: { x: 0.14, y: 0.05 },
  });
  verificar('região na borda fica dentro do quadro',
    naBorda.every((r) => r.x >= 0 && r.y >= 0
      && r.x + r.largura <= 1 + 1e-9 && r.y + r.altura <= 1 + 1e-9));
}

verificar('a ordem dos pontos do detector é a esperada',
  PONTOS.OLHO_ESQUERDO === 0 && PONTOS.OLHO_DIREITO === 1 && PONTOS.NARIZ === 2);

// ---------------------------------------------------------------------------
grupo('Faixas de fundo que fogem do rosto');

{
  /* O fundo serve de referência de iluminação, e só vale se não tiver pulso.
     Faixa fixa em cima do rosto conteria pele, e aí a correção injetaria o
     sinal que deveria remover. */
  const centro = { x: 0.35, y: 0.2, largura: 0.3, altura: 0.6 };
  const faixas = regioesDeFundo(centro);
  verificar('rosto no centro deixa as duas faixas laterais', faixas.length === 2);
  verificar('nenhuma faixa encosta no rosto',
    faixas.every((f) => f.x + f.largura <= centro.x || f.x >= centro.x + centro.largura));

  const naEsquerda = { x: 0.02, y: 0.2, largura: 0.4, altura: 0.6 };
  const faixasDireita = regioesDeFundo(naEsquerda);
  verificar('rosto à esquerda deixa só a faixa da direita',
    faixasDireita.length === 1 && faixasDireita[0].x > 0.5);

  const naDireita = { x: 0.58, y: 0.2, largura: 0.4, altura: 0.6 };
  const faixasEsquerda = regioesDeFundo(naDireita);
  verificar('rosto à direita deixa só a faixa da esquerda',
    faixasEsquerda.length === 1 && faixasEsquerda[0].x === 0);

  /* Rosto ocupando a largura inteira, que é o caso de quem chega muito perto
     da câmera. Sobra a faixa de cima, acima da testa. */
  const larguraToda = { x: 0.0, y: 0.25, largura: 1.0, altura: 0.7 };
  const faixaDeCima = regioesDeFundo(larguraToda);
  verificar('rosto ocupando a largura inteira usa a faixa de cima',
    faixaDeCima.length === 1 && faixaDeCima[0].altura <= 0.1);

  /* Rosto ocupando o quadro todo: não há fundo utilizável, e devolver faixa
     nenhuma é a resposta certa. O medidor então mede sem rectificação, em vez
     de rectificar por uma referência que é pele. */
  const quadroTodo = { x: 0, y: 0, largura: 1, altura: 1 };
  verificar('sem fundo utilizável devolve lista vazia',
    regioesDeFundo(quadroTodo).length === 0);

  verificar('sem rosto rastreado cai nas duas faixas fixas',
    regioesDeFundo(null).length === 2);
}

// ---------------------------------------------------------------------------
grupo('Captura de tela para medir em chamada');

function fluxoFalso(rotulo, ajustes = {}) {
  return {
    getVideoTracks: () => [{
      label: rotulo,
      getSettings: () => ajustes,
    }],
  };
}

verificar('reconhece a janela do Teams',
  identificarPlataforma(fluxoFalso('Reuniao | Microsoft Teams')).chave === 'teams');
verificar('reconhece o Google Meet',
  identificarPlataforma(fluxoFalso('meet.google.com')).chave === 'meet');
verificar('reconhece o Zoom',
  identificarPlataforma(fluxoFalso('Zoom Meeting')).chave === 'zoom');
verificar('reconhece o WhatsApp',
  identificarPlataforma(fluxoFalso('WhatsApp')).chave === 'whatsapp');
verificar('rótulo desconhecido não quebra',
  identificarPlataforma(fluxoFalso('')).chave === 'desconhecida');
verificar('fluxo nulo não quebra',
  identificarPlataforma(null).chave === 'desconhecida');

{
  /* A ressalva da compressão não é condicional: toda plataforma de chamada
     comprime, então o aviso vale sempre. */
  const semNada = avaliarCaptura(null, null);
  verificar('a ressalva da compressão aparece sempre',
    semNada.ressalva.includes('compressão'));

  const boa = avaliarCaptura(
    fluxoFalso('Teams', { width: 1920, height: 1080, frameRate: 30 }),
    { largura: 0.2 },  // rosto com 384 px numa captura de 1920
  );
  verificar('captura boa não gera aviso', boa.avisos.length === 0,
    boa.avisos.join(' | '));

  const lenta = avaliarCaptura(
    fluxoFalso('Teams', { width: 1280, height: 720, frameRate: 8 }),
    null,
  );
  verificar('taxa de quadros baixa gera aviso',
    lenta.avisos.some((a) => a.includes('quadros por segundo')));

  const pequena = avaliarCaptura(
    fluxoFalso('Teams', { width: 240, height: 180, frameRate: 30 }),
    null,
  );
  verificar('janela pequena gera aviso',
    pequena.avisos.some((a) => a.includes('pequena')));

  /* O caso que mais acontece de verdade: chamada em mosaico, com oito pessoas
     na tela. Cada rosto fica com poucas dezenas de pixels, e aí a média
     espacial não tem pixels suficientes para tirar o pulso do ruído. */
  const mosaico = avaliarCaptura(
    fluxoFalso('Teams', { width: 1280, height: 720, frameRate: 30 }),
    { largura: 0.05 },  // rosto com 64 px
  );
  verificar('rosto pequeno demais na captura gera aviso',
    mosaico.avisos.some((a) => a.includes('pixels de largura')));

  verificar('o limiar de largura do rosto é o documentado',
    LIMIARES.larguraMinimaDoRosto === 100);
  verificar('o limiar de taxa de quadros respeita Nyquist para 4 Hz',
    LIMIARES.quadrosPorSegundoMinimo >= 2 * 3.3);
}

// ---------------------------------------------------------------------------
process.stdout.write(`\n${'-'.repeat(62)}\n`);
if (falharam) {
  process.stdout.write(`FALHAS (${falharam}):\n`);
  falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
}
process.stdout.write(`${passaram} passaram, ${falharam} falharam\n`);
process.exit(falharam ? 1 : 0);
