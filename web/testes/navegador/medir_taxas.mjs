/**
 * Mede a taxa de quadros que a câmera entrega de fato, em cada resolução.
 *
 * Existe porque a taxa que a câmera **declara** e a que ela **entrega** são
 * coisas diferentes, e o sistema estava confiando na primeira. Numa EMEET
 * SmartCam S600 ligada por USB, `getSettings()` diz 20 quadros por segundo em
 * 1920x1080 e chegam sete. A conta explica: 1920x1080 sem compressão são dois
 * bytes por pixel, e vinte desses por segundo pedem 83 MB/s, que não cabem nos
 * 60 MB/s úteis de uma porta USB 2.0. A câmera não mente, ela negocia o que
 * cabe, e quem pergunta a taxa recebe a pedida e não a possível.
 *
 * Uso:
 *   node testes/navegador/medir_taxas.mjs
 */

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrirAba, abrirNavegador, acharNavegador } from './cdp.mjs';
import { servir } from './servidor.mjs';

const SEGUNDOS_POR_MEDIDA = 6;
const RESOLUCOES = [
  [1920, 1080],
  [1280, 720],
  [960, 540],
  [640, 480],
  [320, 240],
];
const TAXAS_PEDIDAS = [
  { rotulo: 'teto 24', restricao: { ideal: 20, max: 24 } },
  { rotulo: 'sem teto', restricao: undefined },
];

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function principal() {
  const executavel = acharNavegador();
  if (!executavel) throw new Error('nenhum Chromium encontrado');
  /*
    A página precisa vir de um servidor, e nao de `about:blank`.

    `navigator.mediaDevices` so existe em contexto seguro, e `about:blank` nao e
    um. Como `127.0.0.1` conta como seguro, servir a propria pasta do site
    resolve sem certificado nenhum.
  */
  const servidor = await servir(join(dirname(fileURLToPath(import.meta.url)), '..', '..'));
  const navegador = await abrirNavegador({ executavel, argumentos: [] });

  try {
    const aba = await abrirAba(navegador.sessao, `${servidor.url}/testes/navegador/vazio.html`);
    process.stdout.write(
      `${'resolução'.padEnd(12)}${'taxa pedida'.padEnd(13)}`
      + `${'entregue'.padStart(10)}${'medida'.padStart(10)}  ajustes\n`,
    );
    process.stdout.write(`${'-'.repeat(78)}\n`);

    for (const [largura, altura] of RESOLUCOES) {
      for (const { rotulo, restricao } of TAXAS_PEDIDAS) {
        const resultado = await aba.avaliar(`(async () => {
          const restricoes = {
            width: { ideal: ${largura} },
            height: { ideal: ${altura} },
            ${restricao ? `frameRate: ${JSON.stringify(restricao)},` : ''}
          };
          let fluxo = null;
          try {
            fluxo = await navigator.mediaDevices.getUserMedia({ video: restricoes });
          } catch (erro) {
            return { erro: erro.name + ': ' + erro.message };
          }
          const video = document.createElement('video');
          video.srcObject = fluxo;
          video.muted = true;
          await video.play();

          const tempos = [];
          await new Promise((pronto) => {
            const passo = (_agora, dados) => {
              tempos.push(dados.mediaTime);
              if (tempos.length < ${SEGUNDOS_POR_MEDIDA} * 60 &&
                  performance.now() - inicio < ${SEGUNDOS_POR_MEDIDA} * 1000) {
                video.requestVideoFrameCallback(passo);
              } else {
                pronto();
              }
            };
            const inicio = performance.now();
            video.requestVideoFrameCallback(passo);
            setTimeout(pronto, ${SEGUNDOS_POR_MEDIDA} * 1000 + 1500);
          });

          const trilha = fluxo.getVideoTracks()[0];
          const ajustes = trilha.getSettings();
          fluxo.getTracks().forEach((t) => t.stop());
          video.srcObject = null;

          const duracao = tempos.length > 1 ? tempos[tempos.length - 1] - tempos[0] : 0;
          return {
            quadros: tempos.length,
            duracao,
            medida: duracao > 0 ? (tempos.length - 1) / duracao : 0,
            largura: ajustes.width,
            altura: ajustes.height,
            declarada: ajustes.frameRate,
          };
        })()`);

        if (resultado.erro) {
          process.stdout.write(
            `${`${largura}x${altura}`.padEnd(12)}${rotulo.padEnd(13)}`
            + `${'-'.padStart(10)}${'-'.padStart(10)}  ${resultado.erro}\n`,
          );
        } else {
          process.stdout.write(
            `${`${largura}x${altura}`.padEnd(12)}${rotulo.padEnd(13)}`
            + `${Number(resultado.declarada).toFixed(0).padStart(10)}`
            + `${resultado.medida.toFixed(1).padStart(10)}`
            + `  entregou ${resultado.largura}x${resultado.altura}`
            + ` (${resultado.quadros} quadros em ${resultado.duracao.toFixed(1)} s)\n`,
          );
        }
        // O sistema não solta o dispositivo na hora depois de um stop.
        await espera(600);
      }
    }
  } finally {
    await navegador.fechar();
    await servidor.fechar();
  }
}

principal().catch((erro) => {
  process.stdout.write(`ERRO: ${erro.stack || erro.message}\n`);
  process.exit(1);
});
