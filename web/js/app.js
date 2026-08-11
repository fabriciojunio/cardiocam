/**
 * Amarra a interface ao medidor.
 *
 * Nenhuma lógica de sinal mora aqui: este arquivo só liga botões, desenha os
 * gráficos e conversa com o armazenamento local.
 */

import { confiancaDe } from './dsp.js';
import { Medidor, analisarVideo, BPM_MAXIMO, BPM_MINIMO } from './medidor.js';
import {
  baixarCsv,
  limparTudo,
  listarMedicoes,
  listarPessoas,
  removerMedicao,
  salvarMedicao,
} from './armazenamento.js';

const $ = (id) => document.getElementById(id);

const el = {
  video: $('video'),
  canvas: $('canvasOculto'),
  palco: $('palco'),
  palcoVazio: $('palcoVazio'),
  guia: $('guia'),
  barra: $('barraProgresso').querySelector('i'),
  estado: $('estado'),
  bpm: $('bpm'),
  selo: $('selo'),
  snr: $('dadoSnr'),
  janelasLidas: $('dadoJanelas'),
  dispersao: $('dadoDispersao'),
  fps: $('dadoFps'),
  onda: $('canvasOnda'),
  espectro: $('canvasEspectro'),
  btnIniciar: $('btnIniciar'),
  btnParar: $('btnParar'),
  btnSalvar: $('btnSalvar'),
  btnCamera: $('btnFonteCamera'),
  btnDedo: $('btnFonteDedo'),
  btnArquivo: $('btnFonteArquivo'),
  dispositivo: $('dispositivo'),
  campoDispositivo: $('campoDispositivo'),
  palcoLeitura: $('palcoLeitura'),
  bpmPalco: $('bpmPalco'),
  seloPalco: $('seloPalco'),
  arquivo: $('arquivoVideo'),
  pessoa: $('pessoa'),
  observacao: $('observacao'),
  algoritmo: $('algoritmo'),
  janela: $('janela'),
  pessoasConhecidas: $('pessoasConhecidas'),
  tabela: $('tabelaHistorico').querySelector('tbody'),
  historicoVazio: $('historicoVazio'),
  contadorHistorico: $('contadorHistorico'),
  filtroPessoa: $('filtroPessoa'),
  resumoPessoa: $('resumoPessoa'),
  btnExportar: $('btnExportar'),
  btnLimpar: $('btnLimpar'),
};

let fonte = 'camera';
let fluxo = null;
let medidor = null;
let rodando = false;
let ultimoResultado = null;
let animacao = null;
let ultimaAnalise = 0;
let cancelado = false;
let abrindo = false;

// --------------------------------------------------------------- utilidades
function dizer(texto, tipo = '') {
  el.estado.textContent = texto;
  el.estado.className = `estado ${tipo}`;
}

function corDaConfianca(nivel) {
  return { alta: '#4ea87a', 'média': '#5b87a8', baixa: '#c8994a', descartada: '#b8544c' }[nivel] || '#8b938f';
}

function mostrarLeitura(bpm, snrDb, extras = {}) {
  const nivel = confiancaDe(snrDb);
  const texto = Number.isFinite(bpm) ? bpm.toFixed(0) : '--';
  const confiavel = nivel === 'alta' || nivel === 'média';

  el.bpm.textContent = texto;
  el.bpm.className = 'numerao ' + (confiavel ? 'viva' : 'duvidosa');
  el.selo.textContent = nivel;
  el.selo.dataset.nivel = nivel;

  // Cópia sobre o vídeo, para quem está se enquadrando não precisar rolar a
  // página até o painel.
  el.palcoLeitura.hidden = false;
  el.bpmPalco.textContent = texto;
  el.bpmPalco.className = confiavel ? '' : 'duvidosa';
  el.seloPalco.textContent = nivel;
  el.snr.textContent = Number.isFinite(snrDb) ? `${snrDb.toFixed(1)} dB` : '—';
  if (extras.janelas !== undefined) el.janelasLidas.textContent = extras.janelas;
  if (extras.dispersao !== undefined) {
    el.dispersao.textContent = Number.isFinite(extras.dispersao) ? `${extras.dispersao.toFixed(2)} bpm` : '—';
  }
  if (extras.fps !== undefined) el.fps.textContent = `${extras.fps.toFixed(1)} q/s`;
}

