/**
 * Dá o compasso dos quadros, e vigia o próprio compasso.
 *
 * Existe porque o laço de captura morria em silêncio, e o silêncio é o pior
 * modo de falha que uma medição contínua tem: a imagem congela, a barra para
 * onde estava, e nada na tela diz que parou. Quem está medindo conclui que o
 * sistema não funciona, quando o que parou foi o agendamento.
 *
 * Três mecanismos, e cada um cobre uma falha diferente.
 *
 * **Um quadro por quadro de verdade.** `requestVideoFrameCallback` dispara uma
 * vez por quadro novo da câmera e entrega `mediaTime`, o instante de
 * apresentação daquele quadro. `requestAnimationFrame` dispara na taxa do
 * monitor, que não tem relação nenhuma com a da câmera: com tela de 60 Hz e
 * câmera a 20, o mesmo quadro entrava três vezes na série, com três carimbos de
 * tempo diferentes. Cópia carrega o mesmo ruído do sensor, então a promediação
 * deixa de reduzir ruído na proporção que o código supõe, e a razão entre as
 * duas taxas varia ao longo do tempo, injetando uma modulação lenta bem perto
 * da banda cardíaca.
 *
 * **O vigia.** `requestVideoFrameCallback` só dispara quando chega quadro novo.
 * Se a câmera engasga, se a aba vai para segundo plano, se o sistema silencia a
 * trilha, a cadeia morre e **nada mais a reata**, porque o único evento que a
 * religava era justamente o quadro que deixou de chegar. O vigia roda em
 * `requestAnimationFrame`, que não depende da câmera, e só faz uma coisa:
 * perceber o silêncio e reatar.
 *
 * Na versão anterior o vigia existia e **nunca era ligado** no caminho do
 * `requestVideoFrameCallback`, que é o caminho de todo navegador atual. Ele só
 * era armado dentro do ramo de reserva, onde não fazia falta. Era defesa
 * escrita e não instalada.
 *
 * **A desistência.** Reatar o mesmo mecanismo que acabou de falhar três vezes
 * seguidas é insistir no que não funciona. Depois de três resgates seguidos a
 * cadência abandona `requestVideoFrameCallback` pelo resto da sessão e passa a
 * puxar quadro na taxa do monitor, rejeitando repetido pelo tempo de mídia. É
 * pior que o caminho principal e é muito melhor que parar.
 */

/**
 * Tempo sem quadro novo que faz o vigia assumir, em milissegundos.
 *
 * Meio segundo é folgado para 20 quadros por segundo, onde o intervalo normal é
 * de 50 ms, e curto o bastante para a retomada não dar tempo de ser percebida.
 */
export const LIMITE_SEM_QUADRO_MS = 500;

/** Resgates seguidos antes de abandonar o callback de vídeo nesta sessão. */
export const RESGATES_ATE_DESISTIR = 3;

export class CadenciaDeQuadros {
  /**
   * @param {object} opcoes
   * @param {HTMLVideoElement} opcoes.video  de onde os quadros vêm
   * @param {(quadro: {tempoS: number, retrocedeu: boolean, numero: number}) => void} opcoes.aoQuadro
   * @param {(silencioMs: number, estado: object) => void} [opcoes.aoSilencio]
   */
  constructor({
    video,
    aoQuadro,
    aoSilencio = () => {},
    agora = () => performance.now(),
    pedirAnimacao = (fn) => requestAnimationFrame(fn),
    cancelarAnimacao = (id) => cancelAnimationFrame(id),
    limiteDeSilencioMs = LIMITE_SEM_QUADRO_MS,
    resgatesAteDesistir = RESGATES_ATE_DESISTIR,
  }) {
    this.video = video;
    this.aoQuadro = aoQuadro;
    this.aoSilencio = aoSilencio;
    this.agora = agora;
    this.pedirAnimacao = pedirAnimacao;
    this.cancelarAnimacao = cancelarAnimacao;
    this.limiteDeSilencioMs = limiteDeSilencioMs;
    this.resgatesAteDesistir = resgatesAteDesistir;

    this.rodando = false;
    this.idDaFonte = null;
    this.fonteEhCallback = false;
    this.idDoVigia = null;
    this.usandoCallback = false;
    this.ultimoTempo = -1;
    this.ultimoQuadroEm = 0;
    this.quadros = 0;
    this.resgates = 0;
    this.resgatesSeguidos = 0;
  }

  get estado() {
    return {
      rodando: this.rodando,
      usandoCallback: this.usandoCallback,
      quadros: this.quadros,
      resgates: this.resgates,
      silencioMs: this.rodando ? this.agora() - this.ultimoQuadroEm : 0,
    };
  }

  iniciar() {
    if (this.rodando) return;
    this.rodando = true;
    this.ultimoTempo = -1;
    this.quadros = 0;
    this.resgates = 0;
    this.resgatesSeguidos = 0;
    this.usandoCallback = this._temCallbackDeQuadro();
    this.ultimoQuadroEm = this.agora();
    this._armarFonte();
    this._armarVigia();
  }

