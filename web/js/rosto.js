/**
 * Rastreamento de rosto no navegador, com degradação para o contorno fixo.
 *
 * Por que isto passou a existir. A versão web media dentro de um oval fixo na
 * tela e pedia que a pessoa encaixasse o rosto nele. O comentário que
 * justificava essa escolha estava tecnicamente correto: com o rosto ancorado
 * num lugar fixo, a região medida para de tremer, e o tremor da caixa é o que
 * mais estraga a medição automática.
 *
 * Só que o preço era alto e ficou evidente no uso: a pessoa tem de ficar
 * imóvel, e a câmera também. Sair do oval por meio segundo contamina a janela
 * inteira, porque a média passa a incluir parede em vez de pele, e isso é uma
 * variação de amplitude muito maior que o pulso.
 *
 * A saída é rastrear o rosto de verdade e ancorar as regiões nos olhos, que é
 * exatamente o que a versão em Python faz. Com as regiões seguindo o rosto, o
 * conjunto de pixels promediado continua sendo pele mesmo com a pessoa se
 * movendo, e o problema volta a ser só o artefato de iluminação por pose, que
 * é tratável.
 *
 * O detector é o BlazeFace de curto alcance, via MediaPipe Tasks Vision. A
 * escolha por ele e não pelo modelo de 478 pontos é de custo: ele devolve a
 * caixa e seis pontos (olho esquerdo, olho direito, nariz, boca e os dois
 * tragos), e os dois olhos já bastam para ancorar testa e bochechas na mesma
 * proporção da versão em Python. O modelo de malha completa custaria uns 4 MB
 * de download para informação que não usaríamos.
 *
 * **Sobre privacidade.** O modelo e o runtime são baixados uma vez de uma rede
 * de distribuição; o vídeo não vai a lugar nenhum. A inferência roda em
 * WebAssembly dentro da própria aba. Nenhum quadro e nenhuma medição saem do
 * aparelho, e isso é propriedade do código, não promessa: não há envio em
 * nenhum caminho.
 *
 * **Sobre degradação.** Se a rede estiver bloqueada, se o navegador não tiver
 * suporte ou se o carregamento falhar, o módulo avisa e o medidor volta ao
 * contorno fixo. Página que deixa de funcionar porque uma rede de distribuição
 * caiu é pior que página com modo manual.
 */

const BASE_TAREFAS = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21';
const CAMINHO_WASM = `${BASE_TAREFAS}/wasm`;
const MODELO =
  'https://storage.googleapis.com/mediapipe-models/face_detector/' +
  'blaze_face_short_range/float16/1/blaze_face_short_range.tflite';

/** Ordem dos seis pontos que o BlazeFace devolve. */
export const PONTOS = Object.freeze({
  OLHO_ESQUERDO: 0,
  OLHO_DIREITO: 1,
  NARIZ: 2,
  BOCA: 3,
  TRAGO_ESQUERDO: 4,
  TRAGO_DIREITO: 5,
});

/**
 * Peso da detecção nova na média exponencial da caixa.
 *
 * Mesmo valor da versão em Python, e pelo mesmo motivo: o detector redetecta do
 * zero a cada quadro e a caixa oscila alguns pixels mesmo com a pessoa imóvel.
 * Suavizar troca esse tremor por um atraso, e o atraso é o mal menor, porque
 * tremor entra no sinal como ruído na banda errada e atraso só desloca a região
 * alguns pixels.
 */
const SUAVIZACAO = 0.25;

/**
 * Salto máximo aceito entre dois quadros, em fração da largura do rosto.
 *
 * Acima disso a detecção é tratada como falso positivo e descartada. Rosto
 * humano não atravessa um terço da própria largura em 33 ms; detector, sim,
 * quando pega um padrão de parede.
 */
const SALTO_MAXIMO = 0.35;

/** Por quantos quadros seguidos a última caixa vale quando o detector falha. */
const TOLERANCIA_QUADROS = 15;

function interpolar(antiga, nova, peso) {
  return {
    x: antiga.x + (nova.x - antiga.x) * peso,
    y: antiga.y + (nova.y - antiga.y) * peso,
    largura: antiga.largura + (nova.largura - antiga.largura) * peso,
    altura: antiga.altura + (nova.altura - antiga.altura) * peso,
  };
}

function saltoAbsurdo(antiga, nova) {
  const dx = nova.x + nova.largura / 2 - (antiga.x + antiga.largura / 2);
  const dy = nova.y + nova.altura / 2 - (antiga.y + antiga.altura / 2);
  const distancia = Math.hypot(dx, dy);
  if (distancia > SALTO_MAXIMO * Math.max(antiga.largura, 1e-6)) return true;
  const razao = nova.largura / Math.max(antiga.largura, 1e-6);
  return razao > 1.6 || razao < 0.625;
}

/**
 * Rastreador de rosto. Mantém o estado entre quadros.
 *
 * Uso:
 *   const rastreador = new RastreadorDeRosto();
 *   const pronto = await rastreador.carregar();
 *   const caixa = rastreador.atualizar(video, performance.now());
 */
