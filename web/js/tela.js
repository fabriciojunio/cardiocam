/**
 * Captura da tela, para medir alguém numa chamada de vídeo.
 *
 * É o caminho que funciona com Teams, Meet, Zoom e WhatsApp, e vale explicar
 * por que é este e não outro.
 *
 * **Não existe API dessas plataformas que entregue o vídeo do participante.**
 * Nem Teams, nem Meet, nem Zoom, nem WhatsApp expõem o fluxo de vídeo de quem
 * está na chamada para um programa de fora. Quem promete "integração com o
 * Teams" para medir sinal vital está, na prática, fazendo uma destas três
 * coisas: capturando a tela, instalando uma câmera virtual no meio do caminho,
 * ou medindo localmente em cada máquina. A primeira é esta; a segunda exige
 * instalar software e só resolve o lado de quem envia; a terceira é a correta
 * e está descrita no fim deste comentário.
 *
 * Então: a pessoa escolhe a janela da chamada, e nós medimos o rosto que
 * aparece nela. Funciona em qualquer plataforma, porque não depende de
 * nenhuma, e funciona com o cliente web e com o aplicativo de desktop.
 *
 * **O custo, que é grande e precisa estar na tela e não só aqui.** O vídeo que
 * chega na janela da chamada já passou por compressão com perda. Codec de
 * videochamada aplica subamostragem de crominância e descarta variação temporal
 * sutil em região homogênea, porque isso não afeta a percepção. Essa é a
 * descrição exata do sinal que procuramos: variação de 0,1% a 1% da
 * intensidade, numa região de cor quase uniforme. A literatura mede que a
 * compressão H.264 degrada a relação sinal-ruído do rPPG, com impacto maior
 * nos canais azul e vermelho e em resolução baixa.
 *
 * Quer dizer que medir pela tela é pior, e às vezes impossível. Não é motivo
 * para não ter o recurso; é motivo para o recurso avisar. O que este módulo
 * faz é entregar o fluxo e os indicadores de qualidade que permitem ao medidor
 * recusar um número ruim em vez de exibi-lo.
 *
 * **Consentimento.** Medir frequência cardíaca de alguém é medir dado de saúde.
 * Fazer isso numa reunião sem a pessoa saber é, no mínimo, desrespeito, e no
 * Brasil dado de saúde é dado pessoal sensível pela Lei Geral de Proteção de
 * Dados. A interface exige confirmação explícita de que a pessoa medida
 * consentiu, e isso não é enfeite jurídico: é a diferença entre uma ferramenta
 * e uma câmera escondida.
 *
 * **O desenho correto, para quando isto virar produto.** Cada participante mede
 * a si mesmo, no próprio aparelho, antes da compressão, e compartilha **o
 * número** se quiser. Nada de vídeo circula, a medição é feita no sinal íntegro
 * e o consentimento é intrínseco, porque quem mede é a própria pessoa. A
 * captura de tela existe para o caso em que isso não é possível.
 */

/** Quais plataformas sabemos reconhecer pelo rótulo do fluxo capturado. */
const PLATAFORMAS = [
  { chave: 'teams', nome: 'Microsoft Teams', padrao: /teams|microsoft teams/i },
  { chave: 'meet', nome: 'Google Meet', padrao: /meet\.google|google meet/i },
  { chave: 'zoom', nome: 'Zoom', padrao: /zoom/i },
  { chave: 'whatsapp', nome: 'WhatsApp', padrao: /whatsapp/i },
  { chave: 'discord', nome: 'Discord', padrao: /discord/i },
  { chave: 'slack', nome: 'Slack', padrao: /slack/i },
];

export function suportaCapturaDeTela() {
  return typeof navigator !== 'undefined'
    && Boolean(navigator.mediaDevices?.getDisplayMedia);
}

/**
 * Identifica a plataforma pelo rótulo da faixa de vídeo.
 *
 * Serve só para a mensagem na tela ficar específica ("medindo a janela do
 * Teams") em vez de genérica. O rótulo depende do navegador e do sistema, e
 * pode vir vazio: nesse caso devolvemos desconhecido e seguimos, porque a
 * medição não depende de saber qual é o programa.
 */
export function identificarPlataforma(fluxo) {
  const faixa = fluxo?.getVideoTracks?.()[0];
  const rotulo = faixa?.label || '';
  for (const plataforma of PLATAFORMAS) {
    if (plataforma.padrao.test(rotulo)) {
      return { ...plataforma, rotulo };
    }
  }
  return { chave: 'desconhecida', nome: '', rotulo };
}

/**
 * Pede a captura de uma janela ou aba.
 *
 * `displaySurface: 'window'` é uma dica, não uma ordem: o navegador sempre
 * mostra o seletor com todas as opções, por segurança, e a escolha é do
 * usuário. A dica só faz a aba de janelas abrir já selecionada, que é o que
 * queremos em 99% dos casos.
 *
 * A taxa de quadros pedida é 30. Pedir 60 não ajuda, porque o limite aqui é a
 * taxa com que a plataforma de chamada **renderiza** o vídeo recebido, que
 * costuma ficar entre 15 e 30, e porque quadro repetido não acrescenta
 * informação nenhuma ao espectro.
 */