function limparLeitura() {
  el.bpm.textContent = '--';
  el.bpm.className = 'numerao';
  el.selo.textContent = 'aguardando';
  el.selo.dataset.nivel = 'vazio';
  el.palcoLeitura.hidden = true;
  el.snr.textContent = '—';
  el.janelasLidas.textContent = '—';
  el.dispersao.textContent = '—';
  el.fps.textContent = '—';
  desenharOnda([]);
  desenharEspectro([], null);
  el.barra.style.width = '0%';
}

// ------------------------------------------------------------------ gráficos
function prepararCanvas(canvas) {
  const escala = window.devicePixelRatio || 1;
  const caixa = canvas.getBoundingClientRect();
  if (caixa.width && canvas.width !== Math.round(caixa.width * escala)) {
    canvas.width = Math.round(caixa.width * escala);
    canvas.height = Math.round(caixa.height * escala);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(escala, 0, 0, escala, 0, 0);
  return { ctx, largura: canvas.width / escala, altura: canvas.height / escala };
}

function desenharOnda(sinal) {
  const { ctx, largura, altura } = prepararCanvas(el.onda);
  ctx.clearRect(0, 0, largura, altura);
  if (!sinal || sinal.length < 2) return;

  // Mostra os últimos segundos, que é o trecho que a pessoa reconhece como
  // "agora", em vez de comprimir a janela inteira.
  const trecho = sinal.slice(-Math.min(sinal.length, 400));
  let min = Infinity;
  let max = -Infinity;
  for (const v of trecho) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const amplitude = max - min || 1;
  const margem = 8;

  ctx.beginPath();
  ctx.strokeStyle = '#4ea87a';
  ctx.lineWidth = 1.4;
  ctx.lineJoin = 'round';
  trecho.forEach((v, i) => {
    const x = (i / (trecho.length - 1)) * largura;
    const y = altura - margem - ((v - min) / amplitude) * (altura - 2 * margem);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
}

function desenharEspectro(espectro, bpmMarcado) {
  const { ctx, largura, altura } = prepararCanvas(el.espectro);
  ctx.clearRect(0, 0, largura, altura);
  if (!espectro || espectro.length < 2) return;

  const maxPot = Math.max(...espectro.map((p) => p.potencia)) || 1;
  const margem = 6;

  ctx.beginPath();
  ctx.moveTo(0, altura);
  espectro.forEach((p, i) => {
    const x = (i / (espectro.length - 1)) * largura;
    const y = altura - margem - (p.potencia / maxPot) * (altura - 2 * margem);
    ctx.lineTo(x, y);
  });
  ctx.lineTo(largura, altura);
  ctx.closePath();
  ctx.fillStyle = 'rgba(91, 135, 168, .18)';
  ctx.fill();

  ctx.beginPath();
  espectro.forEach((p, i) => {
    const x = (i / (espectro.length - 1)) * largura;
    const y = altura - margem - (p.potencia / maxPot) * (altura - 2 * margem);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = '#5b87a8';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  if (Number.isFinite(bpmMarcado)) {
    const posicao = (bpmMarcado - BPM_MINIMO) / (BPM_MAXIMO - BPM_MINIMO);
    const x = Math.max(0, Math.min(1, posicao)) * largura;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, altura);
    ctx.strokeStyle = '#4ea87a';
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

// -------------------------------------------------------------------- câmera
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

const PRAZO_POR_TENTATIVA_MS = 6000;

/**
 * Pede a câmera com prazo.
 *
 * `getUserMedia` pode simplesmente nunca responder quando o dispositivo está
 * num estado ruim, e sem prazo a interface fica presa para sempre esperando uma
 * promessa que não chega. Se o prazo estourar mas a permissão for concedida
 * depois, o fluxo que chega atrasado precisa ser encerrado na hora, senão ele
 * continua segurando a câmera e faz todas as tentativas seguintes falharem.
 */
function pedirCamera(restricoes, prazoMs = PRAZO_POR_TENTATIVA_MS) {
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
      const erro = new Error('A câmera não respondeu a tempo.');
      erro.name = 'TimeoutError';
      throw erro;
    }),
  ]);
}

/**
 * Tenta abrir a câmera com exigências cada vez menores.
 *
 * A primeira tentativa pede a resolução e a taxa ideais para a medição. Muitas
 * webcams não conseguem entregar essa combinação e falham de formas variadas,
 * às vezes com o dispositivo chegando a ligar antes de recusar. Em vez de
 * desistir na primeira negativa, descemos as exigências até o mínimo aceitável,
 * que é simplesmente "uma câmera qualquer".
 *
 * A pausa entre tentativas existe porque o sistema operacional não libera o
 * dispositivo instantaneamente depois de uma falha, e uma nova tentativa
 * imediata pega o dispositivo ainda ocupado.
 */
async function abrirFluxo(idDispositivo) {
  const tentativas = [];

  // No modo dedo a câmera é a traseira, porque é do lado dela que fica a
  // lanterna, e sem lanterna não há transiluminação do tecido.
  if (fonte === 'dedo') {
    tentativas.push({ facingMode: { exact: 'environment' } });
    tentativas.push({ facingMode: 'environment' });
    tentativas.push(true);
    return await primeiraQueAbrir(tentativas);
  }

  if (idDispositivo) {
    tentativas.push({ deviceId: { exact: idDispositivo }, width: { ideal: 640 }, height: { ideal: 480 } });
    tentativas.push({ deviceId: { exact: idDispositivo } });
  }
  tentativas.push({
    facingMode: 'user',
    width: { ideal: 640 },
    height: { ideal: 480 },
    frameRate: { ideal: 30 },
  });
  tentativas.push({ width: { ideal: 640 }, height: { ideal: 480 } });
  tentativas.push({ facingMode: 'user' });
  tentativas.push(true);

  return await primeiraQueAbrir(tentativas);
}

async function primeiraQueAbrir(tentativas) {
  let ultimoErro = null;
  for (let i = 0; i < tentativas.length; i++) {
    if (cancelado) throw new Error('Medição cancelada.');
    try {
      dizer(`Abrindo a câmera… tentativa ${i + 1} de ${tentativas.length}.`);
      return await pedirCamera(tentativas[i]);
    } catch (erro) {
      ultimoErro = erro;
      // Permissão negada não melhora afrouxando exigência.
      if (erro?.name === 'NotAllowedError' || erro?.name === 'SecurityError') throw erro;
      await espera(300);
    }
  }
  throw ultimoErro ?? new Error('Não foi possível abrir a câmera.');
}

/** Liga a lanterna. Devolve se conseguiu. */
async function ligarLanterna() {
  try {
    const trilha = fluxo?.getVideoTracks?.()[0];
    if (!trilha?.getCapabilities) return false;
    if (!trilha.getCapabilities().torch) return false;
    await trilha.applyConstraints({ advanced: [{ torch: true }] });
    return true;
  } catch {
    return false;
  }
}

async function listarCameras() {
  try {
    const dispositivos = await navigator.mediaDevices.enumerateDevices();
    return dispositivos.filter((d) => d.kind === 'videoinput');
  } catch {
    return [];
  }
}

async function atualizarListaDeCameras() {
  const cameras = await listarCameras();
  if (cameras.length <= 1 || !el.dispositivo) {
    if (el.campoDispositivo) el.campoDispositivo.hidden = true;
    return;
  }
  const atual = el.dispositivo.value;
  el.dispositivo.innerHTML = cameras
    .map((c, i) => `<option value="${c.deviceId}">${c.label || `Câmera ${i + 1}`}</option>`)
    .join('');
  if (atual) el.dispositivo.value = atual;
  el.campoDispositivo.hidden = false;
}

async function iniciarCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      'Este navegador não expõe a câmera. Use Chrome, Edge, Safari ou Firefox ' +
      'atualizados, e um endereço https.',
    );
  }

  // Garante que nada nosso ainda esteja segurando o dispositivo.
  pararCamera();
  await espera(120);

  fluxo = await abrirFluxo(el.dispositivo?.value || null);
  el.video.srcObject = fluxo;
  el.video.muted = true;

  await el.video.play();

  // Esperar o primeiro quadro de verdade. O play resolve antes de haver
  // imagem, e sem isso o laço começaria a medir um vídeo de largura zero.
  if (!el.video.videoWidth) {
    await new Promise((resolve, reject) => {
      const pronto = () => resolve();
      el.video.addEventListener('loadeddata', pronto, { once: true });
      setTimeout(
        () => (el.video.videoWidth ? resolve() : reject(new Error(
          'A câmera abriu mas não entregou nenhuma imagem. Costuma ser outro ' +
          'programa usando a câmera ao mesmo tempo.',
        ))),
        4000,
      );
    });
  }

  const trilha = fluxo.getVideoTracks()[0];
  const ajustes = trilha?.getSettings?.() ?? {};
  await travarAjustesAutomaticos();
  await atualizarListaDeCameras();
  return ajustes;
}

