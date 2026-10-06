/**
 * Amarra a interface ao medidor.
 *
 * Nenhuma lógica de sinal mora aqui: este arquivo só liga botões, desenha os
 * gráficos e conversa com o armazenamento local.
 */

import { confiancaDe } from './dsp.js';
import { Medidor, analisarVideo, BPM_MAXIMO, BPM_MINIMO } from './medidor.js';
import { carregarModelo } from './cascata.js';
import { RastreadorDeRosto } from './rosto.js';
import {
  aoEncerrarCaptura,
  avaliarCaptura,
  pedirCapturaDeTela,
  suportaCapturaDeTela,
} from './tela.js';
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
  btnTela: $('btnFonteTela'),
  btnDedo: $('btnFonteDedo'),
  btnArquivo: $('btnFonteArquivo'),
  resolucao: $('dadoResolucao'),
  avisoConsentimento: $('avisoConsentimento'),
  chkConsentimento: $('chkConsentimento'),
  ressalvaCompressao: $('ressalvaCompressao'),
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

/**
 * Rastreamento de rosto. Instância única, porque ela guarda o estado temporal
 * da suavização, que é o que impede a caixa de tremer entre quadros.
 *
 * O modelo da cascata é carregado uma vez, sob demanda, e fica guardado: são
 * 148 KB de JSON do próprio site, e rebaixá-lo a cada medição faria a primeira
 * leitura demorar sempre.
 */
let rastreador = new RastreadorDeRosto(null);
let modeloDaCascata = null;
let carregandoModelo = null;
let rastreamentoLigado = false;
let regioesAtuais = null;
let caixaDoRosto = null;
let soltarAvisoDeCaptura = null;
let plataformaDaCaptura = null;

/**
 * Intervalo entre localizações do rosto, em milissegundos.
 *
 * **Não é por quadro, é por tempo**, e a diferença importa. A detecção em
 * cascata custa cerca de 200 ms no quadro de 320 pixels, medido. Amarrá-la à
 * contagem de quadros faria o custo subir junto com a taxa da câmera, que é o
 * oposto do desejado: quanto mais fluida a captura, mais o detector atrapalha.
 *
 * 500 ms é folgado para seguir alguém sentado conversando, e deixa a caixa
 * suavizada valendo entre uma localização e outra. O resultado é cerca de 40%
 * de um núcleo durante a medição, contra 100% se rodasse a cada quadro.
 */
const INTERVALO_DE_LOCALIZACAO_MS = 500;
let ultimaLocalizacao = 0;

/**
 * Garante o modelo carregado, sem bloquear o início da medição.
 *
 * A medição começa sem rastreamento, com o contorno oval, e passa para o modo
 * automático quando o modelo chega. Esperar o download antes de mostrar a
 * câmera deixaria a tela parada por um motivo que quem está olhando não vê.
 */
function garantirModelo() {
  if (modeloDaCascata) return Promise.resolve(modeloDaCascata);
  if (carregandoModelo) return carregandoModelo;

  carregandoModelo = carregarModelo()
    .then((modelo) => {
      modeloDaCascata = modelo;
      rastreador = new RastreadorDeRosto(modelo);
      return modelo;
    })
    .catch((erro) => {
      // Sem modelo a página continua medindo pelo contorno fixo. Página que
      // deixa de funcionar porque um arquivo não baixou é pior que página com
      // modo manual.
      carregandoModelo = null;
      console.warn('rastreamento indisponível:', erro?.message || erro);
      return null;
    });

  return carregandoModelo;
}

/**
 * Degraus de qualidade, do melhor para o pior.
 *
 * A escolha é automática e medida, não configurável, e a razão é que a resposta
 * certa depende da câmera **e** da máquina, que o usuário não tem como saber.
 *
 * Pedia 640x480 fixo, e isso jogava fora sinal de graça em qualquer câmera
 * decente. O raciocínio: o processamento reduz o quadro para uma largura fixa
 * antes de medir, e **reduzir é promediar**. Capturar em 1920 e reduzir para
 * 320 faz cada pixel processado ser a média de 36 pixels do sensor, o que
 * divide o ruído de leitura por seis antes de qualquer algoritmo agir.
 *
 * O teto é 1920 e não 4K de propósito, e isso é decisão de engenharia e não
 * limitação: acima de 1080p o ganho de promediação cresce devagar, enquanto o
 * custo de decodificar e redimensionar cada quadro cresce rápido. E aqui
 * **taxa de quadros estável vale mais que resolução**, porque a estimativa é
 * de frequência: quadro perdido vira irregularidade na amostragem, que é
 * exatamente o que mais atrapalha a análise espectral. Trocar ruído de sensor
 * por instabilidade de amostragem seria trocar um problema tratável por um
 * pior.
 *
 * `ideal` e não `exact`: câmera que não entrega a resolução entrega a mais
 * próxima, em vez de recusar a abertura.
 */
/**
 * Taxa de quadros pedida, com **teto** e não só preferência.
 *
 * O teto é o ponto, e ele vale luz. A câmera não pode expor um quadro por mais
 * tempo que o intervalo entre quadros: a 60 por segundo o limite é 16 ms, a 30
 * é 33 ms, a 20 é 50 ms. **Menos quadros é mais luz**, e luz é exatamente o que
 * falta para medir em sala comum.
 *
 * O número vem da literatura e não de tentativa. Odinaev et al. (CVPRW 2023)
 * mediram o ajuste de exposição para medição de sinal vital por câmera e
 * acharam o ótimo em **1/16 de segundo**, isto é, 62 ms, concluindo que maior
 * tempo de exposição se associa a maior correlação com o fotopletismógrafo de
 * contato em pouca luz. Com ajuste manual de ganho e exposição, a medição
 * funciona com iluminância de até 25 lux.
 *
 * A revisão sistemática da área dá **19,9 quadros por segundo como o mínimo
 * absoluto**. Pedir 20 com teto em 24 fica acima desse piso e permite exposição
 * perto do ótimo. Para a banda cardíaca, que vai a 3,3 Hz, 20 por segundo ainda
 * são três vezes a taxa de Nyquist.
 *
 * Sem o teto a câmera escolhe 60, porque o navegador trata taxa alta como
 * qualidade. Aqui esse é o critério errado: taxa alta compra uma resolução
 * temporal que o pulso não usa, e paga com a luz que ele precisa.
 */
