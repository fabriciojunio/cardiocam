/**
 * Confere que trocar de resolução na trilha viva não derruba a câmera.
 *
 * É a outra metade da correção do ADR 6. A primeira metade tirou a resolução da
 * lista de suspeitas; esta garante que, quando ela de fato precisar mudar, a
 * mudança seja feita com `applyConstraints` na trilha que já está aberta, e não
 * fechando e reabrindo o dispositivo.
 *
 * A diferença entre as duas é o que o usuário via: reabrir apaga e acende a luz
 * da webcam, some com a imagem por cerca de um segundo, e zera a janela de
 * coleta. `applyConstraints` troca o formato sem que a trilha saia do estado
 * `live`, sem disparar `mute` nem `ended`, e sem perder a identidade do
 * dispositivo.
 *
 * O teste cobra as quatro coisas, porque "funcionou" aqui quer dizer
 * exatamente isso: a resolução mudou **e** nada mais mudou.
 *
 * Uso:
 *   node testes/navegador/medir_troca_de_resolucao.mjs
 */

import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrirAba, abrirNavegador, acharNavegador } from './cdp.mjs';
import { servir } from './servidor.mjs';

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) { passaram++; return; }
  falharam++;
  falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
}

async function principal() {
  const executavel = acharNavegador();
  if (!executavel) throw new Error('nenhum Chromium encontrado');

  const servidor = await servir(join(dirname(fileURLToPath(import.meta.url)), '..', '..'));
  const navegador = await abrirNavegador({ executavel, argumentos: [] });

  try {
    const aba = await abrirAba(navegador.sessao, `${servidor.url}/testes/navegador/vazio.html`);

    const r = await aba.avaliar(`(async () => {
      const fluxo = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      const trilha = fluxo.getVideoTracks()[0];
      const eventos = [];
      for (const nome of ['mute', 'unmute', 'ended']) {
        trilha.addEventListener(nome, () => eventos.push(nome));
      }

      const video = document.createElement('video');
      video.srcObject = fluxo;
      video.muted = true;
      await video.play();

      // Deixa a captura andar antes de mexer, para a troca cair no meio de uma
      // sequência de quadros e não na abertura.
      const contar = (ms) => new Promise((pronto) => {
        let n = 0;
        const inicio = performance.now();
        const passo = () => {
          n += 1;
          if (performance.now() - inicio < ms) video.requestVideoFrameCallback(passo);
          else pronto(n);
        };
        if (typeof video.requestVideoFrameCallback === 'function') {
          video.requestVideoFrameCallback(passo);
        } else { setTimeout(() => pronto(0), ms); }
      });

      const antes = trilha.getSettings();
      const quadrosAntes = await contar(2000);
      const idAntes = antes.deviceId;

      const marcaDaTroca = performance.now();
      await trilha.applyConstraints({
        width: { ideal: 1280 }, height: { ideal: 720 },
        frameRate: { ideal: 20, max: 24 },
      });
      const custoMs = performance.now() - marcaDaTroca;

      const quadrosDepois = await contar(2000);
      const depois = trilha.getSettings();
      const estado = trilha.readyState;
      const mudo = trilha.muted;

      fluxo.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
      return {
        antes: antes.width + 'x' + antes.height,
        depois: depois.width + 'x' + depois.height,
        idIgual: idAntes === depois.deviceId,
        estado, mudo, eventos, custoMs,
        quadrosAntes, quadrosDepois,
      };
    })()`);

    process.stdout.write(`resolução: ${r.antes} -> ${r.depois}\n`);
    process.stdout.write(`a troca levou ${r.custoMs.toFixed(0)} ms\n`);
    process.stdout.write(`quadros em 2 s: ${r.quadrosAntes} antes, ${r.quadrosDepois} depois\n`);
    process.stdout.write(`trilha: ${r.estado}, muda=${r.mudo}, eventos=[${r.eventos.join(',')}]\n\n`);

    verificar('a resolução mudou de fato', r.antes !== r.depois, `${r.antes} -> ${r.depois}`);
    verificar('a trilha continua viva', r.estado === 'live', r.estado);
    verificar('e não foi silenciada', r.mudo === false);
    verificar('nenhum evento de interrupção foi disparado',
      r.eventos.length === 0, r.eventos.join(','));
    verificar('é o mesmo dispositivo', r.idIgual);
    verificar('a troca é rápida', r.custoMs < 1500, `${r.custoMs.toFixed(0)} ms`);
    verificar('e os quadros continuam chegando depois dela',
      r.quadrosDepois >= Math.max(8, r.quadrosAntes * 0.6),
      `${r.quadrosAntes} antes, ${r.quadrosDepois} depois`);
  } finally {
    await navegador.fechar();
    await servidor.fechar();
  }
}

principal().then(() => {
  process.stdout.write(`${'-'.repeat(62)}\n`);
  if (falharam) {
    process.stdout.write(`FALHAS (${falharam}):\n`);
    falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
  }
  process.stdout.write(`troca de resolução: ${passaram} passaram, ${falharam} falharam\n`);
  process.exit(falharam ? 1 : 0);
}).catch((erro) => {
  process.stdout.write(`ERRO: ${erro.stack || erro.message}\n`);
  process.exit(1);
});