/**
 * Tenta fixar exposição e balanço de branco.
 *
 * É o ajuste de câmera que mais afeta a medição. Os dois controles trabalham
 * contra o que queremos medir: quando a pele escurece por causa do pulso, a
 * exposição automática clareia a imagem e apaga parte do sinal; e o balanço de
 * branco automático mexe no ganho de cada canal separadamente, criando uma
 * variação de cor que os métodos cromáticos não cancelam.
 *
 * Poucos navegadores expõem esses controles, e em desktop quase nenhum. Quando
 * não dá, a rectificação por referência de fundo cobre boa parte do problema.
 */
async function travarAjustesAutomaticos() {
  try {
    const trilha = fluxo?.getVideoTracks?.()[0];
    if (!trilha?.getCapabilities) return false;
    const capacidades = trilha.getCapabilities();
    const avancado = [];
    if (capacidades.exposureMode?.includes('manual')) avancado.push({ exposureMode: 'manual' });
    if (capacidades.whiteBalanceMode?.includes('manual')) {
      avancado.push({ whiteBalanceMode: 'manual' });
    }
    if (!avancado.length) return false;
    await trilha.applyConstraints({ advanced: avancado });
    return true;
  } catch {
    // Falhar aqui é rotina e não deve interromper a medição.
    return false;
  }
}

