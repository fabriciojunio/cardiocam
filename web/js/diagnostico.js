/**
 * Diagnóstico de câmera: colhe o dado em vez de supor a causa.
 *
 * Existe por causa de um caso concreto. A página principal falhou com
 * `NotReadableError` num computador em que o OpenCV, fora do navegador, lia das
 * duas câmeras sem problema. A mensagem de erro afirmava que outro programa
 * estava com a câmera aberta, e isso era falso. A partir dali havia duas
 * hipóteses plausíveis e nenhum dado para escolher entre elas:
 *
 * - o navegador estava sempre resolvendo para a mesma câmera, a padrão dele, e
 *   era justamente essa que falhava;
 * - alguma outra coisa, de permissão ou de driver, impedia as duas.
 *
 * Esta página separa as duas. Ela abre **cada dispositivo por identificador**,
 * um por vez, e relata por dispositivo: se abriu, se entregou imagem de fato,
 * em que resolução e a que taxa, e o nome exato do erro quando falhou.
 *
 * ## Por que "abriu" não basta
 *
 * `getUserMedia` resolver não quer dizer que chega imagem. O caso clássico é o
 * dispositivo aceitar a reserva e nunca produzir quadro, e aí a página fica
 * esperando um vídeo que não vem. Por isso cada teste espera o primeiro quadro
 * de verdade e mede quantos chegaram num intervalo, em vez de confiar na
 * promessa resolvida.
 */

const $ = (id) => document.getElementById(id);

const PRAZO_DE_ABERTURA_MS = 8000;
const JANELA_DE_CONTAGEM_MS = 1200;

const el = {
  btnRodar: $('btnRodar'),
  btnCopiar: $('btnCopiar'),
  estado: $('estado'),
  tabelaAmbiente: $('tabelaAmbiente'),
  tabelaCameras: $('tabelaCameras'),
  semCameras: $('semCameras'),
  previa: $('previa'),
  legendaPrevia: $('legendaPrevia'),
  saida: $('saida'),
};

function dizer(texto, classe = '') {
  el.estado.textContent = texto;
  el.estado.className = `estado ${classe}`;
}

