/**
 * Localização e rastreamento do rosto, sem baixar modelo nenhum.
 *
 * ## Por que isto passou a existir
 *
 * A versão web media dentro de um oval fixo na tela e pedia que a pessoa
 * encaixasse o rosto nele. O comentário que justificava a escolha estava
 * tecnicamente correto: com o rosto ancorado num lugar fixo, a região medida
 * para de tremer entre quadros, e o tremor da caixa é o que mais estraga a
 * medição automática.
 *
 * Só que o preço aparece no primeiro uso real. A pessoa tem de ficar imóvel, a
 * câmera também, e sair do oval por meio segundo contamina a janela inteira,
 * porque a média passa a incluir parede em vez de pele. Isso é uma variação de
 * amplitude muito maior que o pulso, e na banda errada.
 *
 * ## Por que não um modelo de rede neural
 *
 * O caminho óbvio seria o BlazeFace, via MediaPipe. Foi medido e descartado por
 * três motivos, nesta ordem de peso:
 *
 * 1. **Tamanho.** O runtime em WebAssembly tem 9,3 MB e o pacote todo passa de
 *    18 MB. Numa página que precisa funcionar em celular, isso não é detalhe:
 *    é a diferença entre abrir e não abrir.
 * 2. **Política de segurança.** O site serve com `script-src 'self'` e
 *    `connect-src 'none'`. Baixar modelo de terceiro exigiria afrouxar as duas
 *    diretivas, e elas são o que garante que nenhum dado saia daqui. Trocar
 *    uma garantia verificável por conveniência é troca ruim.
 * 3. **Testabilidade.** Modelo em WebAssembly não roda na suíte em Node, que é
 *    onde os 356 casos deste projeto moram. Um rastreador que não pode ser
 *    testado é um rastreador em que não se confia.
 *
 * ## Como funciona então
 *
 * Reaproveitando o que o projeto já tem testado: o classificador de pele por
 * crominância. Ele limiariza em Cr e Cb e nunca em luminância, de propósito, o
 * que o torna estável em qualquer tom de pele. É a base certa para localizar
 * rosto sem treinar nada.
 *
 * O caminho é clássico e barato:
 *
 * 1. histograma de pixels de pele por coluna e por linha, sobre o quadro já
 *    reduzido que o medidor usa;
 * 2. extensão horizontal e vertical por limiar relativo ao máximo, o que
 *    descarta pixel de pele isolado sem precisar de componente conexo;
 * 3. **corte da altura pela proporção do rosto.** Pescoço e colo são pele e
 *    entrariam na caixa, puxando-a para baixo. Um rosto humano tem altura
 *    entre 1,2 e 1,6 vez a largura, então a altura é limitada a 1,45 vez;
 * 4. suavização exponencial e rejeição de salto, iguais às da versão em
 *    Python e pelos mesmos motivos.
 *
 * As regiões saem das mesmas proporções da caixa que a versão em Python usa
 * quando não tem os olhos. Isso é deliberado: as duas implementações precisam
 * medir a mesma coisa para que os números sejam comparáveis entre elas.
 *
 * ## O que este rastreador não faz
 *
 * Não distingue rosto de qualquer outra mancha de pele grande. Mão na frente da
 * câmera, braço nu atravessando o quadro ou madeira de tom próximo ao da pele
 * deslocam a caixa. A rejeição de salto cobre o caso brusco; a mão parada ao
 * lado do rosto, não. É a limitação honesta de localizar por cor em vez de por
 * forma, e é o preço de não baixar 9 MB.
 *
 * Também não estima pose. Virar a cabeça muda o ângulo entre a pele e a luz, e
 * isso muda a cor refletida por um motivo que não é o pulso. Acompanhar o rosto
 * resolve medir o lugar certo, não a luz mudando.
 */

import { classificarPele } from './pele.js';

/**
 * Proporções das regiões dentro da caixa do rosto.
 *
 * Iguais às da versão em Python e às que a versão web já usava dentro do oval
 * fixo. Mudar aqui sem mudar lá quebraria a comparabilidade entre as duas, que
 * é o que permite usar uma para validar a outra.
 *
 * Olhos e boca ficam fora de propósito: piscar e falar produzem movimento
 * exatamente na banda de frequência do coração, e esse artefato nenhuma
 * filtragem posterior remove.
 */
export const REGIOES_NA_CAIXA = Object.freeze([
  Object.freeze({ x: 0.24, y: 0.12, largura: 0.52, altura: 0.20 }),
  Object.freeze({ x: 0.08, y: 0.50, largura: 0.30, altura: 0.30 }),
  Object.freeze({ x: 0.62, y: 0.50, largura: 0.30, altura: 0.30 }),
]);