function pararCamera() {
  if (fluxo) {
    fluxo.getTracks().forEach((t) => t.stop());
    fluxo = null;
  }
  el.video.srcObject = null;
  el.video.removeAttribute('src');
  // Sem isto o elemento continua exibindo o último quadro recebido, e o aviso
  // de "câmera ainda não iniciada" aparece por cima de uma imagem congelada.
  el.video.load();
  el.palcoLeitura.hidden = true;
}

/* A opção de deixar a tela branca para iluminar o rosto foi retirada.
   Ela partia da suposição de que faltava luz, e a medição no sinal real
   mostrou que não era esse o problema: com iluminação boa, a amplitude na
   banda cardíaca continuou igual ou abaixo do ruído de banda larga. Mais luz
   não resolve o que a própria câmera introduz. Manter o botão só daria a
   impressão de que existe um ajuste capaz de salvar a medição. */

function laco() {
  if (!rodando) return;
  animacao = requestAnimationFrame(laco);

  const video = el.video;
  if (!video.videoWidth) return;

  const largura = 320;
  const altura = Math.round((video.videoHeight / video.videoWidth) * largura) || 240;
  if (el.canvas.width !== largura) {
    el.canvas.width = largura;
    el.canvas.height = altura;
  }
  const ctx = el.canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(video, 0, 0, largura, altura);

  const agora = performance.now() / 1000;
  const estado = medidor.processarQuadro(ctx, largura, altura, agora);

  el.barra.style.width = `${(estado.progresso * 100).toFixed(1)}%`;
  if (!estado.temPele) {
    dizer(estado.mensagem, 'alerta');
  } else if (estado.progresso < 1) {
    dizer(estado.mensagem);
  }

  // Uma análise por segundo basta: a janela é de vários segundos e refazer a
  // FFT a cada quadro só gastaria bateria.
  if (estado.temPele && estado.progresso >= 1 && agora - ultimaAnalise > 1) {
    ultimaAnalise = agora;
    const analise = medidor.analisar();
    if (analise) {
      const final = medidor.resultadoFinal();
      ultimoResultado = {
        bpm: final ? final.bpm : analise.bpm,
        snrDb: analise.snrDb,
        dispersao: final?.dispersao ?? 0,
        janelas: final?.janelas ?? 1,
        fps: analise.fps,
        duracaoS: analise.duracaoS,
        origem: 'câmera',
      };
      mostrarLeitura(analise.bpmExibido, analise.snrDb, {
        janelas: ultimoResultado.janelas,
        dispersao: ultimoResultado.dispersao,
        fps: analise.fps,
      });
      desenharOnda(analise.pulso);
      desenharEspectro(analise.espectro, analise.bpm);
      el.btnSalvar.disabled = false;

      const nivel = confiancaDe(analise.snrDb);
      if (nivel === 'baixa' || nivel === 'descartada') {
        dizer('Sinal fraco. Melhore a luz de frente e fique mais parado.', 'alerta');
      } else {
        dizer(`Medindo. Confiança ${nivel}.`);
      }
    }
  }
}

