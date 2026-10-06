/**
 * Testes do equilíbrio entre exposição e taxa de quadros.
 *
 * O caso central é o segundo bloco, "escada grossa". Ele reproduz o que a EMEET
 * SmartCam S600 faz de fato: declara aceitar qualquer tempo de exposição, com
 * passo de 1,22, e na prática só assume os degraus 5000, 2500, 1250, 625. Pedir
 * 666 devolve 1250, e a taxa de quadros não muda. A primeira versão deste
 * módulo pedia o valor calculado, confiava que ele tinha sido aceito, e
 * terminava com a câmera em 8 quadros por segundo achando que tinha resolvido.
 *
 * O conserto não foi pedir melhor. Foi **conferir onde a câmera ficou** e
 * insistir, e é isso que estes testes cobram.
 */

import {
  encaixarNaFaixa,
  equilibrar,
  exposicaoParaTaxa,
  medirTaxaEntregue,
  TAXA_MINIMA,
  UNIDADES_POR_SEGUNDO,
} from '../js/exposicao.js';

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) { passaram++; return; }
  falharam++;
  falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
}

function igual(nome, obtido, esperado) {
  verificar(nome, obtido === esperado, `esperado ${esperado}, obtido ${obtido}`);
}

function perto(nome, obtido, esperado, tolerancia) {
  verificar(nome, Number.isFinite(obtido) && Math.abs(obtido - esperado) <= tolerancia,
    `esperado ${esperado} ± ${tolerancia}, obtido ${obtido}`);
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Câmera de mentira, com escada opcional.
 *
 * `escada` é a lista de tempos que a câmera de fato assume. Pedir qualquer
 * outro valor cai no menor degrau que seja maior ou igual ao pedido, que é
 * exatamente o arredondamento para cima que quebrou a primeira versão.
 */
function trilhaFalsa({
  exposicao = 5000,
  faixa = { min: 1.220703125, max: 5000, step: 1.220703125 },
  escada = null,
  manual = true,
  recusarModo = false,
  recusarTempo = false,
  semCapacidades = false,
} = {}) {
  const ajustes = { exposureTime: exposicao, exposureMode: manual ? 'manual' : 'continuous' };
  const pedidos = [];
  return {
    pedidos,
    get exposicao() { return ajustes.exposureTime; },
    getCapabilities: semCapacidades ? undefined : () => ({
      exposureMode: manual ? ['continuous', 'manual'] : ['continuous'],
      ...(faixa ? { exposureTime: faixa } : {}),
    }),
    getSettings: () => ({ ...ajustes }),
    async applyConstraints(restricoes) {
      const avancado = restricoes?.advanced?.[0] ?? {};
      if ('exposureMode' in avancado) {
        if (recusarModo) throw new Error('recusado');
        ajustes.exposureMode = avancado.exposureMode;
        return;
      }
      if ('exposureTime' in avancado) {
        if (recusarTempo) throw new Error('recusado');
        pedidos.push(avancado.exposureTime);
        ajustes.exposureTime = escada
          ? (escada.find((degrau) => degrau >= avancado.exposureTime) ?? escada[escada.length - 1])
          : avancado.exposureTime;
      }
    },
  };
}

const semMedir = async () => Number.NaN;

async function ajustar(trilha, { luz = 20, taxaMinima = TAXA_MINIMA } = {}) {
  return equilibrar({
    trilha,
    video: {},
    luminancia: () => luz,
    espera: () => Promise.resolve(),
    medirTaxa: semMedir,
    taxaMinima,
  });
}

// ------------------------------------------------------- a conta do teto
{
  perto('a exposição máxima para 15 quadros por segundo são 66,7 ms',
    exposicaoParaTaxa(15), 666.67, 0.01);
  igual('um segundo são dez mil unidades', exposicaoParaTaxa(1), UNIDADES_POR_SEGUNDO);
  igual('taxa zero não tem teto', exposicaoParaTaxa(0), null);
  igual('taxa negativa também não', exposicaoParaTaxa(-5), null);
}

// ------------------------------------------------- encaixar no que a câmera tem
{
  igual('encaixa no passo', encaixarNaFaixa(100, { min: 0, max: 1000, step: 25 }), 100);
  igual('arredonda para o passo mais próximo',
    encaixarNaFaixa(107, { min: 0, max: 1000, step: 25 }), 100);
  igual('não passa do máximo', encaixarNaFaixa(5000, { min: 0, max: 1000, step: 25 }), 1000);
  igual('não passa do mínimo', encaixarNaFaixa(1, { min: 50, max: 1000, step: 25 }), 50);
  igual('faixa inválida não encaixa nada', encaixarNaFaixa(10, { min: 10, max: 10 }), null);
  igual('faixa ausente não encaixa nada', encaixarNaFaixa(10, undefined), null);
  igual('valor indefinido não encaixa nada',
    encaixarNaFaixa(Number.NaN, { min: 0, max: 100 }), null);
}

// ---------------------------------------------------------- escada grossa
{
  /*
    A regressão, em forma de teste.

    A câmera só assume 5000, 2500, 1250 e 625, e arredonda para cima. O teto é
    666,5. Pedir o teto devolve 1250, que ainda dá oito quadros por segundo.
    Quem confia no pedido para aí e acha que resolveu.
  */
  const trilha = trilhaFalsa({ exposicao: 5000, escada: [625, 1250, 2500, 5000] });
  const relato = await ajustar(trilha);

  verificar('a exposição acaba abaixo do teto',
    trilha.exposicao <= relato.teto, `ficou em ${trilha.exposicao}, teto ${relato.teto}`);
  igual('e o degrau escolhido é o da câmera', trilha.exposicao, 625);
  verificar('precisou de mais de um pedido', relato.passos >= 2, `${relato.passos} passos`);
  verificar('o relato diz que mexeu', relato.ajustou);
  verificar('e diz por quê', relato.motivo.includes('taxa de quadros mínima'), relato.motivo);
}

{
  // Sem escada, o primeiro pedido já resolve, e não há rodada de reserva.
  const trilha = trilhaFalsa({ exposicao: 5000 });
  const relato = await ajustar(trilha);
  perto('câmera fiel acerta de primeira', trilha.exposicao, 666.5, 1.5);
  igual('num passo só', relato.passos, 1);
}

{
  // Escada que não desce o suficiente: tem de parar, e dizer.
  const trilha = trilhaFalsa({ exposicao: 5000, escada: [2500, 5000] });
  const relato = await ajustar(trilha);
  igual('a câmera fica no menor degrau que tem', trilha.exposicao, 2500);
  verificar('e o relato admite que não deu',
    relato.motivo.includes('não desceu até o necessário'), relato.motivo);
  verificar('sem rodar sem fim', relato.passos <= 4, `${relato.passos} passos`);
}

// ------------------------------------------------- o outro lado, a luz
{
  // Exposição curta e imagem escura: sobe, mas nunca acima do teto.
  const trilha = trilhaFalsa({ exposicao: 100 });
  const relato = await ajustar(trilha, { luz: 20 });
  verificar('sobe a exposição quando a imagem está escura', trilha.exposicao > 100);
  verificar('e nunca passa do teto',
    trilha.exposicao <= relato.teto, `ficou em ${trilha.exposicao}, teto ${relato.teto}`);
  verificar('e diz por quê', relato.motivo.includes('imagem escura'), relato.motivo);
}

{
  // Já clara: não mexe.
  const trilha = trilhaFalsa({ exposicao: 300 });
  const relato = await ajustar(trilha, { luz: 140 });
  igual('imagem clara não leva ajuste', trilha.exposicao, 300);
  igual('e nenhum passo', relato.passos, 0);
  verificar('e o relato diz que não havia o que fazer',
    relato.motivo === 'nada a ajustar', relato.motivo);
}

{
  // Luz indefinida (sem quadro ainda) não pode virar ajuste às cegas.
  const trilha = trilhaFalsa({ exposicao: 300 });
  const relato = await equilibrar({
    trilha,
    video: {},
    luminancia: () => Number.NaN,
    espera: () => Promise.resolve(),
    medirTaxa: semMedir,
  });
  igual('luminância indefinida não move a exposição', trilha.exposicao, 300);
  igual('nem gera passo', relato.passos, 0);
}

// ------------------------------------------------------ câmeras limitadas
{
  const trilha = trilhaFalsa({ manual: false });
  const relato = await ajustar(trilha);
  verificar('câmera sem modo manual é relatada, não forçada',
    relato.motivo.includes('não expõe o tempo de exposição'), relato.motivo);
  igual('e nada é aplicado', relato.passos, 0);
}

{
  const trilha = trilhaFalsa({ faixa: null });
  const relato = await ajustar(trilha);
  verificar('câmera sem faixa de exposição também',
    relato.motivo.includes('não expõe o tempo de exposição'), relato.motivo);
}

{
  const trilha = trilhaFalsa({ semCapacidades: true });
  const relato = await ajustar(trilha);
  verificar('câmera sem capacidades não quebra nada',
    relato.motivo.includes('não deixa ajustar'), relato.motivo);
}

{
  const trilha = trilhaFalsa({ exposicao: 5000, recusarModo: true });
  const relato = await ajustar(trilha);
  verificar('recusa do modo manual é relatada',
    relato.motivo.includes('recusou o modo manual'), relato.motivo);
  igual('e a exposição fica como estava', trilha.exposicao, 5000);
}

{
  const trilha = trilhaFalsa({ exposicao: 5000, recusarTempo: true });
  const relato = await ajustar(trilha);
  igual('recusa do tempo deixa a exposição intacta', trilha.exposicao, 5000);
  igual('e não conta passo', relato.passos, 0);
  verificar('mas o relato registra a tentativa',
    relato.motivo.includes('taxa de quadros mínima'), relato.motivo);
}

{
  const eventos = [];
  const trilha = trilhaFalsa({ exposicao: 5000 });
  await equilibrar({
    trilha,
    video: {},
    luminancia: () => 20,
    espera: () => Promise.resolve(),
    medirTaxa: semMedir,
    registrar: (evento, dados) => eventos.push({ evento, dados }),
  });
  verificar('o ajuste fica registrado',
    eventos.some((e) => e.evento === 'exposicao.ajustada'),
    eventos.map((e) => e.evento).join(','));
}

// ------------------------------------------------------ medir a taxa de fato
{
  /** Vídeo de mentira que entrega quadros num intervalo escolhido. */
  function videoFalso({ intervaloS = 0.05, passoMs = 4, comCallback = true } = {}) {
    let tempo = 0;
    const video = { currentTime: 0 };
    const avancar = () => {
      tempo += intervaloS;
      video.currentTime = tempo;
    };
    if (comCallback) {
      video.requestVideoFrameCallback = (fn) => setTimeout(() => {
        avancar();
        fn(performance.now(), { mediaTime: tempo });
      }, passoMs);
    } else {
      setInterval(avancar, passoMs);
    }
    return video;
  }

  const taxa = await medirTaxaEntregue(videoFalso({ intervaloS: 0.05 }), {
    quadros: 10, prazoMs: 500,
  });
  perto('a taxa sai do tempo de mídia, não do relógio da parede', taxa, 20, 0.01);

  const taxaLenta = await medirTaxaEntregue(videoFalso({ intervaloS: 0.125 }), {
    quadros: 10, prazoMs: 500,
  });
  perto('e acompanha a câmera lenta', taxaLenta, 8, 0.01);

  /*
    Sem o callback de quadro, o caminho de reserva assume.

    Ele existe porque o principal devolveu nada em parte das execuções com
    navegador: o elemento de vídeo ainda está escondido na hora da abertura, e
    compor quadro de elemento invisível é opcional para o navegador.
  */
  const taxaReserva = await medirTaxaEntregue(
    videoFalso({ intervaloS: 0.05, passoMs: 10, comCallback: false }),
    { quadros: 8, prazoMs: 150 },
  );
  verificar('o caminho de reserva mede alguma coisa',
    Number.isFinite(taxaReserva) && taxaReserva > 0, `obtido ${taxaReserva}`);

  const semNada = await medirTaxaEntregue({}, { quadros: 5, prazoMs: 60 });
  verificar('vídeo que não anda não inventa taxa', Number.isNaN(semNada), `obtido ${semNada}`);
}

// ---------------------------------------------------------------------------
await espera(10);
process.stdout.write(`\n${'-'.repeat(62)}\n`);
if (falharam) {
  process.stdout.write(`FALHAS (${falharam}):\n`);
  falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
}
process.stdout.write(`exposição: ${passaram} passaram, ${falharam} falharam\n`);
process.exit(falharam ? 1 : 0);
