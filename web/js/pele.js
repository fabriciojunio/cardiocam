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

// Faixa de crominância da pele, partindo da clássica (Chai e Ngan, 1999) e
// alargada por medição em 05/10/2026. Os valores são os mesmos da versão em
// Python, em visao/pele.py, e precisam continuar sendo: as duas implementações
// medem a mesma coisa, e divergir aqui tornaria os números incomparáveis.
//
// O piso de Cr era 133, o valor do artigo. Medido num rosto real de tom médio
// sob luz fraca de ambiente interno, a mediana de Cr ficou em 130, três
// unidades abaixo do corte, e só 9,8% dos pixels do rosto passavam.
//
// Não é defeito de um caso: a faixa clássica veio de imagens bem iluminadas e
// de amostra pouco diversa, e é o tipo de limiar que funciona melhor para pele
// clara e bem iluminada. Baixar para 128 levou o acerto de 9,8% para 45,2%,
// mantendo 94,8% de rejeição do fundo e sem perder nenhum dos oito tons de
// referência nem aceitar nenhuma das seis cores que a suíte recusa.
const CR_MINIMO = 128;
const CR_MAXIMO = 173;
const CB_MINIMO = 77;
const CB_MAXIMO = 127;

// Piso de luminância, que depende do uso. São dois, e separá-los é o ponto.
//
// **Para medir**, 40. Abaixo disso o pixel não carrega sinal aproveitável: o
// pulso é 0,1% a 1% da intensidade, então em luminância 20 vale entre 0,02 e
// 0,2 nível, e o sensor quantiza em inteiros. Incluir na média só soma ruído.
//
// **Para localizar o rosto**, 10. Ali interessa a extensão da mancha e não a
// qualidade de cada pixel. Medido num rosto real sob luz fraca, a mediana de
// luminância ficou em 20 e a testa em 10: o corte em 40 descartava três quartos
// do rosto antes de olhar a cor, e o localizador não achava rosto nenhum.
const Y_MINIMO = 40;
export const Y_MINIMO_LOCALIZACAO = 10;
const Y_MAXIMO = 250;

/**
 * Decide se um pixel RGB é pele.
 *
 * `yMinimo` tem como padrão o piso da medição, que é o mais exigente. O
 * localizador de rosto passa `Y_MINIMO_LOCALIZACAO`.
 */
export function classificarPele(r, g, b, yMinimo = Y_MINIMO) {
  const y = 0.299 * r + 0.587 * g + 0.114 * b;
  if (y < yMinimo || y > Y_MAXIMO) return false;
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
/**
 * Monta a lista de pixels a promediar, uma única vez.
 *
 * Reaproveitar essa lista entre quadros é o que garante que a média seja
 * sempre sobre o mesmo conjunto de pixels. Parece detalhe e não é: com rosto
 * real, os pixels de borda entram e saem da máscara a cada quadro por causa do
 * ruído do sensor, e essa troca de conjunto vira ruído no sinal, na mesma
 * ordem de grandeza do que queremos medir. Congelar a seleção rendeu 3,7 dB
 * numa medição controlada.
 *
 * Devolve os deslocamentos dentro do array de pixels, já multiplicados por 4.
 */
export function construirSelecao(dados, largura, altura, passo = 2) {
  const selecao = [];
  for (let y = 0; y < altura; y += passo) {
    for (let x = 0; x < largura; x += passo) {
      const i = (y * largura + x) * 4;
      if (classificarPele(dados[i], dados[i + 1], dados[i + 2])) selecao.push(i);
    }
  }
  return selecao.length >= 30 ? Int32Array.from(selecao) : null;
}

/** Média dos canais sobre uma seleção já montada. */
export function mediaPorSelecao(dados, selecao) {
  if (!selecao || !selecao.length) return null;
  let somaR = 0;
  let somaG = 0;
  let somaB = 0;
  for (let k = 0; k < selecao.length; k++) {
    const i = selecao[k];
    somaR += dados[i];
    somaG += dados[i + 1];
    somaB += dados[i + 2];
  }
  const n = selecao.length;
  return { vermelho: somaR / n, verde: somaG / n, azul: somaB / n, pixels: n };
}

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
