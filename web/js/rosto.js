/**
 * Rastreamento do rosto: localização estável ao longo do tempo.
 *
 * ## O caminho até aqui, porque as duas tentativas anteriores ensinaram algo
 *
 * A versão original media dentro de um **oval fixo** e pedia que a pessoa se
 * encaixasse nele. Funcionava, e o comentário que justificava a escolha estava
 * certo quanto ao tremor da caixa. O preço era a pessoa ter de ficar imóvel.
 *
 * A segunda tentativa localizou o rosto pela **mancha de pele**, reaproveitando
 * o classificador de crominância que o projeto já tinha testado. Passou em todo
 * cenário sintético e falhou na primeira foto real, pela razão mais simples
 * possível: **a parede bege do quarto cai na faixa de crominância da pele e é
 * maior que o rosto**. A maior região conexa de "pele" era a parede. Nenhum
 * ajuste de limiar conserta isso, porque o problema não é o limiar: é a
 * premissa de que a maior mancha cor de pele é um rosto.
 *
 * A terceira, que é esta, usa o **detector em cascata de Haar**, portado para
 * JavaScript em `cascata.js`. Ele procura estrutura, o padrão de contraste de
 * um rosto, e não cor. Na mesma foto em que a cor falhou, acha o rosto a quatro
 * pixels de onde o OpenCV acha.
 *
 * A lição que fica, e que vale além deste módulo: **cenário sintético aprova
 * método que o mundo reprova**. O rosto sintético era uma mancha uniforme sobre
 * fundo azul, e nessa cena a cor basta. Quarto de verdade tem parede cor de
 * pele.
 *
 * ## O que este módulo acrescenta ao detector
 *
 * Estabilidade temporal, que o detector sozinho não tem:
 *
 * - **suavização exponencial** da caixa, porque o detector redetecta do zero e
 *   a caixa oscila alguns pixels mesmo com a pessoa imóvel. Esse tremor entra
 *   no sinal como ruído na banda errada, e trocá-lo por um pequeno atraso é o
 *   mal menor;
 * - **rejeição de salto**, porque rosto humano não atravessa um terço da
 *   própria largura entre dois quadros;
 * - **tolerância a falha**, porque piscar, virar de leve ou uma sombra
 *   passageira não deveriam zerar o sinal acumulado.
 *
 * São as mesmas três coisas, com os mesmos valores, da versão em Python.
 */

import { detectar, paraCinza } from './cascata.js';

/**
 * Proporções das regiões dentro da caixa do rosto.
 *
 * Iguais às da versão em Python e às que a versão web usava dentro do oval
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

/** Peso da detecção nova na média exponencial da caixa. */
const SUAVIZACAO = 0.25;

/** Salto aceito entre detecções, em fração da largura do rosto. */
const SALTO_MAXIMO = 0.35;

/** Execuções seguidas em que a última caixa continua valendo sem detecção. */
const TOLERANCIA = 6;

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
 * Rosto humano não atravessa um terço da própria largura entre duas
 * localizações, e não dobra de tamanho. Quando isso aparece, é outro rosto que
 * entrou no quadro ou um falso positivo.
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
 * Mantém a caixa do rosto estável ao longo do tempo.
 *
 * O modelo da cascata é passado no construtor em vez de carregado aqui, para
 * este módulo não depender de rede e continuar testável em Node.
 */
export class RastreadorDeRosto {
  constructor(modelo, { suavizacao = SUAVIZACAO, tolerancia = TOLERANCIA } = {}) {
    this.modelo = modelo;
    this.suavizacao = suavizacao;
    this.tolerancia = tolerancia;
    this.reiniciar();
  }

  reiniciar() {
    this.caixa = null;
    this.semRosto = 0;
    this.saltosRejeitados = 0;
    this.ultimaDeteccao = null;
  }

  get perdeuORosto() {
    return this.semRosto > this.tolerancia;
  }

  /**
   * Localiza o rosto num quadro RGBA e devolve a caixa estabilizada.
   *
   * @param {Uint8ClampedArray} rgba pixels do quadro
   * @returns {{x,y,largura,altura}|null} em frações do quadro
   */
  atualizar(rgba, largura, altura) {
    if (!this.modelo || !rgba) return null;

    const cinza = paraCinza(rgba, largura, altura);
    const achados = detectar(this.modelo, cinza, largura, altura);

    if (achados.length === 0) {
      this.semRosto += 1;
      if (this.caixa && !this.perdeuORosto) return this.caixa;
      this.caixa = null;
      return null;
    }

    // O maior rosto do quadro: quem está sendo medido é quem está mais perto
    // da câmera, e rosto ao fundo é distração.
    const melhor = achados[0];
    const medida = {
      x: melhor.x / largura,
      y: melhor.y / altura,
      largura: melhor.largura / largura,
      altura: melhor.altura / altura,
    };
    this.ultimaDeteccao = { ...medida, vizinhos: melhor.n };

    if (this.caixa && saltoAbsurdo(this.caixa, medida)) {
      this.saltosRejeitados += 1;
      this.semRosto += 1;
      if (!this.perdeuORosto) return this.caixa;
    }

    this.semRosto = 0;
    this.caixa = this.caixa
      ? interpolar(this.caixa, medida, this.suavizacao)
      : medida;
    return this.caixa;
  }

  /** Regiões de interesse do estado atual. */
  regioes() {
    return regioesDaCaixa(this.caixa);
  }
}

/**
 * Faixas de fundo que não encostam no rosto.
 *
 * O fundo serve de referência de iluminação, e só vale se não tiver pulso. Com
 * o rosto se movendo, uma faixa fixa pode acabar em cima dele, e aí a correção
 * passa a injetar o sinal que deveria remover.
 *
 * Devolver lista vazia é resposta legítima: sem fundo utilizável o medidor mede
 * sem rectificação, o que é melhor que rectificar por uma referência que é pele.
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