async function comecar() {
  if (abrindo) return;
  abrindo = true;
  cancelado = false;
  try {
    el.btnIniciar.disabled = true;
    // O botão de parar precisa funcionar durante a abertura, senão não há como
    // sair de uma tentativa demorada a não ser recarregando a página.
    el.btnParar.disabled = false;
    limparLeitura();
    ultimoResultado = null;
    el.btnSalvar.disabled = true;

    medidor = new Medidor({
      // O sinal do dedo é ordens de grandeza mais forte que o do rosto, então
      // uma janela curta já basta e a leitura aparece bem mais rápido.
      janelaS: fonte === 'dedo' ? 12 : Number(el.janela.value),
      algoritmo: el.algoritmo.value,
      modo: fonte === 'dedo' ? 'dedo' : 'rosto',
    });

    dizer('Pedindo acesso à câmera…');
    const ajustes = await iniciarCamera();
    if (ajustes?.width) {
      el.fps.textContent = `${ajustes.width}x${ajustes.height}`;
    }

    if (cancelado) {
      pararCamera();
      dizer('Medição cancelada.');
      return;
    }

    el.palcoVazio.hidden = true;
    el.palco.classList.remove('arquivo');
    rodando = true;
    ultimaAnalise = 0;

    if (fonte === 'dedo') {
      el.guia.classList.remove('visivel');
      const acendeu = await ligarLanterna();
      dizer(
        acendeu
          ? 'Lanterna acesa. Cubra a lente com a ponta do dedo, sem apertar.'
          : 'Este aparelho não deixa ligar a lanterna pelo navegador. Ligue-a pela '
            + 'central de atalhos do sistema e cubra a lente com o dedo.',
        acendeu ? '' : 'alerta',
      );
    } else {
      el.guia.classList.add('visivel');
      dizer('Encaixe o rosto no contorno e alinhe os olhos na linha.');
    }
    laco();
  } catch (erro) {
    pararCamera();
    dizer(cancelado ? 'Medição cancelada.' : mensagemDeErroDeCamera(erro), cancelado ? '' : 'erro');
  } finally {
    // Sem isto, qualquer falha durante a abertura deixaria a interface presa
    // com o botão desabilitado e sem saída a não ser recarregar a página.
    abrindo = false;
    el.btnIniciar.disabled = false;
    el.btnParar.disabled = !rodando;
  }
}

/** Traduz a falha em algo que a pessoa consiga resolver. */
function mensagemDeErroDeCamera(erro) {
  switch (erro?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return (
        'Acesso à câmera negado. Clique no ícone de câmera na barra de endereço, ' +
        'permita o acesso e recarregue a página.'
      );
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'Nenhuma câmera encontrada neste aparelho.';
    case 'NotReadableError':
    case 'TrackStartError':
      return (
        'A câmera acende mas o navegador não consegue ler dela. Isso quer dizer ' +
        'que outro programa está com ela aberta: feche o Cardiocam do PowerShell, ' +
        'o Teams, Meet, Discord, OBS ou o app Câmera do Windows, e recarregue esta página.'
      );
    case 'OverconstrainedError':
      return 'Esta câmera não aceita nenhuma das resoluções pedidas.';
    case 'AbortError':
      return 'A câmera foi interrompida pelo sistema. Recarregue a página e tente de novo.';
    case 'TimeoutError':
      return (
        'A câmera não respondeu dentro do prazo em nenhuma das tentativas. ' +
        'Feche a aba, desconecte e reconecte a câmera, e abra a página de novo. ' +
        'Se persistir, teste em outro navegador para separar problema de driver ' +
        'de problema do navegador.'
      );
    default:
      return erro?.message || 'Não foi possível iniciar a câmera.';
  }
}