const TAXA_ALVO = Object.freeze({ ideal: 20, max: 24 });

const DEGRAUS_DE_QUALIDADE = Object.freeze([
  { width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: TAXA_ALVO },
  { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: TAXA_ALVO },
  { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: TAXA_ALVO },
]);

/** O degrau em uso. Começa no melhor e desce sozinho se a máquina não aguentar. */
let degrauAtual = 0;

/**
 * Taxa de quadros abaixo da qual vale descer um degrau de resolução.
 *
 * Desceu de 20 para 14 quando a taxa pedida passou a ser 20: reprovar a 20
 * quando se pede 20 derrubaria a resolução em toda medição.
 *
 * O valor não vem de Nyquist, que para 3,3 Hz pediria 6,6. Vem de que taxa
 * abaixo disso costuma significar que a máquina está **perdendo** quadros, e
 * quadro perdido é amostra faltando em instante irregular, que é o que mais
 * atrapalha a análise espectral.
 */
const QUADROS_MINIMOS_ACEITAVEIS = 14;

/**
 * Quadros processados antes de julgar o desempenho.
 *
 * Os primeiros quadros depois de abrir a câmera são sempre irregulares:
 * exposição se acomodando, buffer enchendo, o navegador alocando textura.
 * Julgar ali reprovaria uma configuração boa por causa do aquecimento. Cinco
 * segundos a 30 por segundo dão amostra suficiente para a mediana significar
 * algo.
 */
const QUADROS_ANTES_DE_JULGAR = 150;
let quadrosParaAvaliarDesempenho = 0;
let jaAvaliouDesempenho = false;

/**
 * Desce um degrau de qualidade e reabre, quando a máquina não sustenta.
 *
 * Automático de propósito. A resposta certa depende da câmera e da máquina
 * juntas, e nenhuma das duas o usuário tem como avaliar olhando. Pedir que ele
 * escolha entre "1080p" e "720p" seria transferir para ele uma decisão que o
 * programa pode medir.
 */
async function descerDegrauSeNecessario() {
  if (jaAvaliouDesempenho || !rodando || !medidor) return;

  quadrosParaAvaliarDesempenho += 1;
  if (quadrosParaAvaliarDesempenho < QUADROS_ANTES_DE_JULGAR) return;

  jaAvaliouDesempenho = true;
  const entregue = medidor.fpsEfetivo;
  if (entregue >= QUADROS_MINIMOS_ACEITAVEIS) return;
  if (degrauAtual >= DEGRAUS_DE_QUALIDADE.length - 1) {
    dizer(
      `A captura está em ${entregue.toFixed(0)} quadros por segundo, que é `
      + 'pouco, e já estou na menor resolução. Feche abas e programas pesados.',
      'alerta',
    );
    return;
  }

  degrauAtual += 1;
  const alvo = DEGRAUS_DE_QUALIDADE[degrauAtual];
  dizer(
    `A máquina entregou ${entregue.toFixed(0)} quadros por segundo nesta `
    + `resolução. Baixando para ${alvo.width.ideal}x${alvo.height.ideal} e `
    + 'recomeçando, porque taxa de quadros estável vale mais que resolução.',
    'alerta',
  );
  parar();
  await espera(400);
  comecar();
}

/**
 * Nomes que denunciam câmera virtual.
 *
 * Câmera virtual não é um sensor: é um programa que entrega quadros, quase
 * sempre depois de processá-los. Enquadramento automático, desfoque de fundo,
 * suavização de pele e correção de cor são exatamente as operações que apagam
 * a variação de 0,1% a 1% de intensidade que carrega o pulso. Medir através de
 * uma delas é medir o resultado do filtro, não a pessoa.
 *
 * Isto saiu de um caso real: a página abriu a "EMEET STUDIO Virtual Camera" e
 * recebeu o logo de espera do programa, sem imagem nenhuma, e mesmo quando
 * havia imagem a relação sinal-ruído ficou em -4,8 dB com 42 bpm de dispersão
 * entre janelas, isto é, ruído puro.
 *
 * A lista cobre o que é comum; a palavra "virtual" sozinha pega o resto.
 */
const PADRAO_DE_CAMERA_VIRTUAL =
  /virtual|obs|nvidia broadcast|xsplit|snap camera|manycam|droidcam|iriun|epoccam|logi tune|streamlabs|camo/i;

function pareceCameraVirtual(rotulo) {
  return PADRAO_DE_CAMERA_VIRTUAL.test(String(rotulo || ''));
}

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
  el.snr.textContent = Number.isFinite(snrDb) ? `${snrDb.toFixed(1)} dB` : '--';
  if (extras.janelas !== undefined) el.janelasLidas.textContent = extras.janelas;
  if (extras.dispersao !== undefined) {
    el.dispersao.textContent = Number.isFinite(extras.dispersao) ? `${extras.dispersao.toFixed(2)} bpm` : '--';
  }
  if (extras.fps !== undefined) el.fps.textContent = `${extras.fps.toFixed(1)} q/s`;
}

