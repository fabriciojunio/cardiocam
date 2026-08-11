/**
 * Segmentação de pele por crominância.
 *
 * Mesma ideia da versão em Python: converter para YCrCb e limiarizar apenas os
 * canais de cor, nunca o de brilho. A crominância da pele humana ocupa uma
 * faixa estreita e estável em qualquer tom, e o que varia entre pessoas de pele
 * clara e escura é sobretudo a luminância. Limiarizar só em Cr e Cb faz o
 * sistema medir todo mundo com a mesma competência, o que aqui é requisito de
 * correção e não detalhe de implementação.
 */

// Faixa clássica de crominância da pele (Chai e Ngan, 1999).
const CR_MINIMO = 133;
const CR_MAXIMO = 173;
const CB_MINIMO = 77;
const CB_MAXIMO = 127;

// Descarta pixels queimados ou totalmente escuros, onde a informação de cor
// perde o sentido.
const Y_MINIMO = 40;
const Y_MAXIMO = 250;

/** Decide se um pixel RGB é pele. */
export function classificarPele(r, g, b) {
  const y = 0.299 * r + 0.587 * g + 0.114 * b;
  if (y < Y_MINIMO || y > Y_MAXIMO) return false;
  const cr = (r - y) * 0.713 + 128;
  const cb = (b - y) * 0.564 + 128;
  return cr >= CR_MINIMO && cr <= CR_MAXIMO && cb >= CB_MINIMO && cb <= CB_MAXIMO;
}

/**
 * Média dos canais sobre os pixels de pele de uma região do canvas.
 *
 * A média espacial é o passo que viabiliza a medição inteira. A variação de
 * intensidade causada pelo pulso fica entre 0,1% e 1%, abaixo do ruído de
 * leitura de um pixel isolado; como esse ruído é aproximadamente independente
 * entre pixels, promediar N deles reduz o desvio por um fator de raiz de N.
 *
 * `passo` amostra um pixel a cada N para caber no orçamento de tempo de um
 * quadro em celular. Reduz o ganho de raiz de N, mas manter a taxa de quadros
 * estável importa mais.
 */
export function mediaDaPele(dados, largura, altura, passo = 2) {
  let somaR = 0;
  let somaG = 0;
  let somaB = 0;
  let pele = 0;
  let total = 0;

  for (let y = 0; y < altura; y += passo) {
    for (let x = 0; x < largura; x += passo) {
      const i = (y * largura + x) * 4;
      const r = dados[i];
      const g = dados[i + 1];
      const b = dados[i + 2];
      total++;
      if (classificarPele(r, g, b)) {
        somaR += r;
        somaG += g;
        somaB += b;
        pele++;
      }
    }
  }

  if (pele < 30) return null;
  return {
    vermelho: somaR / pele,
    verde: somaG / pele,
    azul: somaB / pele,
    pixels: pele,
    proporcao: total ? pele / total : 0,
  };
}