export class RastreadorDeRosto {
  constructor() {
    this.detector = null;
    this.disponivel = false;
    this.motivoIndisponivel = '';
    this.caixa = null;
    this.olhos = null;
    this.quadrosSemRosto = 0;
    this.deteccoesRejeitadas = 0;
    this._carregando = null;
  }

  /**
   * Baixa o runtime e o modelo. Pode ser chamado mais de uma vez sem repetir o
   * download: a promessa é memorizada.
   */
  async carregar() {
    if (this._carregando) return this._carregando;
    this._carregando = this._carregarDeFato();
    return this._carregando;
  }

  async _carregarDeFato() {
    try {
      const { FaceDetector, FilesetResolver } = await import(
        /* @vite-ignore */ `${BASE_TAREFAS}/vision_bundle.mjs`
      );
      const vision = await FilesetResolver.forVisionTasks(CAMINHO_WASM);
      this.detector = await FaceDetector.createFromOptions(vision, {
        baseOptions: { modelAssetPath: MODELO, delegate: 'GPU' },
        runningMode: 'VIDEO',
        minDetectionConfidence: 0.5,
        minSuppressionThreshold: 0.3,
      });
      this.disponivel = true;
      return true;
    } catch (erro) {
      // Tenta uma segunda vez em CPU: delegado de GPU falha em aparelho sem
      // WebGL habilitado, e nesse caso a CPU resolve com folga para um
      // detector deste tamanho.
      try {
        const { FaceDetector, FilesetResolver } = await import(
          /* @vite-ignore */ `${BASE_TAREFAS}/vision_bundle.mjs`
        );
        const vision = await FilesetResolver.forVisionTasks(CAMINHO_WASM);
        this.detector = await FaceDetector.createFromOptions(vision, {
          baseOptions: { modelAssetPath: MODELO, delegate: 'CPU' },
          runningMode: 'VIDEO',
          minDetectionConfidence: 0.5,
        });
        this.disponivel = true;
        return true;
      } catch (segundoErro) {
        this.disponivel = false;
        this.motivoIndisponivel = String(segundoErro?.message || segundoErro || erro);
        return false;
      }
    }
  }

  reiniciar() {
    this.caixa = null;
    this.olhos = null;
    this.quadrosSemRosto = 0;
  }

  get perdeuORosto() {
    return this.quadrosSemRosto > TOLERANCIA_QUADROS;
  }

  /**
   * Processa um quadro e devolve a caixa do rosto em frações do quadro,
   * ou `null` quando o rosto não está localizado.
   *
   * `instanteMs` tem de crescer de forma estritamente monotônica: a API do
   * MediaPipe rejeita carimbo repetido ou para trás, e o sintoma é uma exceção
   * no meio do laço de vídeo.
   */
  atualizar(video, instanteMs) {
    if (!this.disponivel || !this.detector) return null;

    let resultado;
    try {
      resultado = this.detector.detectForVideo(video, instanteMs);
    } catch {
      // Carimbo fora de ordem ou textura ainda não pronta. Vale manter a
      // última caixa em vez de derrubar a medição.
      this.quadrosSemRosto += 1;
      return this.perdeuORosto ? null : this.caixa;
    }

    const deteccoes = resultado?.detections ?? [];
    if (deteccoes.length === 0) {
      this.quadrosSemRosto += 1;
      if (this.caixa && !this.perdeuORosto) return this.caixa;
      this.caixa = null;
      this.olhos = null;
      return null;
    }

    // O maior rosto do quadro: quem está sendo medido é quem está mais perto.
    const largura = video.videoWidth || 1;
    const altura = video.videoHeight || 1;
    let melhor = null;
    let maiorArea = -1;
    for (const deteccao of deteccoes) {
      const cb = deteccao.boundingBox;
      if (!cb) continue;
      const area = (cb.width || 0) * (cb.height || 0);
      if (area > maiorArea) {
        maiorArea = area;
        melhor = deteccao;
      }
    }
    if (!melhor) {
      this.quadrosSemRosto += 1;
      return this.perdeuORosto ? null : this.caixa;
    }

    const cb = melhor.boundingBox;
    const nova = {
      x: cb.originX / largura,
      y: cb.originY / altura,
      largura: cb.width / largura,
      altura: cb.height / altura,
    };

    if (this.caixa && saltoAbsurdo(this.caixa, nova)) {
      this.deteccoesRejeitadas += 1;
      this.quadrosSemRosto += 1;
      if (!this.perdeuORosto) return this.caixa;
    }

    this.quadrosSemRosto = 0;
    this.caixa = this.caixa ? interpolar(this.caixa, nova, SUAVIZACAO) : nova;

    // Os pontos do BlazeFace já vêm normalizados de 0 a 1.
    const pontos = melhor.keypoints;
    if (pontos && pontos.length >= 2) {
      const esquerdo = pontos[PONTOS.OLHO_ESQUERDO];
      const direito = pontos[PONTOS.OLHO_DIREITO];
      if (esquerdo && direito) {
        const novosOlhos = {
          esquerdo: { x: esquerdo.x, y: esquerdo.y },
          direito: { x: direito.x, y: direito.y },
        };
        this.olhos = this.olhos
          ? {
              esquerdo: {
                x: this.olhos.esquerdo.x + (novosOlhos.esquerdo.x - this.olhos.esquerdo.x) * SUAVIZACAO,
                y: this.olhos.esquerdo.y + (novosOlhos.esquerdo.y - this.olhos.esquerdo.y) * SUAVIZACAO,
              },
              direito: {
                x: this.olhos.direito.x + (novosOlhos.direito.x - this.olhos.direito.x) * SUAVIZACAO,
                y: this.olhos.direito.y + (novosOlhos.direito.y - this.olhos.direito.y) * SUAVIZACAO,
              },
            }
          : novosOlhos;
      }
    }

    return this.caixa;
  }