function limparLeitura() {
  el.bpm.textContent = '--';
  el.bpm.className = 'numerao';
  el.selo.textContent = 'aguardando';
  el.selo.dataset.nivel = 'vazio';
  el.palcoLeitura.hidden = true;
  el.snr.textContent = '--';
  el.janelasLidas.textContent = '--';
  el.dispersao.textContent = '--';
  el.fps.textContent = '--';
  el.resolucao.textContent = '--';
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

  // Do degrau atual para baixo: se a máquina já se mostrou incapaz de
  // sustentar 1080p numa tentativa anterior, não adianta insistir nele.
  const degraus = DEGRAUS_DE_QUALIDADE.slice(degrauAtual);

  if (idDispositivo) {
    for (const degrau of degraus) {
      tentativas.push({ deviceId: { exact: idDispositivo }, ...degrau });
    }
    tentativas.push({ deviceId: { exact: idDispositivo } });
  }
  for (const degrau of degraus) {
    tentativas.push({ facingMode: 'user', ...degrau });
  }
  for (const degrau of degraus) {
    tentativas.push(degrau);
  }
  tentativas.push({ facingMode: 'user' });
  tentativas.push(true);

  try {
    return await primeiraQueAbrir(tentativas);
  } catch (erro) {
    // Permissão negada não melhora trocando de dispositivo.
    if (erro?.name === 'NotAllowedError' || erro?.name === 'SecurityError') throw erro;

    /*
      Última cartada: tentar **cada câmera do aparelho, uma por uma**.

      Isto existe por causa de um caso real. Em 05/10/2026 a página falhava com
      `NotReadableError` num computador com duas câmeras, e o OpenCV, fora do
      navegador, lia das duas sem problema. A câmera não estava ocupada: o que
      acontecia é que todas as tentativas acima resolvem para a **mesma**
      câmera, a padrão do navegador. Se é justamente ela que falha, afrouxar
      resolução e `facingMode` não muda nada, porque o dispositivo é o mesmo.

      `enumerateDevices` só revela os identificadores depois de alguma
      permissão ter sido concedida, e a esta altura ela já foi, mesmo que a
      abertura tenha falhado depois. Por isso esta etapa vem no fim, e não no
      começo: antes da primeira tentativa a lista viria sem identificador útil.
    */
    const cameras = await listarCameras();
    const jaTentado = new Set([idDispositivo].filter(Boolean));
    const restantes = cameras.filter((c) => c.deviceId && !jaTentado.has(c.deviceId));

    if (restantes.length === 0) throw erro;

    for (let i = 0; i < restantes.length; i++) {
      if (cancelado) throw new Error('Medição cancelada.');
      const camera = restantes[i];
      const nome = camera.label || `câmera ${i + 1}`;
      try {
        dizer(`A câmera padrão falhou. Tentando ${nome}…`);
        const aberto = await pedirCamera({ deviceId: { exact: camera.deviceId } });
        // Deixa o seletor refletindo o que de fato abriu, senão a próxima
        // medição recomeça pela câmera que não funciona.
        if (el.dispositivo && el.dispositivo.querySelector(`option[value="${camera.deviceId}"]`)) {
          el.dispositivo.value = camera.deviceId;
        }
        return aberto;
      } catch {
        await espera(300);
      }
    }
    throw erro;
  }
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

/**
 * Monta o seletor de câmera, quando há mais de uma.
 *
 * Chamado depois de abrir **e também depois de falhar**. O segundo caso é o
 * que importa: num aparelho com duas câmeras, se a padrão do navegador não
 * abre, é pelo seletor que se escolhe a outra. Preencher a lista só no sucesso
 * deixava a ferramenta aparecer apenas para quem não precisava dela.
 */
async function atualizarListaDeCameras() {
  // Entrada sem identificador é a que o navegador devolve antes de conceder
  // permissão: não serve para escolher nada e só polui a lista.
  const cameras = (await listarCameras()).filter((c) => c.deviceId);

  if (cameras.length <= 1 || !el.dispositivo) {
    if (el.campoDispositivo) el.campoDispositivo.hidden = true;
    return;
  }

  // Câmera de verdade primeiro, virtual depois. A ordem do seletor é a ordem
  // em que o navegador devolveu, e numa máquina com programa de câmera
  // instalado a virtual costuma vir antes da real. Como a primeira da lista é
  // a que o navegador também escolhe por padrão, isso faz a medição começar
  // justamente pela câmera que não serve.
  const ordenadas = [...cameras].sort((a, b) => {
    const va = pareceCameraVirtual(a.label) ? 1 : 0;
    const vb = pareceCameraVirtual(b.label) ? 1 : 0;
    return va - vb;
  });

  const atual = el.dispositivo.value;
  el.dispositivo.innerHTML = ordenadas
    .map((c, i) => {
      const nome = c.label || `Câmera ${i + 1}`;
      const marca = pareceCameraVirtual(c.label) ? ' (virtual, não recomendada)' : '';
      return `<option value="${escaparHtml(c.deviceId)}">${escaparHtml(nome + marca)}</option>`;
    })
    .join('');

  // Só restaura a escolha anterior se ela ainda existir: câmera desconectada
  // entre uma tentativa e outra deixaria o seletor apontando para o nada.
  if (atual && el.dispositivo.querySelector(`option[value="${CSS.escape(atual)}"]`)) {
    el.dispositivo.value = atual;
  }
  el.campoDispositivo.hidden = false;
}

/**
 * Avisa quando o que está medindo é uma câmera virtual.
 *
 * Não bloqueia: pode haver motivo para usar uma, e decidir pelo usuário seria
 * presunção. Mas a medição com câmera virtual é quase sempre ruído, e deixar
 * isso sem aviso faz a pessoa concluir que o sistema não funciona quando o que
 * não funciona é a fonte.
 */
function avisarSeCameraVirtual() {
  const trilha = fluxo?.getVideoTracks?.()[0];
  const rotulo = trilha?.label || '';
  if (!rotulo || !pareceCameraVirtual(rotulo)) return false;

  const temReal = [...(el.dispositivo?.options || [])]
    .some((o) => !/virtual, não recomendada/.test(o.textContent));

  dizer(
    `Está medindo pela "${rotulo}", que é uma câmera virtual. `
    + 'Programa de câmera virtual aplica enquadramento automático, suavização '
    + 'de pele e correção de cor, que são exatamente as operações que apagam o '
    + 'sinal do pulso. '
    + (temReal
      ? 'Escolha a câmera de verdade na lista abaixo e comece de novo.'
      : 'Feche o programa da câmera para que a câmera de verdade apareça.'),
    'alerta',
  );
  return true;
}

/**
 * Escapa texto que vai para dentro de HTML montado em string.
 *
 * O rótulo da câmera vem do sistema operacional e do fabricante, não de nós.
 * É improvável que contenha caractere de marcação, mas montar HTML com texto
 * de fora sem escapar é o tipo de coisa que funciona por anos e um dia não
 * funciona.
 */
function escaparHtml(texto) {
  return String(texto)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
          'A câmera abriu mas não entregou nenhuma imagem em 4 segundos. '
          + 'Se o aparelho tiver mais de uma câmera, escolha outra na lista '
          + 'abaixo e tente de novo.',
        ))),
        4000,
      );
    });
  }

  const trilha = fluxo.getVideoTracks()[0];
  await subirResolucaoSePuder(trilha);
  const ajustes = trilha?.getSettings?.() ?? {};
  await travarAjustesAutomaticos();
  await atualizarListaDeCameras();
  return ajustes;
}