export async function pedirCapturaDeTela() {
  if (!suportaCapturaDeTela()) {
    return {
      ok: false,
      erro: 'Este navegador não permite capturar a tela. '
        + 'No celular isso é limitação do sistema, não do site: '
        + 'use a câmera, ou abra esta página no computador.',
    };
  }

  try {
    const fluxo = await navigator.mediaDevices.getDisplayMedia({
      video: {
        displaySurface: 'window',
        frameRate: { ideal: 30, max: 30 },
        // Mantém o cursor fora do quadro: ele passando sobre o rosto é uma
        // mudança brusca de pixel na região medida. Vai dentro de `video`
        // porque é restrição de faixa; no nível de cima é ignorado.
        cursor: 'never',
      },
      audio: false,
      // Pede ao navegador que não ofereça a própria aba como opção: capturar a
      // si mesma cria um túnel de espelhos e mede nada.
      selfBrowserSurface: 'exclude',
      surfaceSwitching: 'include',
    });
    return { ok: true, fluxo, plataforma: identificarPlataforma(fluxo) };
  } catch (erro) {
    const nome = erro?.name || '';
    if (nome === 'NotAllowedError') {
      return { ok: false, cancelado: true, erro: 'Captura cancelada.' };
    }
    if (nome === 'NotFoundError') {
      return { ok: false, erro: 'Nenhuma janela disponível para capturar.' };
    }
    return {
      ok: false,
      erro: `Não foi possível capturar a tela: ${erro?.message || nome || 'erro desconhecido'}.`,
    };
  }
}

/**
 * Avisa quando o usuário encerra a captura pelo botão do navegador.
 *
 * O navegador mostra uma barra própria com "parar compartilhamento", e ela não
 * passa pela nossa interface. Sem escutar isso, a página fica num estado em que
 * diz que está medindo e o fluxo já morreu.
 */
export function aoEncerrarCaptura(fluxo, callback) {
  const faixa = fluxo?.getVideoTracks?.()[0];
  if (!faixa) return () => {};
  const aoFim = () => callback();
  faixa.addEventListener('ended', aoFim);
  return () => faixa.removeEventListener('ended', aoFim);
}

/**
 * Qualidade do que foi capturado, para a interface poder avisar antes de medir.
 *
 * Os três limiares abaixo não são chute. São o que separa uma captura em que a
 * medição tem chance de uma em que ela não tem:
 *
 * - **resolução da área do rosto**: o rosto precisa ter pelo menos uns 100
 *   pixels de largura na captura para que a média espacial reduza o ruído o
 *   suficiente. Numa chamada com oito participantes em mosaico, cada rosto fica
 *   com muito menos que isso;
 * - **taxa de quadros**: abaixo de 15 por segundo a banda cardíaca chega perto
 *   do limite de Nyquist para a faixa alta, e frequência acima de 150 bpm deixa
 *   de ser representável com folga;
 * - **tamanho da janela capturada**: janela minúscula indica que a pessoa
 *   escolheu o item errado no seletor.
 */
export const LIMIARES = Object.freeze({
  larguraMinimaDoRosto: 100,
  quadrosPorSegundoMinimo: 15,
  larguraMinimaDaJanela: 320,
});

export function avaliarCaptura(fluxo, caixaRosto) {
  const faixa = fluxo?.getVideoTracks?.()[0];
  const ajustes = faixa?.getSettings?.() || {};
  const largura = ajustes.width || 0;
  const altura = ajustes.height || 0;
  const fps = ajustes.frameRate || 0;

  const avisos = [];

  if (largura && largura < LIMIARES.larguraMinimaDaJanela) {
    avisos.push('A janela capturada é muito pequena. Escolha a janela da chamada inteira.');
  }
  if (fps && fps < LIMIARES.quadrosPorSegundoMinimo) {
    avisos.push(
      `A captura está em ${Math.round(fps)} quadros por segundo. `
      + 'Abaixo de 15 a medição fica pouco confiável.',
    );
  }
  if (caixaRosto && largura) {
    const larguraDoRosto = caixaRosto.largura * largura;
    if (larguraDoRosto < LIMIARES.larguraMinimaDoRosto) {
      avisos.push(
        `O rosto tem ${Math.round(larguraDoRosto)} pixels de largura na captura. `
        + 'Coloque a chamada em tela cheia, ou fixe o participante em destaque.',
      );
    }
  }

  return {
    largura,
    altura,
    fps,
    avisos,
    // A compressão é certa, não provável: toda plataforma de chamada comprime.
    // Por isso este aviso não é condicional.
    ressalva:
      'O vídeo da chamada já passou por compressão, que descarta justamente a '
      + 'variação sutil de cor que carrega o pulso. Medir pela tela é sempre '
      + 'menos confiável que medir pela própria câmera.',
  };
}