function parar() {
  cancelado = true;
  rodando = false;
  if (animacao) cancelAnimationFrame(animacao);
  pararCamera();
  el.guia.classList.remove('visivel');
  el.palcoVazio.hidden = false;
  el.btnIniciar.disabled = false;
  el.btnParar.disabled = true;
  const final = medidor?.resultadoFinal();
  dizer(final ? `Medição encerrada: ${final.bpm.toFixed(0)} bpm.` : 'Medição encerrada.');
}

// ------------------------------------------------------------------- arquivo
async function processarArquivo(arquivo) {
  try {
    parar();
    limparLeitura();
    ultimoResultado = null;
    el.btnSalvar.disabled = true;
    el.palcoVazio.hidden = true;
    el.palco.classList.add('arquivo');
    el.guia.classList.add('visivel');

    const url = URL.createObjectURL(arquivo);
    el.video.srcObject = null;
    el.video.src = url;
    el.video.muted = true;

    await new Promise((resolve, reject) => {
      el.video.onloadedmetadata = resolve;
      el.video.onerror = () => reject(new Error('Não foi possível ler este vídeo.'));
    });

    dizer('Analisando o vídeo…');
    const resultado = await analisarVideo(el.video, {
      algoritmo: el.algoritmo.value,
      janelaS: Number(el.janela.value),
      aoProgredir: (p) => {
        el.barra.style.width = `${(p * 100).toFixed(1)}%`;
        dizer(`Analisando o vídeo… ${(p * 100).toFixed(0)}%`);
      },
    });

    URL.revokeObjectURL(url);
    el.barra.style.width = '100%';

    ultimoResultado = { ...resultado, origem: `arquivo: ${arquivo.name}` };
    mostrarLeitura(resultado.bpm, resultado.snrDb, {
      janelas: resultado.janelas,
      dispersao: resultado.dispersao,
      fps: resultado.fps,
    });
    desenharOnda(resultado.pulso);
    desenharEspectro(resultado.espectro, resultado.bpm);
    el.btnSalvar.disabled = false;

    const nivel = confiancaDe(resultado.snrDb);
    dizer(
      nivel === 'baixa' || nivel === 'descartada'
        ? 'Análise concluída, mas o sinal é fraco. Trate o valor com desconfiança.'
        : `Análise concluída. Confiança ${nivel}.`,
      nivel === 'baixa' || nivel === 'descartada' ? 'alerta' : '',
    );
  } catch (erro) {
    dizer(erro.message || 'Falha ao analisar o vídeo.', 'erro');
    el.barra.style.width = '0%';
  }
}