/**
 * Altura máxima da caixa, em múltiplos da largura.
 *
 * Existe por causa do pescoço. Pescoço e colo são pele pela crominância, e sem
 * este corte a caixa desce até a camiseta, jogando a região da testa para o
 * meio do rosto e as bochechas para a mandíbula.
 *
 * O valor vem da proporção do rosto humano, que fica entre 1,2 e 1,6 vez a
 * largura. 1,45 deixa folga para cabelo na testa sem alcançar o pescoço.
 */
export const ALTURA_MAXIMA_RELATIVA = 1.45;

/** Fração do máximo do histograma que conta como "tem pele nesta faixa". */
const LIMIAR_DO_HISTOGRAMA = 0.28;

/** Pixels de pele mínimos para considerar que há rosto no quadro. */
const PIXELS_MINIMOS = 180;

/** Peso da medição nova na média exponencial da caixa. */
const SUAVIZACAO = 0.25;

/** Salto aceito entre quadros, em fração da largura do rosto. */
const SALTO_MAXIMO = 0.35;

/** Quadros seguidos em que a última caixa continua valendo sem detecção. */
const TOLERANCIA_QUADROS = 15;

/**
 * Extensão de um histograma, pelo limiar relativo ao máximo.
 *
 * Devolve o primeiro e o último índice acima do limiar. Usar limiar relativo e
 * não absoluto é o que faz isto funcionar igual com rosto perto e longe da
 * câmera, e com pouca ou muita luz.
 */
function extensao(histograma, limiarRelativo) {
  let maximo = 0;
  for (const valor of histograma) if (valor > maximo) maximo = valor;
  if (maximo === 0) return null;

  const limiar = maximo * limiarRelativo;
  let inicio = -1;
  let fim = -1;
  for (let i = 0; i < histograma.length; i++) {
    if (histograma[i] >= limiar) {
      if (inicio < 0) inicio = i;
      fim = i;
    }
  }
  return inicio < 0 ? null : { inicio, fim };
}

/**
 * Localiza o rosto num quadro, pela mancha de pele.
 *
 * `dados` é o array RGBA de `getImageData`. `passo` amostra um pixel a cada N
 * em cada eixo: com passo 2 o custo cai a um quarto e a caixa resultante muda
 * menos de um pixel, porque o que se mede aqui é a extensão de uma mancha
 * grande e não a posição de uma borda fina.
 *
 * @returns {{x,y,largura,altura}|null} caixa em frações do quadro
 */
export function localizarRosto(dados, largura, altura, passo = 2) {
  if (!dados || largura < 8 || altura < 8) return null;

  const porColuna = new Float32Array(largura);
  const porLinha = new Float32Array(altura);
  let total = 0;

  for (let y = 0; y < altura; y += passo) {
    const base = y * largura;
    for (let x = 0; x < largura; x += passo) {
      const i = (base + x) * 4;
      if (!classificarPele(dados[i], dados[i + 1], dados[i + 2])) continue;
      porColuna[x] += 1;
      porLinha[y] += 1;
      total += 1;
    }
  }

  // Normaliza pelo número de amostras, para o limiar não depender do passo.
  if (total * passo * passo < PIXELS_MINIMOS) return null;

  const colunas = extensao(porColuna, LIMIAR_DO_HISTOGRAMA);
  const linhas = extensao(porLinha, LIMIAR_DO_HISTOGRAMA);
  if (!colunas || !linhas) return null;

  const x = colunas.inicio / largura;
  const larguraCaixa = (colunas.fim - colunas.inicio + 1) / largura;
  const y = linhas.inicio / altura;
  let alturaCaixa = (linhas.fim - linhas.inicio + 1) / altura;

  if (larguraCaixa <= 0 || alturaCaixa <= 0) return null;

  // Corte pela proporção do rosto, medido em pixels e não em frações, porque
  // o quadro não é quadrado e comparar frações compararia coisas diferentes.
  const larguraEmPixels = larguraCaixa * largura;
  const alturaMaximaEmPixels = larguraEmPixels * ALTURA_MAXIMA_RELATIVA;
  if (alturaCaixa * altura > alturaMaximaEmPixels) {
    alturaCaixa = alturaMaximaEmPixels / altura;
  }

  return {
    x,
    y,
    largura: larguraCaixa,
    altura: Math.min(alturaCaixa, 1 - y),
  };
}

/** Regiões de interesse dentro da caixa do rosto, em frações do quadro. */
export function regioesDaCaixa(caixa) {
  if (!caixa || caixa.largura <= 0 || caixa.altura <= 0) return null;
  return REGIOES_NA_CAIXA.map((r) =>
    limitar({
      x: caixa.x + r.x * caixa.largura,
      y: caixa.y + r.y * caixa.altura,
      largura: r.largura * caixa.largura,
      altura: r.altura * caixa.altura,
    }),
  );
}