/**
 * Pede à câmera a melhor resolução que ela declara suportar.
 *
 * Existe porque pedir `width: { ideal: 1920 }` na abertura **não bastou**, e
 * isso foi medido: a câmera abriu em 640x480 mesmo declarando suportar bem
 * mais. `ideal` é uma preferência que o navegador pondera junto com as outras,
 * e ele costuma resolver por um modo de baixa resolução e taxa alta, que é o
 * oposto do que serve aqui.
 *
 * O caminho determinístico é perguntar. `getCapabilities` diz o que a câmera
 * aceita de fato, e `applyConstraints` pede aquilo, sem adivinhação.
 *
 * O teto de 1920 é a mesma decisão de antes: acima de 1080p o ganho de
 * promediação cresce devagar e o custo de decodificar cada quadro cresce
 * rápido, e **taxa de quadros estável vale mais que resolução** numa estimativa
 * de frequência. Câmera de 4K entra em 1080p de propósito.
 *
 * Falhar aqui não é erro: câmera que não expõe `getCapabilities`, ou que
 * recusa a mudança, continua medindo no modo em que abriu.
 */
async function subirResolucaoSePuder(trilha) {
  if (!trilha?.getCapabilities || !trilha.applyConstraints) return;

  let capacidades;
  try {
    capacidades = trilha.getCapabilities();
  } catch {
    return;
  }

  const larguraMaxima = capacidades?.width?.max;
  const alturaMaxima = capacidades?.height?.max;
  if (!larguraMaxima || !alturaMaxima) return;

  const atual = trilha.getSettings?.() ?? {};
  const alvoLargura = Math.min(1920, larguraMaxima);
  const alvoAltura = Math.min(1080, alturaMaxima);

  // Já está igual ou melhor que o alvo: mexer só arriscaria piorar.
  if ((atual.width || 0) >= alvoLargura) return;

  try {
    await trilha.applyConstraints({
      width: { ideal: alvoLargura },
      height: { ideal: alvoAltura },
      // O mesmo teto da abertura, e não um valor próprio.
      //
      // Esta chamada tinha `frameRate: { ideal: 30, min: 15 }` e **desfazia** o
      // teto de 20 aplicado ao abrir a câmera: a captura voltava para 60
      // quadros por segundo, e com ela o limite de 16 ms de exposição que a
      // mudança existia para remover. O sintoma era não mudar nada, que é o
      // pior: parece que a hipótese estava errada quando o que estava errado
      // era a segunda chamada contradizendo a primeira.
      frameRate: TAXA_ALVO,
    });
  } catch {
    // Combinação recusada: tenta só a largura, que é o que mais importa para a
    // promediação. Altura o navegador deriva pela proporção do sensor. A taxa
    // vai junto, porque sem ela a câmera volta para a taxa máxima e perde o
    // tempo de exposição.
    try {
      await trilha.applyConstraints({
        width: { ideal: alvoLargura },
        frameRate: TAXA_ALVO,
      });
    } catch {
      /* a câmera fica no modo em que abriu */
    }
  }
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
/**
 * Luminância alvo da pele, de 0 a 255.
 *
 * Abaixo de 60 o pulso, que vale 0,1% a 1% da intensidade, fica menor que um
 * nível inteiro, e o sensor entrega inteiros. 110 dá folga confortável sem
 * chegar perto de estourar a pele, que começa a saturar por volta de 200 e aí
 * perde a modulação inteira.
 */
const LUMINANCIA_ALVO = 110;

/**
 * Trava exposição e balanço de branco, **depois de deixar a imagem clara**.
 *
 * A versão anterior fazia só a metade disto, e a metade que faltava era a que
 * aparecia na tela. Ela punha `exposureMode: 'manual'` sem definir tempo de
 * exposição, então a câmera congelava no valor que tivesse no instante da
 * abertura. Num quarto com luz de teto isso é um valor escuro, e a imagem
 * ficava escura o resto da sessão.
 *
 * O travamento precisa existir: exposição automática clareia a imagem
 * justamente quando a pele escurece por causa do pulso, apagando o sinal. Mas
 * travar no escuro troca um problema por outro pior, porque com pouca luz o
 * pulso não chega a existir no sinal.
 *
 * A sequência aqui resolve os dois: deixa o automático assentar, lê o tempo de
 * exposição que ele escolheu, trava, e então **sobe o tempo até a pele chegar
 * na luminância alvo**. É malha fechada com alvo medido, e não um valor fixo
 * que funcionaria só numa sala.
 */
async function travarAjustesAutomaticos() {
  try {
    const trilha = fluxo?.getVideoTracks?.()[0];
    if (!trilha?.getCapabilities) return false;

    // Deixa o automático assentar antes de olhar o que ele escolheu. Travar no
    // primeiro quadro pega a câmera ainda no valor de inicialização.
    await espera(700);

    const capacidades = trilha.getCapabilities();
    const avancado = [];
    if (capacidades.exposureMode?.includes('manual')) avancado.push({ exposureMode: 'manual' });
    if (capacidades.whiteBalanceMode?.includes('manual')) {
      avancado.push({ whiteBalanceMode: 'manual' });
    }
    if (!avancado.length) return false;

    await trilha.applyConstraints({ advanced: avancado });
    await clarearAteOAlvo(trilha, capacidades);
    return true;
  } catch {
    // Falhar aqui é rotina e não deve interromper a medição.
    return false;
  }
}

/** Luminância média do quadro atual, pela conversão BT.601. */
function luminanciaDoQuadro() {
  const video = el.video;
  if (!video?.videoWidth) return NaN;

  const l = 64;
  const a = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * l));
  const canvas = document.createElement('canvas');
  canvas.width = l;
  canvas.height = a;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(video, 0, 0, l, a);

  const dados = ctx.getImageData(0, 0, l, a).data;
  let soma = 0;
  let n = 0;
  // Só o terço central: as bordas costumam ter parede e janela, e deixar a
  // janela puxar a média faria o controle escurecer o rosto para não estourar
  // o fundo, que é o erro clássico de medição de luz por quadro inteiro.
  const x0 = Math.floor(l / 3);
  const x1 = Math.ceil((2 * l) / 3);
  const y0 = Math.floor(a / 4);
  const y1 = Math.ceil((3 * a) / 4);
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const i = (y * l + x) * 4;
      soma += 0.299 * dados[i] + 0.587 * dados[i + 1] + 0.114 * dados[i + 2];
      n += 1;
    }
  }
  return n ? soma / n : NaN;
}