  parar() {
    this.rodando = false;
    this._cancelarFonte();
    if (this.idDoVigia !== null) {
      this.cancelarAnimacao(this.idDoVigia);
      this.idDoVigia = null;
    }
    this.ultimoTempo = -1;
  }

  /**
   * Força um resgate agora, sem esperar o vigia perceber.
   *
   * Serve para o retorno da aba ao primeiro plano: ali já se sabe que o
   * agendamento ficou parado, e esperar meio segundo para constatar o óbvio só
   * atrasa a retomada.
   */
  resgatar() {
    if (!this.rodando) return;
    this.ultimoQuadroEm = -Infinity;
    this._conferirSilencio();
  }

  _temCallbackDeQuadro() {
    return typeof this.video?.requestVideoFrameCallback === 'function';
  }

  _armarFonte() {
    if (!this.rodando) return;
    if (this.usandoCallback && this._temCallbackDeQuadro()) {
      this.fonteEhCallback = true;
      this.idDaFonte = this.video.requestVideoFrameCallback((_horario, metadados) => {
        this.idDaFonte = null;
        this._tique(metadados);
      });
      return;
    }
    this.fonteEhCallback = false;
    this.idDaFonte = this.pedirAnimacao(() => {
      this.idDaFonte = null;
      this._tique(null);
    });
  }

  _cancelarFonte() {
    if (this.idDaFonte === null) return;
    // O tipo é guardado junto com o identificador de propósito: a cadência pode
    // ter desistido do callback entre o agendamento e o cancelamento, e aí
    // decidir pelo modo atual cancelaria na fila errada, deixando a chamada
    // antiga viva.
    if (this.fonteEhCallback && this.video?.cancelVideoFrameCallback) {
      this.video.cancelVideoFrameCallback(this.idDaFonte);
    } else if (!this.fonteEhCallback) {
      this.cancelarAnimacao(this.idDaFonte);
    }
    this.idDaFonte = null;
  }

  _armarVigia() {
    if (!this.rodando) return;
    this.idDoVigia = this.pedirAnimacao(() => {
      this.idDoVigia = null;
      if (!this.rodando) return;
      this._conferirSilencio();
      this._armarVigia();
    });
  }

  _conferirSilencio() {
    const silencio = this.agora() - this.ultimoQuadroEm;
    if (silencio <= this.limiteDeSilencioMs) return;

    this.resgates += 1;
    this.resgatesSeguidos += 1;
    if (this.usandoCallback && this.resgatesSeguidos >= this.resgatesAteDesistir) {
      this.usandoCallback = false;
    }

    this._despertarOVideo();
    // Rearma o relógio antes de reatar: sem isto o vigia dispararia de novo no
    // próximo quadro de tela, e um resgate viraria uma rajada deles.
    this.ultimoQuadroEm = this.agora();
    this._cancelarFonte();
    this._armarFonte();
    this.aoSilencio(silencio, this.estado);
  }

  /**
   * Manda tocar, quando o elemento foi pausado por fora.
   *
   * Vídeo pausado não produz quadro, e nenhum dos dois agendamentos conserta
   * isso. O navegador pausa sozinho em algumas trocas de origem e quando o
   * sistema devolve o dispositivo depois de tê-lo tomado.
   */
  _despertarOVideo() {
    const video = this.video;
    if (!video || video.paused !== true) return;
    try {
      const tocando = video.play();
      if (tocando && typeof tocando.catch === 'function') tocando.catch(() => {});
    } catch {
      /* Sem fonte, ou sem permissão: o vigia tenta de novo no próximo ciclo. */
    }
  }

  _tique(metadados) {
    if (!this.rodando) return;
    // Reata antes de qualquer coisa que possa falhar. Exceção no consumidor não
    // pode levar a cadeia junto.
    this._armarFonte();

    /*
      Uma base de tempo só, e ela é a da mídia.

      Misturar `performance.now()`, que conta desde o carregamento da página e
      chega às dezenas de segundos, com `mediaTime`, que começa do zero, foi um
      defeito real: a primeira amostra entrava com 42 e as seguintes com 0,1, a
      duração acumulada ficava negativa, e a barra de progresso nunca
      completava. `mediaTime` e `currentTime` vivem na mesma linha do tempo,
      então os dois caminhos são compatíveis entre si.
    */
    const tempo = metadados && Number.isFinite(metadados.mediaTime)
      ? metadados.mediaTime
      : this.video?.currentTime;
    if (!Number.isFinite(tempo)) return;

    // Quadro repetido tem exatamente o mesmo tempo de mídia, e deixá-lo entrar
    // de novo é o defeito que esta classe existe para impedir.
    if (tempo === this.ultimoTempo) return;

    // Tempo andando para trás quer dizer fonte reiniciada. Acumular por cima
    // produziria duração negativa.
    const retrocedeu = this.ultimoTempo >= 0 && tempo < this.ultimoTempo;

    this.ultimoTempo = tempo;
    this.ultimoQuadroEm = this.agora();
    this.resgatesSeguidos = 0;
    this.quadros += 1;
    this.aoQuadro({ tempoS: tempo, retrocedeu, numero: this.quadros });
  }
}