function limitar(regiao) {
  const x = Math.max(0, Math.min(1, regiao.x));
  const y = Math.max(0, Math.min(1, regiao.y));
  return {
    x,
    y,
    largura: Math.max(0, Math.min(1 - x, regiao.largura)),
    altura: Math.max(0, Math.min(1 - y, regiao.altura)),
  };
}

function interpolar(antiga, nova, peso) {
  return {
    x: antiga.x + (nova.x - antiga.x) * peso,
    y: antiga.y + (nova.y - antiga.y) * peso,
    largura: antiga.largura + (nova.largura - antiga.largura) * peso,
    altura: antiga.altura + (nova.altura - antiga.altura) * peso,
  };
}

/**
 * Decide se a caixa nova é salto absurdo em relação à anterior.
 *
 * Rosto humano não atravessa um terço da própria largura em 33 ms, e não dobra
 * de tamanho entre dois quadros. Quando isso aparece, é mancha de pele que
 * entrou no quadro, não a pessoa se movendo.
 */
export function saltoAbsurdo(antiga, nova) {
  if (!antiga) return false;
  const dx = nova.x + nova.largura / 2 - (antiga.x + antiga.largura / 2);
  const dy = nova.y + nova.altura / 2 - (antiga.y + antiga.altura / 2);
  const referencia = Math.max(antiga.largura, 1e-6);
  if (Math.hypot(dx, dy) > SALTO_MAXIMO * referencia) return true;
  const razao = nova.largura / referencia;
  return razao > 1.6 || razao < 0.625;
}

/**
 * Mantém a caixa estável ao longo do tempo.
 *
 * Suavizar troca o tremor da localização por um atraso, e o atraso é o mal
 * menor: tremor entra no sinal como ruído na banda errada, e atraso só desloca
 * a região alguns pixels, o que a folga das proporções absorve.
 */
export class RastreadorDeRosto {
  constructor({ suavizacao = SUAVIZACAO, tolerancia = TOLERANCIA_QUADROS } = {}) {
    this.suavizacao = suavizacao;
    this.tolerancia = tolerancia;
    this.reiniciar();
  }

  reiniciar() {
    this.caixa = null;
    this.quadrosSemRosto = 0;
    this.saltosRejeitados = 0;
  }

  get perdeuORosto() {
    return this.quadrosSemRosto > this.tolerancia;
  }

  /** Processa um quadro e devolve a caixa estabilizada, ou null. */
  atualizar(dados, largura, altura, passo = 2) {
    const medida = localizarRosto(dados, largura, altura, passo);

    if (!medida) {
      this.quadrosSemRosto += 1;
      if (this.caixa && !this.perdeuORosto) return this.caixa;
      this.caixa = null;
      return null;
    }

    if (this.caixa && saltoAbsurdo(this.caixa, medida)) {
      this.saltosRejeitados += 1;
      this.quadrosSemRosto += 1;
      if (!this.perdeuORosto) return this.caixa;
    }

    this.quadrosSemRosto = 0;
    this.caixa = this.caixa
      ? interpolar(this.caixa, medida, this.suavizacao)
      : medida;
    return this.caixa;
  }

  /** Regiões de interesse do quadro atual. */
  regioes() {
    return regioesDaCaixa(this.caixa);
  }
}

/**
 * Faixas de fundo que não encostam no rosto rastreado.
 *
 * Com o oval fixo, o fundo eram duas faixas laterais fixas, e isso funcionava
 * porque o rosto estava sempre no meio. Com o rosto se movendo, uma faixa fixa
 * pode acabar em cima dele, e aí a referência de iluminação passa a conter
 * pulso, que é o oposto do que ela serve para fazer.
 *
 * Devolver lista vazia é resposta legítima: sem fundo utilizável, o medidor
 * mede sem rectificação, o que é melhor que rectificar por uma referência que
 * é pele.
 */
export function regioesDeFundo(caixaRosto) {
  const LARGURA = 0.13;
  const FOLGA = 0.03;

  if (!caixaRosto) {
    return [
      { x: 0, y: 0, largura: LARGURA, altura: 1 },
      { x: 1 - LARGURA, y: 0, largura: LARGURA, altura: 1 },
    ];
  }

  const faixas = [];
  if (caixaRosto.x > LARGURA + FOLGA) {
    faixas.push({ x: 0, y: 0, largura: LARGURA, altura: 1 });
  }
  if (caixaRosto.x + caixaRosto.largura < 1 - LARGURA - FOLGA) {
    faixas.push({ x: 1 - LARGURA, y: 0, largura: LARGURA, altura: 1 });
  }
  if (faixas.length === 0 && caixaRosto.y > 0.12) {
    faixas.push({
      x: 0,
      y: 0,
      largura: 1,
      altura: Math.min(0.1, caixaRosto.y - 0.02),
    });
  }
  return faixas;
}
