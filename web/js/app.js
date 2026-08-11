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
  btnArquivo: $('btnFonteArquivo'),
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
  el.bpm.textContent = Number.isFinite(bpm) ? bpm.toFixed(0) : '--';
  el.bpm.className = 'numerao ' + (nivel === 'alta' || nivel === 'média' ? 'viva' : 'duvidosa');
  el.selo.textContent = nivel;
  el.selo.dataset.nivel = nivel;
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
async function iniciarCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      'Este navegador não expõe a câmera. Em celular, use Chrome, Safari ou Firefox atualizados.',
    );
  }
  fluxo = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: 'user',
      width: { ideal: 640 },
      height: { ideal: 480 },
      frameRate: { ideal: 30 },
    },
    audio: false,
  });
  el.video.srcObject = fluxo;
  el.video.muted = true;
  await el.video.play();
}

function pararCamera() {
  if (fluxo) {
    fluxo.getTracks().forEach((t) => t.stop());
    fluxo = null;
  }
  el.video.srcObject = null;
}

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
  try {
    el.btnIniciar.disabled = true;
    limparLeitura();
    ultimoResultado = null;
    el.btnSalvar.disabled = true;

    medidor = new Medidor({
      janelaS: Number(el.janela.value),
      algoritmo: el.algoritmo.value,
    });

    dizer('Pedindo acesso à câmera…');
    await iniciarCamera();

    el.palcoVazio.hidden = true;
    el.guia.classList.add('visivel');
    el.palco.classList.remove('arquivo');
    rodando = true;
    ultimaAnalise = 0;
    el.btnParar.disabled = false;
    dizer('Encaixe o rosto no contorno e fique parado.');
    laco();
  } catch (erro) {
    el.btnIniciar.disabled = false;
    const mensagem = erro?.name === 'NotAllowedError'
      ? 'Acesso à câmera negado. Libere a permissão no navegador e tente de novo.'
      : erro?.name === 'NotFoundError'
        ? 'Nenhuma câmera encontrada neste aparelho.'
        : erro?.name === 'NotReadableError'
          ? 'A câmera está sendo usada por outro programa. Feche e tente de novo.'
          : erro.message || 'Não foi possível iniciar a câmera.';
    dizer(mensagem, 'erro');
  }
}

function parar() {
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

el.btnCamera.addEventListener('click', () => {
  fonte = 'camera';
  el.btnCamera.classList.add('pilula-ativa');
  el.btnArquivo.classList.remove('pilula-ativa');
  el.btnIniciar.textContent = 'Iniciar medição';
  el.palco.classList.remove('arquivo');
  dizer('Pronto para começar.');
});

el.btnArquivo.addEventListener('click', () => {
  fonte = 'arquivo';
  el.btnArquivo.classList.add('pilula-ativa');
  el.btnCamera.classList.remove('pilula-ativa');
  el.btnIniciar.textContent = 'Escolher vídeo';
  dizer('Escolha um vídeo com o rosto enquadrado no contorno.');
});

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
