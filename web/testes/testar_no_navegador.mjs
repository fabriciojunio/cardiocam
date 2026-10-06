/**
 * Teste de ponta a ponta: a página de verdade, num Chromium de verdade.
 *
 * Existe porque duas correções seguidas do laço de captura foram publicadas e
 * não resolveram, e as duas vezes o motivo só podia ser visto com um navegador
 * aberto. A suíte sem navegador testa as peças; esta testa a montagem, que é
 * onde as falhas estavam: o vigia que não era armado, a base de tempo
 * misturada, a câmera reabrindo sozinha.
 *
 * A câmera é falsa, e é falsa de um jeito útil: o Chromium aceita
 * `--use-file-for-fake-video-capture` e entrega um arquivo y4m no lugar do
 * sensor. O arquivo é gerado por `ferramentas/gerar_y4m.py`, com o mesmo
 * simulador que a suíte em Python usa, então a frequência cardíaca que a página
 * tem de encontrar é conhecida de antemão. Entra por `getUserMedia`, passa por
 * `requestVideoFrameCallback` e pelo resto do caminho real.
 *
 * Não roda no `npm test`, porque depende de navegador instalado e leva meio
 * minuto. Roda com `npm run test:navegador`.
 */

import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrirAba, abrirNavegador, acharNavegador } from './navegador/cdp.mjs';
import { servir } from './navegador/servidor.mjs';

/* O heredoc deste ambiente come a contrabarra, entao a quebra de linha vem
   por constante em vez de literal. */
const NOVA_LINHA = String.fromCharCode(10);
const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..');

/** Frequência gravada no vídeo falso. A página tem de chegar perto dela. */
const BPM_DO_VIDEO = 75;
/** Quanto a leitura pode errar. Larga de propósito: o alvo aqui é a montagem. */
const TOLERANCIA_BPM = 8;
/** Quanto tempo a medição roda. A janela padrão é de 15 s. */
const SEGUNDOS_DE_MEDICAO = Number(process.env.CARDIOCAM_SEGUNDOS || 40);

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) { passaram++; return true; }
  falharam++;
  falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
  return false;
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

/** Separa a linha do tempo do diagnóstico em eventos. */
function lerEventos(texto) {
  const eventos = [];
  for (const linha of texto.split('\n')) {
    const partes = linha.trim().split(/\s+/);
    if (partes.length < 2 || !partes[0].endsWith('s')) continue;
    const segundos = Number(partes[0].slice(0, -1));
    if (!Number.isFinite(segundos)) continue;
    const dados = {};
    for (const par of partes.slice(2)) {
      const igual = par.indexOf('=');
      if (igual < 0) continue;
      const valor = par.slice(igual + 1);
      const numero = Number(valor);
      dados[par.slice(0, igual)] = valor !== '' && Number.isFinite(numero) ? numero : valor;
    }
    eventos.push({ segundos, evento: partes[1], dados });
  }
  return eventos;
}

const contar = (eventos, nome) => eventos.filter((e) => e.evento === nome).length;