/**
 * Sobe o tempo de exposição até a imagem chegar na luminância alvo.
 *
 * Busca proporcional e com poucos passos de propósito: a resposta da câmera não
 * é linear nem conhecida, e cada passo custa um quadro para surtir efeito.
 * Cinco passos levam de uma imagem bem escura ao alvo, e parar cedo é melhor
 * que oscilar em volta dele.
 *
 * Quando a câmera não expõe `exposureTime`, tenta `brightness`, que algumas
 * expõem no lugar. Não conseguindo nenhum dos dois, a medição segue com o que
 * houver: a mensagem de luz na tela cobre esse caso.
 */
async function clarearAteOAlvo(trilha, capacidades) {
  const temExposicao = Boolean(capacidades.exposureTime);
  const temBrilho = Boolean(capacidades.brightness);
  if (!temExposicao && !temBrilho) return;

  const faixa = temExposicao ? capacidades.exposureTime : capacidades.brightness;
  const propriedade = temExposicao ? 'exposureTime' : 'brightness';
  const minimo = faixa.min ?? 0;
  const maximo = faixa.max ?? 0;
  if (!(maximo > minimo)) return;

  for (let passo = 0; passo < 5; passo++) {
    const luz = luminanciaDoQuadro();
    if (!Number.isFinite(luz) || luz >= LUMINANCIA_ALVO) return;

    const ajustes = trilha.getSettings?.() ?? {};
    const atual = ajustes[propriedade] ?? minimo;

    // Proporcional ao quanto falta, com teto de 2,5x por passo: subir demais de
    // uma vez estoura a pele, e pele estourada perde a modulação inteira, que é
    // uma falha pior que a imagem escura.
    const fator = Math.min(2.5, Math.max(1.2, LUMINANCIA_ALVO / Math.max(luz, 1)));
    const alvo = Math.min(maximo, Math.max(minimo, atual * fator));
    if (!(alvo > atual)) return;

    try {
      await trilha.applyConstraints({ advanced: [{ [propriedade]: alvo }] });
    } catch {
      return;
    }
    // A mudança leva alguns quadros para aparecer na imagem.
    await espera(220);
  }
}

function pararCamera() {
  if (soltarAvisoDeCaptura) {
    soltarAvisoDeCaptura();
    soltarAvisoDeCaptura = null;
  }
  plataformaDaCaptura = null;
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

  // O detector fica carregado de propósito: o modelo já foi baixado e
  // descartá-lo faria a próxima medição pagar o download de novo. O que é
  // zerado é o estado de rastreamento, que não vale entre sessões.
  rastreamentoLigado = false;
  regioesAtuais = null;
  caixaDoRosto = null;
  rastreador.reiniciar();
}

/* A opção de deixar a tela branca para iluminar o rosto foi retirada.
   Ela partia da suposição de que faltava luz, e a medição no sinal real
   mostrou que não era esse o problema: com iluminação boa, a amplitude na
   banda cardíaca continuou igual ou abaixo do ruído de banda larga. Mais luz
   não resolve o que a própria câmera introduz. Manter o botão só daria a
   impressão de que existe um ajuste capaz de salvar a medição. */


/*
  Um quadro da camera por vez, e com o tempo do quadro.

  Este laco usava `requestAnimationFrame`, que dispara na taxa do MONITOR e nao
  na da camera. Com tela de 60 Hz e camera entregando 20 ou 30, o mesmo quadro
  era lido duas ou tres vezes, e cada copia entrava na serie com um carimbo de
  tempo diferente.

  O estrago nao e obvio e e grande. As copias carregam o MESMO ruido de sensor,
  entao a serie tem menos amostras independentes do que o codigo supoe, e a
  promediacao deixa de reduzir o ruido na proporcao esperada. Pior: a camera e
  a tela nao sao sincronas, o numero de repeticoes varia ao longo do tempo, e
  essa variacao injeta uma modulacao lenta que cai perto da banda cardiaca.

  Era o que fazia a medicao ser descartada "independente da luz": mais luz nao
  conserta amostra duplicada.

  `requestVideoFrameCallback` resolve as duas coisas de uma vez. Ele dispara
  exatamente uma vez por quadro NOVO e entrega `mediaTime`, que e o instante de
  apresentacao daquele quadro, bem mais fiel que o `performance.now()` lido
  quando o laco por acaso rodou.

  O caminho de `requestAnimationFrame` continua existindo para navegador que
  nao tem a API, e la a defesa e comparar `currentTime`: quadro repetido tem o
  mesmo valor e e descartado em vez de entrar duplicado.
*/
let ultimoTempoDeQuadro = -1;
let ultimoQuadroEm = 0;
let vigia = null;