// ----------------------------------------------------------------- histórico
function formatarData(instante) {
  const d = new Date(instante);
  return `${d.toLocaleDateString('pt-BR')} ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
}

function atualizarHistorico() {
  const todas = listarMedicoes();
  el.contadorHistorico.textContent = todas.length;

  const pessoas = listarPessoas();
  el.pessoasConhecidas.innerHTML = pessoas.map((p) => `<option value="${p.nome}">`).join('');

  const filtroAtual = el.filtroPessoa.value;
  el.filtroPessoa.innerHTML =
    '<option value="">todas</option>' +
    pessoas.map((p) => `<option value="${p.nome}">${p.nome} (${p.total})</option>`).join('');
  el.filtroPessoa.value = filtroAtual;

  const lista = filtroAtual ? todas.filter((m) => m.pessoa === filtroAtual) : todas;

  el.historicoVazio.hidden = lista.length > 0;
  el.tabela.innerHTML = lista
    .map(
      (m) => `
      <tr>
        <td>${m.pessoa || '<span style="color:#626b67">sem nome</span>'}</td>
        <td>${formatarData(m.instante)}</td>
        <td class="num">${Number(m.bpm).toFixed(0)}</td>
        <td><span class="marca-confianca" data-nivel="${m.confianca}">${m.confianca}</span></td>
        <td class="num">${Number(m.snrDb).toFixed(1)}</td>
        <td>${m.algoritmo}</td>
        <td>${m.observacao || ''}</td>
        <td><button class="remover" data-id="${m.id}" title="Remover">×</button></td>
      </tr>`,
    )
    .join('');

  el.tabela.querySelectorAll('.remover').forEach((botao) => {
    botao.addEventListener('click', () => {
      removerMedicao(botao.dataset.id);
      atualizarHistorico();
    });
  });

  if (filtroAtual && lista.length >= 2) {
    const valores = lista.map((m) => m.bpm);
    const media = valores.reduce((a, b) => a + b, 0) / valores.length;
    const min = Math.min(...valores);
    const max = Math.max(...valores);
    el.resumoPessoa.hidden = false;
    el.resumoPessoa.innerHTML =
      `<strong>${filtroAtual}</strong>: ${lista.length} medições, ` +
      `média <strong>${media.toFixed(1)}</strong> bpm, ` +
      `mínima <strong>${min.toFixed(0)}</strong>, máxima <strong>${max.toFixed(0)}</strong>.`;
  } else {
    el.resumoPessoa.hidden = true;
  }
}

function salvar() {
  if (!ultimoResultado) return;
  salvarMedicao({
    pessoa: el.pessoa.value.trim(),
    observacao: el.observacao.value.trim(),
    bpm: ultimoResultado.bpm,
    snrDb: ultimoResultado.snrDb,
    confianca: confiancaDe(ultimoResultado.snrDb),
    algoritmo: el.algoritmo.value,
    duracaoS: ultimoResultado.duracaoS,
    origem: ultimoResultado.origem,
  });
  atualizarHistorico();
  el.btnSalvar.disabled = true;
  dizer(`Resultado salvo${el.pessoa.value.trim() ? ` para ${el.pessoa.value.trim()}` : ''}.`);
}

// -------------------------------------------------------------------- ligação
document.querySelectorAll('.aba').forEach((aba) => {
  aba.addEventListener('click', () => {
    document.querySelectorAll('.aba').forEach((a) => a.classList.remove('aba-ativa'));
    document.querySelectorAll('.vista').forEach((v) => v.classList.remove('vista-ativa'));
    aba.classList.add('aba-ativa');
    $(`vista-${aba.dataset.vista}`).classList.add('vista-ativa');
  });
});

function escolherFonte(nova, botaoAtivo, rotuloBotao, mensagem) {
  fonte = nova;
  [el.btnCamera, el.btnDedo, el.btnArquivo].forEach((b) =>
    b.classList.toggle('pilula-ativa', b === botaoAtivo),
  );
  el.btnIniciar.textContent = rotuloBotao;
  el.palco.classList.remove('arquivo');
  el.campoDispositivo.hidden = nova !== 'camera' || el.dispositivo.options.length <= 1;
  dizer(mensagem);
}

el.btnCamera.addEventListener('click', () =>
  escolherFonte('camera', el.btnCamera, 'Iniciar medição', 'Pronto para começar.'),
);

el.btnDedo.addEventListener('click', () =>
  escolherFonte(
    'dedo',
    el.btnDedo,
    'Iniciar medição',
    'Use a câmera de trás: cubra a lente com a ponta do dedo, sem apertar.',
  ),
);

el.btnArquivo.addEventListener('click', () =>
  escolherFonte(
    'arquivo',
    el.btnArquivo,
    'Escolher vídeo',
    'Escolha um vídeo com o rosto enquadrado no contorno.',
  ),
);

el.btnIniciar.addEventListener('click', () => {
  if (fonte === 'camera') comecar();
  else el.arquivo.click();
});

el.arquivo.addEventListener('change', (evento) => {
  const arquivo = evento.target.files?.[0];
  if (arquivo) processarArquivo(arquivo);
  evento.target.value = '';
});

el.btnParar.addEventListener('click', parar);
el.btnSalvar.addEventListener('click', salvar);
el.filtroPessoa.addEventListener('change', atualizarHistorico);
el.btnExportar.addEventListener('click', baixarCsv);
el.btnLimpar.addEventListener('click', () => {
  if (confirm('Apagar todas as medições salvas neste aparelho? Não dá para desfazer.')) {
    limparTudo();
    atualizarHistorico();
  }
});

window.addEventListener('resize', () => {
  if (medidor?.ultimaAnalise) {
    desenharOnda(medidor.ultimaAnalise.pulso);
    desenharEspectro(medidor.ultimaAnalise.espectro, medidor.ultimaAnalise.bpm);
  }
});

window.addEventListener('beforeunload', pararCamera);

atualizarHistorico();
limparLeitura();