async function principal() {
  /*
    Com `--real`, usa a câmera do computador em vez da falsa.

    É o modo que reproduz o ambiente de quem relatou o defeito, e por isso o
    único que prova alguma coisa sobre hardware: webcam USB, driver do Windows,
    Chromium sem interface. A permissão sai de `--use-fake-ui-for-media-stream`,
    que concede sem perguntar. A leitura de frequência não é cobrada neste modo,
    porque não há como saber o batimento de quem, ou do que, estiver na frente
    da lente.
  */
  const comCameraReal = process.argv.includes('--real');
  /*
    Com `--exposicao-maxima`, prende a câmera no tempo de exposição mais longo
    que ela aceita **antes** de abrir a página.

    É a reprodução exata do defeito relatado. A EMEET SmartCam S600 abre nesse
    estado por conta própria, e nele entrega oito quadros por segundo em
    qualquer resolução. A versão anterior do aplicativo lia a taxa baixa,
    concluía que a culpa era da resolução, e reabria a câmera. Duas vezes. Do
    lado de fora: a câmera desligando e ligando sozinha, e a contagem nunca
    terminando.

    O ajuste de exposição é do dispositivo e sobrevive ao fim do fluxo, então
    basta pedi-lo uma vez, soltar a câmera, e abrir a página em seguida.
  */
  const comExposicaoMaxima = process.argv.includes('--exposicao-maxima');
  const videoFalso = process.env.CARDIOCAM_VIDEO_FALSO
    || join(process.env.TEMP || '/tmp', 'cardiocam-falso-75.y4m');
  const comVideo = !comCameraReal && existsSync(videoFalso);
  if (!comVideo && !comCameraReal) {
    process.stdout.write(
      `\nAviso: ${videoFalso} não existe, então a câmera falsa entrega o padrão\n`
      + 'rolante do Chromium, sem rosto. A cadência ainda é testada; a leitura\n'
      + 'de frequência, não. Gere o arquivo com gerar_y4m.py.\n\n',
    );
  }

  const executavel = acharNavegador();
  if (!executavel) {
    process.stdout.write('Nenhum Chromium encontrado. Defina CHROME com o caminho.\n');
    process.exit(2);
  }
  process.stdout.write(`navegador: ${executavel}\n`);
  process.stdout.write(`câmera: ${comCameraReal ? 'a do computador' : comVideo ? videoFalso : 'padrão do Chromium'}\n`);

  /*
    Por padrão a página vem de um servidor local, para testar o que está no
    disco. Com `CARDIOCAM_URL`, vem do endereço indicado, e aí o que se testa é
    o que está publicado. Os dois importam, e por motivos diferentes: o local
    pega o defeito antes de subir, e o publicado pega o que só aparece depois,
    como arquivo que não foi junto no envio.
  */
  const externo = process.env.CARDIOCAM_URL || null;
  const servidor = externo
    ? { url: externo, fechar: async () => {} }
    : await servir(RAIZ);
  process.stdout.write(`página: ${servidor.url}` + NOVA_LINHA);
  const navegador = await abrirNavegador({
    executavel,
    argumentos: comCameraReal ? [] : [
      '--use-fake-device-for-media-stream',
      ...(comVideo ? [`--use-file-for-fake-video-capture=${videoFalso}`] : []),
    ],
  });

  try {
    const problemas = [];
    const aba = await abrirAba(navegador.sessao, servidor.url, {
      aoErro: (mensagem) => {
        if (mensagem.method === 'Runtime.exceptionThrown') {
          const d = mensagem.params.exceptionDetails;
          problemas.push(d.exception?.description || d.text);
        }
        if (mensagem.method === 'Runtime.consoleAPICalled'
            && ['error', 'warning'].includes(mensagem.params.type)) {
          problemas.push(`console.${mensagem.params.type}: `
            + mensagem.params.args.map((x) => x.value ?? x.description ?? '?').join(' '));
        }
      },
    });

    // Espera o módulo carregar. Se ele cair, `cardiocamDiagnostico` não existe,
    // e isso já é a falha mais importante que esta página pode ter.
    let carregou = false;
    for (let i = 0; i < 100 && !carregou; i++) {
      carregou = await aba.avaliar('typeof window.cardiocamDiagnostico === "function"');
      if (!carregou) await espera(100);
    }
    if (!verificar('o módulo da página carrega', carregou)) return;

    if (comExposicaoMaxima) {
      const preparo = await aba.avaliar(`(async () => {
        const fluxo = await navigator.mediaDevices.getUserMedia({ video: true });
        const trilha = fluxo.getVideoTracks()[0];
        const faixa = trilha.getCapabilities?.().exposureTime;
        if (!faixa) { fluxo.getTracks().forEach((t) => t.stop()); return { pulou: true }; }
        await trilha.applyConstraints({ advanced: [{ exposureMode: 'manual' }] });
        await trilha.applyConstraints({ advanced: [{ exposureTime: faixa.max }] });
        const ficou = trilha.getSettings().exposureTime;
        fluxo.getTracks().forEach((t) => t.stop());
        return { pulou: false, pedido: faixa.max, ficou };
      })()`);
      process.stdout.write(`preparo: exposição presa em ${JSON.stringify(preparo)}` + NOVA_LINHA);
      verificar('deu para prender a câmera na exposição máxima', preparo.pulou !== true);
      await espera(800);
    }

    await aba.avaliar('document.getElementById("btnIniciar").click(); true');

    const amostras = [];
    for (let s = 0; s < SEGUNDOS_DE_MEDICAO; s++) {
      await espera(1000);
      amostras.push(await aba.avaliar(`(() => ({
        estado: document.getElementById('estado').textContent,
        bpm: document.getElementById('bpm').textContent,
        selo: document.getElementById('selo').textContent,
        janelas: document.getElementById('dadoJanelas').textContent,
        snr: document.getElementById('dadoSnr').textContent,
        taxa: document.getElementById('dadoFps').textContent,
        resolucao: document.getElementById('dadoResolucao').textContent,
        progresso: document.querySelector('#barraProgresso i').style.width,
      }))()`));
    }

    const diagnostico = await aba.avaliar('window.cardiocamDiagnostico()');
    const eventos = lerEventos(diagnostico);
    const pulsos = eventos.filter((e) => e.evento === 'pulso');
    const ultima = amostras[amostras.length - 1];

    process.stdout.write(`\n${'='.repeat(64)}\n`);
    process.stdout.write(diagnostico.split('\n').slice(1, 8).join('\n'));
    process.stdout.write(`\n${'='.repeat(64)}\n`);
    for (const e of eventos.filter((x) => x.evento !== 'pulso')) {
      process.stdout.write(`  ${e.segundos.toFixed(2)}s  ${e.evento}  ${JSON.stringify(e.dados)}\n`);
    }
    process.stdout.write(`\nPulsos (${pulsos.length}):\n`);
    for (const p of pulsos) {
      process.stdout.write(
        `  ${p.segundos.toFixed(1).padStart(6)}s  quadros=${String(p.dados.quadros).padStart(4)}`
        + `  resgates=${p.dados.resgates}  taxa=${Number(p.dados.taxaReal).toFixed(1)}`
        + `  amostras=${String(p.dados.amostras).padStart(4)}`
        + `  progresso=${Number(p.dados.progresso).toFixed(2)}`
        + `  trilha=${p.dados.trilha}  pronto=${p.dados.prontoDoVideo}\n`,
      );
    }
    process.stdout.write(`\nTela ao final: ${JSON.stringify(ultima)}\n\n`);

    if (problemas.length) {
      process.stdout.write(`Erros e avisos da página (${problemas.length}):` + NOVA_LINHA);
      for (const item of problemas.slice(0, 12)) {
        process.stdout.write(`  ${String(item).split(NOVA_LINHA)[0]}` + NOVA_LINHA);
      }
      process.stdout.write(NOVA_LINHA);
    }
    verificar('a página não lançou erro nem aviso', problemas.length === 0,
      problemas[0] ? String(problemas[0]).split(NOVA_LINHA)[0] : '');

    // ------------------------------------------------------------- asserções
    verificar('a câmera abriu', contar(eventos, 'camera.aberta') >= 1);

    if (comExposicaoMaxima) {
      const ajuste = eventos.find((e) => e.evento === 'exposicao.ajustada');
      verificar('o aplicativo encurtou a exposição em vez de reabrir a câmera',
        Boolean(ajuste), 'nenhum evento exposicao.ajustada');
      if (ajuste) {
        process.stdout.write(
          `exposição: ${ajuste.dados.de} -> ${ajuste.dados.para} `
          + `(teto ${ajuste.dados.teto}, ${ajuste.dados.passos} passos), `
          + `taxa medida ${ajuste.dados.taxa}` + NOVA_LINHA + NOVA_LINHA,
        );
        /*
          A asserção forte é sobre a exposição e não sobre a taxa medida.

          A taxa medida é a parte frágil: depende de o navegador estar compondo
          quadro do elemento, e sem interface ele às vezes não está. A exposição
          ficar abaixo do teto é a condição que **causa** a taxa, vem da câmera
          na hora, e não tem como dar indefinida.
        */
        verificar('a exposição desceu até o teto da taxa mínima',
          Number(ajuste.dados.para) <= Number(ajuste.dados.teto),
          `ficou em ${ajuste.dados.para}, teto ${ajuste.dados.teto}`);
        verificar('e desceu bastante em relação ao que estava',
          Number(ajuste.dados.para) <= Number(ajuste.dados.de) / 2,
          `de ${ajuste.dados.de} para ${ajuste.dados.para}`);
      }

      const ultimo = pulsos[pulsos.length - 1];
      const primeiro = pulsos[0];
      if (ultimo && primeiro && ultimo.segundos > primeiro.segundos) {
        const taxaReal = (ultimo.dados.quadros - primeiro.dados.quadros)
          / (ultimo.segundos - primeiro.segundos);
        verificar('e a captura de fato roda acima do mínimo',
          taxaReal >= 15, `${taxaReal.toFixed(1)} quadros por segundo`);
      }
    }
    verificar('a medição começou uma vez só, sem reabrir sozinha',
      contar(eventos, 'medicao.inicio') === 1,
      `${contar(eventos, 'medicao.inicio')} inícios`);
    verificar('nenhuma descida de resolução',
      contar(eventos, 'degrau.descida') === 0,
      `${contar(eventos, 'degrau.descida')} descidas`);
    verificar('a trilha não foi silenciada nem encerrada',
      contar(eventos, 'trilha.mute') + contar(eventos, 'trilha.ended') === 0);
    verificar('a captura não precisou de resgate',
      contar(eventos, 'captura.resgate') === 0,
      `${contar(eventos, 'captura.resgate')} resgates`);

    verificar('houve pulsação de diagnóstico', pulsos.length >= 5, `${pulsos.length} pulsos`);
    if (pulsos.length >= 2) {
      const paradas = [];
      for (let i = 1; i < pulsos.length; i++) {
        if (pulsos[i].dados.quadros <= pulsos[i - 1].dados.quadros) {
          paradas.push(pulsos[i].segundos.toFixed(1));
        }
      }
      verificar('o contador de quadros nunca para',
        paradas.length === 0, `parou em ${paradas.join(', ')}s`);

      const primeiro = pulsos[0];
      const ultimo = pulsos[pulsos.length - 1];
      const esperados = 18 * (ultimo.segundos - primeiro.segundos);
      verificar('chegou quadro perto da taxa pedida',
        ultimo.dados.quadros - primeiro.dados.quadros >= esperados * 0.7,
        `${ultimo.dados.quadros - primeiro.dados.quadros} quadros em `
        + `${(ultimo.segundos - primeiro.segundos).toFixed(1)}s`);
      verificar('o vídeo nunca ficou pausado',
        pulsos.every((p) => String(p.dados.videoPausado) === 'false'));
      verificar('a trilha ficou viva o tempo todo',
        pulsos.every((p) => p.dados.trilha === 'live'),
        [...new Set(pulsos.map((p) => p.dados.trilha))].join(','));
    }

    if (comVideo) {
      // O navegador normaliza a largura: escrevemos "100.0%" e ele guarda
      // "100%". Comparar texto cru daria falso negativo eterno.
      verificar('a barra de progresso completou',
        Number.parseFloat(ultima.progresso) >= 99.9, `ficou em ${ultima.progresso}`);
      const bpm = Number(ultima.bpm);
      verificar('a página achou a frequência gravada no vídeo',
        Number.isFinite(bpm) && Math.abs(bpm - BPM_DO_VIDEO) <= TOLERANCIA_BPM,
        `esperado ${BPM_DO_VIDEO} ± ${TOLERANCIA_BPM}, mostrou ${ultima.bpm}`);
      verificar('e contou mais de uma janela',
        Number(ultima.janelas) >= 2, `janelas=${ultima.janelas}`);
    }
  } finally {
    await navegador.fechar();
    await servidor.fechar();
  }
}

principal().then(() => {
  process.stdout.write(`${'-'.repeat(64)}\n`);
  if (falharam) {
    process.stdout.write(`FALHAS (${falharam}):\n`);
    falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
  }
  process.stdout.write(`navegador: ${passaram} passaram, ${falharam} falharam\n`);
  process.exit(falharam ? 1 : 0);
}).catch((erro) => {
  process.stdout.write(`\nERRO: ${erro.stack || erro.message}\n`);
  process.exit(1);
});