/*
  Tempo sem quadro novo que faz o vigia assumir o laco.

  `requestVideoFrameCallback` so dispara quando chega quadro NOVO, e se a camera
  engasga ou o navegador para de compor a imagem a cadeia morre em silencio e
  nunca mais reata. Foi o que aconteceu: a camera "parava sozinha".

  Meio segundo e folgado para 20 quadros por segundo, onde o intervalo normal e
  50 ms, e curto o bastante para a pessoa nao perceber a retomada.
*/
const LIMITE_SEM_QUADRO_MS = 500;

function suportaCallbackDeQuadro() {
  return typeof el.video?.requestVideoFrameCallback === 'function';
}

function agendarProximoQuadro() {
  if (!rodando) return;
  if (suportaCallbackDeQuadro()) {
    animacao = el.video.requestVideoFrameCallback((_agora, metadados) => {
      animacao = null;
      laco(metadados);
    });
    return;
  }
  animacao = requestAnimationFrame(() => {
    animacao = null;
    laco(null);
    vigiarQuadros();
  });
}

function cancelarProximoQuadro() {
  if (animacao === null) return;
  if (suportaCallbackDeQuadro() && el.video?.cancelVideoFrameCallback) {
    el.video.cancelVideoFrameCallback(animacao);
  } else {
    cancelAnimationFrame(animacao);
  }
  animacao = null;
}

/*
  Vigia a cadeia de quadros, e a retoma quando ela para.

  Roda em `requestAnimationFrame`, que nao depende da camera e por isso continua
  batendo mesmo quando nenhum quadro chega. Ele nao mede nada: so percebe o
  silencio e reata, pelo caminho de reserva.
*/
function vigiarQuadros() {
  if (!rodando) {
    vigia = null;
    return;
  }
  vigia = requestAnimationFrame(vigiarQuadros);
  if (performance.now() - ultimoQuadroEm <= LIMITE_SEM_QUADRO_MS) return;
  cancelarProximoQuadro();
  laco(null);
}