  fechar() {
    try {
      this.detector?.close();
    } catch {
      /* fechar duas vezes não deve derrubar a página */
    }
    this.detector = null;
    this.disponivel = false;
  }
}

/**
 * Regiões de interesse ancoradas nos olhos, em frações do quadro.
 *
 * As proporções são as mesmas da versão em Python, de propósito: as duas
 * implementações precisam medir a mesma coisa para que os números sejam
 * comparáveis entre elas.
 *
 * A distância entre os olhos é a unidade de medida, e não a caixa do rosto. A
 * razão é prática: a caixa do detector muda de tamanho conforme a confiança e
 * o enquadramento, enquanto a distância interocular é uma medida anatômica
 * estável. Ancorar na caixa faria as regiões respirarem junto com o detector.
 *
 * Boca e olhos ficam fora. Piscar e falar produzem movimento exatamente na
 * banda de frequência do coração, e esse artefato nenhuma filtragem remove.
 */
export function regioesAncoradas(olhos) {
  if (!olhos) return null;
  const { esquerdo, direito } = olhos;

  const dx = direito.x - esquerdo.x;
  const dy = direito.y - esquerdo.y;
  const distancia = Math.hypot(dx, dy);
  if (!(distancia > 1e-6)) return null;

  const centroX = (esquerdo.x + direito.x) / 2;
  const centroY = (esquerdo.y + direito.y) / 2;

  // Testa: acima da linha dos olhos, centrada, com largura de 1,1 interocular.
  const testa = {
    x: centroX - distancia * 0.55,
    y: centroY - distancia * 0.95,
    largura: distancia * 1.1,
    altura: distancia * 0.45,
  };

  // Bochechas: abaixo e para fora, evitando a boca.
  const larguraBochecha = distancia * 0.52;
  const alturaBochecha = distancia * 0.46;
  const bochechaEsquerda = {
    x: esquerdo.x - larguraBochecha * 0.62,
    y: centroY + distancia * 0.32,
    largura: larguraBochecha,
    altura: alturaBochecha,
  };
  const bochechaDireita = {
    x: direito.x - larguraBochecha * 0.38,
    y: centroY + distancia * 0.32,
    largura: larguraBochecha,
    altura: alturaBochecha,
  };

  return [testa, bochechaEsquerda, bochechaDireita].map(limitar);
}

/** Recorta a região para dentro do quadro, devolvendo null se sobrar nada. */
function limitar(regiao) {
  const x = Math.max(0, Math.min(1, regiao.x));
  const y = Math.max(0, Math.min(1, regiao.y));
  const largura = Math.max(0, Math.min(1 - x, regiao.largura));
  const altura = Math.max(0, Math.min(1 - y, regiao.altura));
  return { x, y, largura, altura };
}

/**
 * Faixas de fundo que não encostam no rosto rastreado.
 *
 * Na versão com oval fixo, o fundo eram duas faixas laterais fixas, e isso
 * funcionava porque o rosto estava sempre no meio. Com o rosto se movendo, uma
 * faixa fixa pode acabar em cima dele, e aí a referência de iluminação passa a
 * conter pulso, que é o oposto do que ela serve para fazer.
 *
 * Aqui as faixas são escolhidas do lado oposto a onde o rosto está.
 */
export function regioesDeFundo(caixaRosto) {
  const LARGURA = 0.13;
  if (!caixaRosto) {
    return [
      { x: 0, y: 0, largura: LARGURA, altura: 1 },
      { x: 1 - LARGURA, y: 0, largura: LARGURA, altura: 1 },
    ];
  }

  const faixas = [];
  const folga = 0.03;
  if (caixaRosto.x > LARGURA + folga) {
    faixas.push({ x: 0, y: 0, largura: LARGURA, altura: 1 });
  }
  const direitaDoRosto = caixaRosto.x + caixaRosto.largura;
  if (direitaDoRosto < 1 - LARGURA - folga) {
    faixas.push({ x: 1 - LARGURA, y: 0, largura: LARGURA, altura: 1 });
  }
  // Rosto ocupando a largura inteira: usa a faixa do topo, acima da testa.
  if (faixas.length === 0 && caixaRosto.y > 0.12) {
    faixas.push({ x: 0, y: 0, largura: 1, altura: Math.min(0.1, caixaRosto.y - 0.02) });
  }
  return faixas;
}