function escapar(texto) {
  return String(texto)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Pede um dispositivo com prazo.
 *
 * O prazo existe porque `getUserMedia` pode simplesmente não responder quando
 * o dispositivo está num estado ruim, e sem prazo o diagnóstico trava no
 * primeiro problema, que é exatamente o que ele deveria diagnosticar.
 */
function pedirComPrazo(restricoes, prazoMs = PRAZO_DE_ABERTURA_MS) {
  let desistiu = false;
  const pedido = navigator.mediaDevices.getUserMedia({ video: restricoes, audio: false });

  pedido
    .then((atrasado) => {
      if (desistiu) atrasado.getTracks().forEach((t) => t.stop());
    })
    .catch(() => {});

  return Promise.race([
    pedido,
    espera(prazoMs).then(() => {
      desistiu = true;
      const erro = new Error(`Sem resposta em ${prazoMs / 1000} s.`);
      erro.name = 'TimeoutError';
      throw erro;
    }),
  ]);
}

/**
 * Conta quadros de verdade durante uma janela de tempo.
 *
 * `requestVideoFrameCallback` conta quadro apresentado, que é a medida certa.
 * Onde ele não existe, a reserva é comparar `currentTime` no começo e no fim,
 * que diz se o vídeo andou mesmo sem dizer quantos quadros foram.
 */
async function contarQuadros(video, janelaMs = JANELA_DE_CONTAGEM_MS) {
  if (typeof video.requestVideoFrameCallback === 'function') {
    let quadros = 0;
    let parar = false;
    const passo = () => {
      if (parar) return;
      quadros += 1;
      video.requestVideoFrameCallback(passo);
    };
    video.requestVideoFrameCallback(passo);
    await espera(janelaMs);
    parar = true;
    return { quadros, fps: (quadros / janelaMs) * 1000, metodo: 'contagem de quadro apresentado' };
  }

  const inicio = video.currentTime;
  await espera(janelaMs);
  const avancou = video.currentTime - inicio;
  return {
    quadros: avancou > 0 ? -1 : 0,
    fps: NaN,
    metodo: avancou > 0 ? 'o tempo do vídeo avançou' : 'o tempo do vídeo não avançou',
  };
}

/** Testa um dispositivo e devolve o que aconteceu com ele. */
async function testarDispositivo(dispositivo, indice) {
  const nome = dispositivo.label || `câmera ${indice + 1} (sem nome)`;
  const resultado = {
    nome,
    id: dispositivo.deviceId ? `${dispositivo.deviceId.slice(0, 12)}…` : '(sem id)',
    abriu: false,
    entregouImagem: false,
    resolucao: '',
    fps: '',
    detalhe: '',
    fluxo: null,
  };

  let fluxo = null;
  try {
    fluxo = await pedirComPrazo({ deviceId: { exact: dispositivo.deviceId } });
    resultado.abriu = true;
  } catch (erro) {
    resultado.detalhe = `${erro?.name || 'Erro'}: ${erro?.message || 'sem mensagem'}`;
    return resultado;
  }

  const video = document.createElement('video');
  video.playsInline = true;
  video.muted = true;
  video.srcObject = fluxo;

  try {
    await video.play();
    if (!video.videoWidth) {
      await Promise.race([
        new Promise((r) => video.addEventListener('loadeddata', r, { once: true })),
        espera(4000),
      ]);
    }

    if (!video.videoWidth) {
      resultado.detalhe = 'Abriu e não entregou nenhuma imagem em 4 s.';
      fluxo.getTracks().forEach((t) => t.stop());
      return resultado;
    }

    resultado.entregouImagem = true;
    resultado.resolucao = `${video.videoWidth}x${video.videoHeight}`;

    const contagem = await contarQuadros(video);
    resultado.fps = Number.isFinite(contagem.fps)
      ? `${contagem.fps.toFixed(1)}`
      : contagem.metodo;

    const ajustes = fluxo.getVideoTracks()[0]?.getSettings?.() || {};
    const partes = [];
    if (ajustes.frameRate) partes.push(`taxa pedida ${Math.round(ajustes.frameRate)}`);
    if (ajustes.facingMode) partes.push(`lado ${ajustes.facingMode}`);
    resultado.detalhe = partes.join(', ') || 'sem detalhe adicional';
    resultado.fluxo = fluxo;
    return resultado;
  } catch (erro) {
    resultado.detalhe = `${erro?.name || 'Erro'}: ${erro?.message || 'sem mensagem'}`;
    fluxo.getTracks().forEach((t) => t.stop());
    return resultado;
  }
}

function montarAmbiente() {
  const linhas = [
    ['Endereço', location.origin],
    ['Contexto seguro', window.isSecureContext ? 'sim' : 'NÃO (câmera exige https)'],
    ['Navegador', navigator.userAgent],
    ['Plataforma', navigator.platform || 'não informada'],
    ['getUserMedia', navigator.mediaDevices?.getUserMedia ? 'disponível' : 'AUSENTE'],
    ['getDisplayMedia', navigator.mediaDevices?.getDisplayMedia ? 'disponível' : 'ausente'],
    ['Núcleos de CPU', navigator.hardwareConcurrency || 'não informado'],
  ];
  el.tabelaAmbiente.innerHTML = linhas
    .map(([k, v]) => `<tr><th>${escapar(k)}</th><td class="mono">${escapar(v)}</td></tr>`)
    .join('');
  return linhas;
}

async function consultarPermissao() {
  try {
    const estado = await navigator.permissions.query({ name: 'camera' });
    return estado.state;
  } catch {
    return 'o navegador não informa';
  }
}

async function rodar() {
  el.btnRodar.disabled = true;
  el.btnCopiar.disabled = true;
  dizer('Rodando…');

  const ambiente = montarAmbiente();

  if (!navigator.mediaDevices?.getUserMedia) {
    dizer('Este navegador não expõe câmera para páginas. Use https e um navegador atual.', 'erro');
    el.btnRodar.disabled = false;
    return;
  }

  const permissao = await consultarPermissao();

  /*
    Um pedido genérico antes de enumerar, de propósito.

    Sem permissão concedida, `enumerateDevices` devolve entradas sem nome e sem
    identificador, e aí não há como testar dispositivo por dispositivo. Este
    pedido serve só para destravar a lista; se ele falhar, seguimos assim mesmo,
    porque a falha dele já é um dado.
  */
  let erroDoPedidoGenerico = '';
  try {
    const inicial = await pedirComPrazo(true);
    inicial.getTracks().forEach((t) => t.stop());
    await espera(200);
  } catch (erro) {
    erroDoPedidoGenerico = `${erro?.name || 'Erro'}: ${erro?.message || ''}`;
  }

  let dispositivos = [];
  try {
    dispositivos = (await navigator.mediaDevices.enumerateDevices())
      .filter((d) => d.kind === 'videoinput');
  } catch (erro) {
    erroDoPedidoGenerico += ` | enumerateDevices falhou: ${erro?.message || erro}`;
  }

  const resultados = [];
  for (let i = 0; i < dispositivos.length; i++) {
    dizer(`Testando câmera ${i + 1} de ${dispositivos.length}…`);
    // Pausa entre dispositivos: o sistema não libera o anterior na hora, e
    // testar imediatamente pegaria o próximo ainda com o anterior ocupado,
    // produzindo uma falha que seria do teste e não do dispositivo.
    if (i > 0) await espera(600);
    resultados.push(await testarDispositivo(dispositivos[i], i));
  }

  // Mostra a prévia da primeira que funcionou, e encerra as demais.
  let previaMostrada = false;
  for (const r of resultados) {
    if (r.fluxo && !previaMostrada) {
      el.previa.srcObject = r.fluxo;
      el.previa.play().catch(() => {});
      el.legendaPrevia.textContent = `${r.nome}, ${r.resolucao}`;
      previaMostrada = true;
    } else if (r.fluxo) {
      r.fluxo.getTracks().forEach((t) => t.stop());
    }
  }
  if (!previaMostrada) el.legendaPrevia.textContent = 'Nenhuma câmera entregou imagem.';

  // Tabela
  if (resultados.length === 0) {
    el.semCameras.textContent = 'O navegador não enumerou nenhuma câmera.';
    el.tabelaCameras.hidden = true;
  } else {
    el.semCameras.hidden = true;
    el.tabelaCameras.hidden = false;
    el.tabelaCameras.querySelector('tbody').innerHTML = resultados
      .map((r) => `<tr>
        <td>${escapar(r.nome)}<br><span class="fraco mono">${escapar(r.id)}</span></td>
        <td class="${r.abriu ? 'ok' : 'falha'}">${r.abriu ? 'sim' : 'não'}</td>
        <td class="${r.entregouImagem ? 'ok' : 'falha'}">${r.entregouImagem ? 'sim' : 'não'}</td>
        <td class="mono">${escapar(r.resolucao || '-')}</td>
        <td class="mono">${escapar(r.fps || '-')}</td>
        <td class="mono">${escapar(r.detalhe)}</td>
      </tr>`)
      .join('');
  }

  const funcionaram = resultados.filter((r) => r.entregouImagem).length;
  const conclusao = resultados.length === 0
    ? 'O navegador não enumerou câmera nenhuma. É permissão do sistema, driver ou ausência de dispositivo.'
    : funcionaram === resultados.length
      ? 'Todas as câmeras funcionam neste navegador. Se a medição falhou, o problema não é o dispositivo.'
      : funcionaram === 0
        ? 'Nenhuma câmera entregou imagem. Confira permissão do sistema para o navegador, e se algum programa está com a câmera aberta.'
        : `${funcionaram} de ${resultados.length} funcionam. Escolha uma que funcionou no seletor da página de medição.`;

  const texto = [
    'DIAGNOSTICO DE CAMERA, CARDIOCAM',
    new Date().toISOString(),
    '',
    'AMBIENTE',
    ...ambiente.map(([k, v]) => `  ${k}: ${v}`),
    `  Permissao de camera: ${permissao}`,
    erroDoPedidoGenerico ? `  Pedido generico: ${erroDoPedidoGenerico}` : '  Pedido generico: ok',
    '',
    `CAMERAS (${resultados.length})`,
    ...resultados.flatMap((r, i) => [
      `  ${i + 1}. ${r.nome}  [${r.id}]`,
      `     abriu: ${r.abriu ? 'sim' : 'nao'}   entregou imagem: ${r.entregouImagem ? 'sim' : 'nao'}`,
      `     resolucao: ${r.resolucao || '-'}   quadros por segundo: ${r.fps || '-'}`,
      `     detalhe: ${r.detalhe}`,
    ]),
    '',
    'CONCLUSAO',
    `  ${conclusao}`,
  ].join('\n');

  el.saida.textContent = texto;
  el.btnCopiar.disabled = false;
  el.btnRodar.disabled = false;
  dizer(conclusao, funcionaram === 0 ? 'erro' : funcionaram < resultados.length ? 'alerta' : '');
}

el.btnRodar.addEventListener('click', () => {
  rodar().catch((erro) => {
    dizer(`O diagnóstico falhou: ${erro?.message || erro}`, 'erro');
    el.btnRodar.disabled = false;
  });
});

el.btnCopiar.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(el.saida.textContent);
    el.btnCopiar.textContent = 'Copiado';
    setTimeout(() => { el.btnCopiar.textContent = 'Copiar resultado'; }, 1500);
  } catch {
    // Área de transferência bloqueada: selecionar o texto resolve, e dizer
    // isso é melhor que um botão que não faz nada.
    const faixa = document.createRange();
    faixa.selectNodeContents(el.saida);
    const selecao = window.getSelection();
    selecao.removeAllRanges();
    selecao.addRange(faixa);
    dizer('Não consegui copiar sozinho. O texto já está selecionado: use Ctrl+C.', 'alerta');
  }
});

montarAmbiente();