function laco(metadados) {
  if (!rodando) return;
  ultimoQuadroEm = performance.now();
  agendarProximoQuadro();

  const video = el.video;
  if (!video.videoWidth) return;

  /*
    UMA base de tempo so, e ela e a da midia.

    Misturar `performance.now()`, que conta desde o carregamento da pagina e
    chega as dezenas de segundos, com `mediaTime`, que comeca do zero, foi um
    defeito real: a primeira amostra entrava com 42 e as seguintes com 0,1, a
    duracao acumulada ficava negativa, e a barra de progresso nunca completava.
    Era o "a contagem demora muito".

    `mediaTime` e `currentTime` vivem na mesma linha do tempo, entao os dois
    caminhos sao compativeis entre si.
  */
  const tempoDoQuadro = metadados && Number.isFinite(metadados.mediaTime)
    ? metadados.mediaTime
    : video.currentTime;
  if (!Number.isFinite(tempoDoQuadro)) return;

  // Quadro repetido tem exatamente o mesmo tempo de midia. Deixa-lo entrar de
  // novo e o defeito que esta funcao existe para impedir: copias carregam o
  // mesmo ruido e so fazem o piso de ruido parecer mais baixo do que e.
  if (tempoDoQuadro === ultimoTempoDeQuadro) return;

  // Tempo andando para tras quer dizer fonte reiniciada. Acumular por cima
  // produziria duracao negativa, que e o defeito acima com outra roupa.
  if (tempoDoQuadro < ultimoTempoDeQuadro) {
    medidor?.reiniciar();
  }
  ultimoTempoDeQuadro = tempoDoQuadro;

  const largura = 320;
  const altura = Math.round((video.videoHeight / video.videoWidth) * largura) || 240;
  if (el.canvas.width !== largura) {
    el.canvas.width = largura;
    el.canvas.height = altura;
  }
  const ctx = el.canvas.getContext('2d', { willReadFrequently: true });
  /*
    Qualidade alta na redução, e isso não é estética.

    É aqui que a média espacial de fato acontece: capturando em 1920 e
    reduzindo para 320, cada pixel processado é a média de 36 pixels do sensor,
    o que divide o ruído de leitura por seis antes de qualquer algoritmo agir.
    Com a reamostragem de baixa qualidade o navegador descarta pixels em vez de
    promediá-los, e boa parte dessa redução de ruído se perde justamente no
    passo em que ela sairia de graça.
  */
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(video, 0, 0, largura, altura);

  // Rastreamento antes da medição: as regiões acompanham o rosto, então a
  // pessoa pode se mover. Sem isso valeriam as posições fixas, e o contorno
  // oval na tela seria a única referência.
  if (rastreamentoLigado && medidor.modo !== 'dedo' && modeloDaCascata) {
    const agoraMs = performance.now();
    if (agoraMs - ultimaLocalizacao >= INTERVALO_DE_LOCALIZACAO_MS || !rastreador.caixa) {
      ultimaLocalizacao = agoraMs;
      const dados = ctx.getImageData(0, 0, largura, altura).data;
      const caixa = rastreador.atualizar(dados, largura, altura);
      const regioes = caixa ? rastreador.regioes() : null;
      if (regioes) {
        regioesAtuais = regioes;
        caixaDoRosto = caixa;
      } else if (rastreador.perdeuORosto) {
        // Perdeu o rosto de vez. Lista vazia faz o medidor relatar ausência de
        // pele, em vez de seguir medindo um lugar onde o rosto já não está.
        regioesAtuais = [];
        caixaDoRosto = null;
      }
    }
  }

  // Avalia o desempenho sem bloquear o laço: a função sai na hora até ter
  // amostra suficiente, e só então decide.
  void descerDegrauSeNecessario();

  // O instante do QUADRO, quando o navegador o fornece. `mediaTime` e o tempo
  // de apresentacao daquele quadro na linha do tempo da midia, e e o carimbo
  // correto para reamostrar: `performance.now()` mede quando o laco rodou, que
  // e outra coisa e carrega o jitter do laco junto.
  const agora = tempoDoQuadro;
  const estado = rastreamentoLigado && regioesAtuais
    ? medidor.processarQuadro(ctx, largura, altura, agora, regioesAtuais, caixaDoRosto)
    : medidor.processarQuadro(ctx, largura, altura, agora);

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
        /*
          Diagnóstico em vez de conselho genérico.

          "Melhore a luz e fique parado" é o tipo de mensagem que não ajuda,
          porque não diz o que está errado nem quanto. Agora, quando a causa
          provável é escuridão, a mensagem diz **o número medido** e a meta.

          O limiar de 60 saiu da física do problema: a variação que carrega o
          pulso é de 0,1% a 1% da intensidade, e o sensor quantiza em inteiros.
          Com luminância 20, o pulso vale entre 0,02 e 0,2 níveis, muito abaixo
          do passo de quantização, e sobrevive apenas pelo que a média espacial
          recupera. Acima de 60 o pulso passa a valer de 0,06 a 0,6 nível, que
          já é a faixa em que a promediação resolve com folga.
        */
        const luz = medidor.luminanciaMedia;
        if (analise.fundoAplicado === false) {
          /*
            A correção por fundo mede a perturbação de iluminação numa parte do
            quadro que não tem pulso, e a remove do sinal do rosto. Ela é a
            defesa principal contra o controle automático da câmera, que é a
            maior fonte de ruído correlacionado quando não dá para travá-lo:
            medido, ela levou os acertos de 1 em 16 para 16 em 16 sob balanço de
            branco oscilando.

            Ela exige referência em todos os quadros da janela, porque
            interpolar buraco introduziria o artefato lento que ela remove.
            Quando cai, é a causa mais provável de sinal ruim, e antes caía em
            silêncio.
          */
          dizer(
            'Sinal fraco, e a correção de iluminação está desligada porque o '
            + 'fundo não pôde ser medido em todos os quadros. Deixe algum fundo '
            + 'visível ao redor do rosto, afastando-se um pouco da câmera.',
            'alerta',
          );
        } else if (Number.isFinite(luz) && luz < 60) {
          dizer(
            `Sinal fraco, e a causa mais provável é luz: a pele está medindo `
            + `${luz.toFixed(0)} de 255 de luminância. Abaixo de 60 o pulso fica `
            + 'menor que o passo de quantização da câmera. Ponha uma luz de '
            + 'frente, não atrás.',
            'alerta',
          );
        } else {
          dizer('Sinal fraco. Fique mais parado e evite luz que oscila.', 'alerta');
        }
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

    // No modo dedo não há rosto: o que está na frente da lente é o dedo.
    regioesAtuais = null;
    caixaDoRosto = null;
    ultimaLocalizacao = 0;
    rastreador.reiniciar();
    rastreamentoLigado = fonte !== 'dedo';
    if (rastreamentoLigado) {
      // Sem bloquear: a medição começa pelo contorno fixo e passa para o
      // rastreamento quando o modelo chega.
      garantirModelo().then((modelo) => {
        if (modelo && rodando) {
          dizer('Rosto sendo acompanhado. Você pode se mover.');
        }
      });
    }

    let ajustes = null;
    if (fonte === 'tela') {
      dizer('Escolha a janela da chamada…');
      const captura = await pedirCapturaDeTela();
      if (!captura.ok) {
        dizer(captura.erro, captura.cancelado ? '' : 'erro');
        return;
      }
      fluxo = captura.fluxo;
      plataformaDaCaptura = captura.plataforma;
      el.video.srcObject = fluxo;
      el.video.muted = true;
      await el.video.play().catch(() => {});
      ajustes = fluxo.getVideoTracks()[0]?.getSettings?.() || null;

      // Quem encerra o compartilhamento pela barra do navegador não passa pela
      // nossa interface, e sem isto a página ficaria dizendo que mede um fluxo
      // que já morreu.
      soltarAvisoDeCaptura = aoEncerrarCaptura(fluxo, () => {
        if (rodando) {
          parar();
          dizer('O compartilhamento da janela foi encerrado.', 'alerta');
        }
      });
    } else {
      dizer('Pedindo acesso à câmera…');
      ajustes = await iniciarCamera();
    }

    // A resolução vai no campo dela. Antes era escrita no campo rotulado
    // "taxa de quadros", que depois era sobrescrito pela taxa de verdade: até
    // a primeira medida sair, a tela dizia que a taxa de quadros era 640x480.
    if (ajustes?.width) {
      el.resolucao.textContent = `${ajustes.width}x${ajustes.height}`;
    }

    if (cancelado) {
      pararCamera();
      dizer('Medição cancelada.');
      return;
    }

    el.palcoVazio.hidden = true;
    el.palco.classList.remove('arquivo');
    el.palco.classList.toggle('tela', fonte === 'tela');
    rodando = true;
    ultimaAnalise = 0;
    ultimoTempoDeQuadro = -1;
    ultimoQuadroEm = performance.now();

    if (fonte === 'tela') {
      const qualidade = avaliarCaptura(fluxo, null);
      const nome = plataformaDaCaptura?.nome;
      const avisos = qualidade.avisos.join(' ');
      dizer(
        (nome ? `Medindo a janela do ${nome}. ` : 'Medindo a janela escolhida. ')
        + (avisos || 'Deixe o rosto grande na tela.'),
        qualidade.avisos.length ? 'alerta' : '',
      );
    } else if (fonte === 'dedo') {
      const acendeu = await ligarLanterna();
      dizer(
        acendeu
          ? 'Lanterna acesa. Cubra a lente com a ponta do dedo, sem apertar.'
          : 'Este aparelho não deixa ligar a lanterna pelo navegador. Ligue-a pela '
            + 'central de atalhos do sistema e cubra a lente com o dedo.',
        acendeu ? '' : 'alerta',
      );
    } else {
      // O contorno aparece até o rastreamento assumir. Enquanto o modelo não
      // chega, ou se o detector não achar o rosto, ele é a referência que a
      // pessoa tem; assim que a caixa for localizada, o laço o esconde.
      // O aviso de câmera virtual tem precedência sobre a instrução normal:
      // medindo por uma delas, nenhuma instrução de postura vai salvar o
      // resultado, e insistir em dar dica de iluminação seria desviar do que
      // de fato importa.
      if (!avisarSeCameraVirtual()) {
        dizer('Olhe para a câmera. Você pode se mover, só mantenha a luz estável.');
      }
    }
    quadrosParaAvaliarDesempenho = 0;
    jaAvaliouDesempenho = false;
    laco(null);
  } catch (erro) {
    pararCamera();
    if (cancelado) {
      dizer('Medição cancelada.');
    } else {
      // Atualiza a lista de câmeras **também quando falha**. Antes ela só era
      // preenchida depois de uma abertura bem sucedida, o que deixava quem não
      // conseguia abrir sem o seletor, isto é, sem como escolher a outra
      // câmera do aparelho. Era o caminho sem saída: a ferramenta que
      // resolveria o problema só aparecia para quem não tinha o problema.
      await atualizarListaDeCameras().catch(() => {});

      // E diz quantas câmeras foram encontradas. Sem isso, "não consegui ler
      // nenhuma" não distingue "o aparelho não tem câmera" de "tem duas e as
      // duas recusaram", que pedem providências diferentes.
      const encontradas = (await listarCameras().catch(() => [])).filter((c) => c.deviceId);
      const quantas = encontradas.length === 0
        ? ' O navegador não enumerou nenhuma câmera.'
        : ` Câmeras que o navegador enumerou: ${encontradas.length}`
          + (encontradas.some((c) => c.label)
            ? ` (${encontradas.map((c) => c.label || 'sem nome').join(', ')}).`
            : '.');

      dizer(mensagemDeErroDeCamera(erro) + quantas, 'erro');
    }
  } finally {
    // Sem isto, qualquer falha durante a abertura deixaria a interface presa
    // com o botão desabilitado e sem saída a não ser recarregar a página.
    abrindo = false;
    el.btnParar.disabled = !rodando;
    atualizarBotaoIniciar();
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
      /*
        A mensagem anterior afirmava a causa: "outro programa está com ela
        aberta". Em 05/10/2026 isso se mostrou errado num caso real, em que a
        câmera estava livre e o OpenCV lia dela normalmente fora do navegador.

        Dizer a causa errada com segurança é pior que não dizer: manda a pessoa
        fechar programas que não são o problema, e quando isso não resolve ela
        conclui que o sistema não funciona. Agora a mensagem descreve o que
        aconteceu e lista o que conferir, em ordem de probabilidade, sem
        prometer qual é.
      */
      return (
        'O navegador não conseguiu ler nenhuma das câmeras. Já tentei todas as '
        + 'que este aparelho tem. Confira, nesta ordem: outro programa com a '
        + 'câmera aberta (Teams, Meet, Discord, OBS, app Câmera); permissão de '
        + 'câmera do Windows para o navegador; e desconectar e reconectar a '
        + 'câmera. Se nada resolver, teste em outro navegador, porque isso '
        + 'separa problema de driver de problema do navegador.'
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
  cancelarProximoQuadro();
  if (vigia !== null) {
    cancelAnimationFrame(vigia);
    vigia = null;
  }
  ultimoTempoDeQuadro = -1;
  pararCamera();
  el.palcoVazio.hidden = false;
  el.btnParar.disabled = true;
  // Pelo estado da fonte, e não direto para falso: na fonte de chamada o botão
  // continua travado se o consentimento não estiver marcado.
  atualizarBotaoIniciar();
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
  [el.btnCamera, el.btnTela, el.btnDedo, el.btnArquivo].forEach((b) =>
    b.classList.toggle('pilula-ativa', b === botaoAtivo),
  );
  el.btnIniciar.textContent = rotuloBotao;
  el.palco.classList.remove('arquivo', 'tela');
  el.campoDispositivo.hidden = nova !== 'camera' || el.dispositivo.options.length <= 1;

  // O consentimento só aparece na fonte que mede outra pessoa.
  el.avisoConsentimento.hidden = nova !== 'tela';
  if (nova === 'tela') {
    el.ressalvaCompressao.textContent = avaliarCaptura(null, null).ressalva;
  }
  atualizarBotaoIniciar();
  dizer(mensagem);
}

/**
 * Habilita o botão de iniciar conforme a fonte e o consentimento.
 *
 * Mantido numa função só porque três lugares diferentes mexem no estado do
 * botão, e espalhar a regra entre eles é como surge o botão que fica
 * desabilitado para sempre.
 */
function atualizarBotaoIniciar() {
  // Durante a abertura o botão fica travado de propósito, para não disparar
  // duas aberturas sobrepostas. Enquanto mede, ele continua ativo: clicar de
  // novo reinicia a medição, que é comportamento que já existia.
  if (abrindo) {
    el.btnIniciar.disabled = true;
    return;
  }
  const faltaConsentir = fonte === 'tela' && !el.chkConsentimento.checked;
  el.btnIniciar.disabled = faltaConsentir;
  el.btnIniciar.title = faltaConsentir
    ? 'Confirme que a pessoa medida sabe e concordou.'
    : '';
}

el.chkConsentimento.addEventListener('change', atualizarBotaoIniciar);

el.btnCamera.addEventListener('click', () =>
  escolherFonte('camera', el.btnCamera, 'Iniciar medição', 'Pronto para começar.'),
);

el.btnTela.addEventListener('click', () => {
  if (!suportaCapturaDeTela()) {
    dizer(
      'Este navegador não permite capturar a tela. No celular é limitação do '
      + 'sistema: abra esta página no computador.',
      'alerta',
    );
    return;
  }
  escolherFonte(
    'tela',
    el.btnTela,
    'Escolher janela',
    'Abra a chamada, deixe o rosto grande na tela e escolha a janela dela.',
  );
});

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
  if (fonte === 'camera' || fonte === 'tela' || fonte === 'dedo') comecar();
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
