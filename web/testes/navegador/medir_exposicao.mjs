/**
 * Mede o que a exposição faz com a taxa de quadros entregue.
 *
 * A medição de resolução já tinha eliminado banda e máquina: a câmera entregou
 * oito quadros por segundo igualmente em 1920x1080 e em 320x240, e nenhuma
 * dessas duas causas se comporta assim. Sobra a exposição, e a física é direta:
 * a câmera não pode entregar um quadro antes de terminar de expô-lo, então
 * integrar por 125 ms limita a entrega a oito por segundo, qualquer que seja o
 * tamanho do quadro.
 *
 * Este programa confirma ou derruba isso medindo a taxa com a exposição no
 * automático e depois presa em valores cada vez mais curtos.
 *
 * Uso:
 *   node testes/navegador/medir_exposicao.mjs
 */

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrirAba, abrirNavegador, acharNavegador } from './cdp.mjs';
import { servir } from './servidor.mjs';

const SEGUNDOS_POR_MEDIDA = 5;

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function principal() {
  const executavel = acharNavegador();
  if (!executavel) throw new Error('nenhum Chromium encontrado');

  const servidor = await servir(join(dirname(fileURLToPath(import.meta.url)), '..', '..'));
  const navegador = await abrirNavegador({ executavel, argumentos: [] });

  try {
    const aba = await abrirAba(navegador.sessao, `${servidor.url}/testes/navegador/vazio.html`);

    const capacidades = await aba.avaliar(`(async () => {
      const fluxo = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
      });
      const trilha = fluxo.getVideoTracks()[0];
      const capacidades = trilha.getCapabilities ? trilha.getCapabilities() : {};
      const ajustes = trilha.getSettings();
      fluxo.getTracks().forEach((t) => t.stop());
      return { rotulo: trilha.label, capacidades, ajustes };
    })()`);

    process.stdout.write(`câmera: ${capacidades.rotulo}\n\n`);
    process.stdout.write('O que a câmera diz saber fazer\n');
    for (const chave of ['exposureMode', 'exposureTime', 'frameRate', 'brightness', 'whiteBalanceMode']) {
      const valor = capacidades.capacidades[chave];
      process.stdout.write(`  ${chave.padEnd(18)} ${JSON.stringify(valor)}\n`);
    }
    process.stdout.write('\nComo ela estava ao abrir\n');
    for (const chave of ['exposureMode', 'exposureTime', 'frameRate', 'whiteBalanceMode']) {
      process.stdout.write(`  ${chave.padEnd(18)} ${JSON.stringify(capacidades.ajustes[chave])}\n`);
    }

    const faixa = capacidades.capacidades.exposureTime;
    const tempos = [];
    if (faixa && Number.isFinite(faixa.min) && Number.isFinite(faixa.max)) {
      const passo = faixa.step || 1;
      for (const fracao of [1, 0.5, 0.25, 0.12, 0.06, 0.03]) {
        const bruto = faixa.min + (faixa.max - faixa.min) * fracao;
        const valor = Math.max(faixa.min, Math.round(bruto / passo) * passo);
        if (!tempos.includes(valor)) tempos.push(valor);
      }
    }

    process.stdout.write(`\n${'exposição'.padEnd(22)}${'taxa medida'.padStart(12)}`
      + `${'luz do quadro'.padStart(16)}\n${'-'.repeat(52)}\n`);

    const cenarios = [
      { rotulo: 'automática', aplicar: null },
      ...tempos.map((t) => ({ rotulo: `manual, tempo ${t}`, aplicar: t })),
    ];

    for (const cenario of cenarios) {
      const r = await aba.avaliar(`(async () => {
        const fluxo = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
        });
        const trilha = fluxo.getVideoTracks()[0];
        let aviso = '';
        ${cenario.aplicar === null ? '' : `
        try {
          await trilha.applyConstraints({ advanced: [{ exposureMode: 'manual' }] });
          await trilha.applyConstraints({ advanced: [{ exposureTime: ${cenario.aplicar} }] });
        } catch (erro) { aviso = 'recusou: ' + erro.name; }
        `}
        const video = document.createElement('video');
        video.srcObject = fluxo;
        video.muted = true;
        await video.play();
        await new Promise((r) => setTimeout(r, 900));

        const marcas = [];
        await new Promise((pronto) => {
          const inicio = performance.now();
          const passo = (_a, dados) => {
            marcas.push(dados.mediaTime);
            if (performance.now() - inicio < ${SEGUNDOS_POR_MEDIDA} * 1000) {
              video.requestVideoFrameCallback(passo);
            } else { pronto(); }
          };
          video.requestVideoFrameCallback(passo);
          setTimeout(pronto, ${SEGUNDOS_POR_MEDIDA} * 1000 + 1500);
        });

        // Luminância média do quadro, pela mesma conversão que o aplicativo usa.
        const tela = document.createElement('canvas');
        tela.width = 64;
        tela.height = 48;
        const ctx = tela.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(video, 0, 0, 64, 48);
        const pixels = ctx.getImageData(0, 0, 64, 48).data;
        let soma = 0;
        for (let i = 0; i < pixels.length; i += 4) {
          soma += 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
        }
        const luz = soma / (pixels.length / 4);

        const ajustes = trilha.getSettings();
        fluxo.getTracks().forEach((t) => t.stop());
        video.srcObject = null;
        const duracao = marcas.length > 1 ? marcas[marcas.length - 1] - marcas[0] : 0;
        return {
          taxa: duracao > 0 ? (marcas.length - 1) / duracao : 0,
          luz,
          aviso,
          tempoFinal: ajustes.exposureTime,
          modoFinal: ajustes.exposureMode,
        };
      })()`);

      process.stdout.write(
        `${cenario.rotulo.padEnd(22)}${r.taxa.toFixed(1).padStart(12)}`
        + `${r.luz.toFixed(0).padStart(16)}   `
        + `(ficou em ${r.modoFinal}/${r.tempoFinal}) ${r.aviso}\n`,
      );
      await espera(600);
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
