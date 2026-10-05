/**
 * Detector de rosto em cascata de Haar, em JavaScript puro.
 *
 * ## Por que existe
 *
 * A versão web localizava o rosto pela mancha de pele, e isso foi medido num
 * quarto comum e falhou pela razão mais simples possível: **a parede bege cai
 * na faixa de crominância da pele e é maior que o rosto**. A maior região
 * conexa de "pele" era a parede. Nenhum ajuste de limiar conserta, porque o
 * problema não é o limiar: é a premissa de que a maior mancha cor de pele é
 * um rosto.
 *
 * Na mesma imagem, a cascata acha o rosto com precisão, nas três variantes do
 * modelo, com e sem equalização, e em três resoluções diferentes. A diferença
 * é que ela procura **estrutura**, o padrão de contraste de um rosto, e não
 * cor. Pele é consequência; rosto é o que se quer.
 *
 * O BlazeFace via MediaPipe foi medido e descartado antes: 9,3 MB de runtime
 * em WebAssembly, política de segurança do site que precisaria ser afrouxada
 * em duas diretivas, e impossibilidade de rodar na suíte em Node. A cascata
 * pesa **107 KB de JSON**, roda em JavaScript puro, e é o mesmo algoritmo da
 * versão em Python, o que coloca as duas implementações em paridade.
 *
 * ## Como funciona
 *
 * Viola e Jones (2001). Três ideias que se encaixam:
 *
 * 1. **Imagem integral.** Cada ponto guarda a soma de tudo acima e à esquerda.
 *    Com isso a soma de qualquer retângulo sai em quatro acessos, qualquer que
 *    seja o tamanho dele. É o que torna viável avaliar milhares de retângulos
 *    por janela.
 * 2. **Classificador fraco.** Cada um olha um arranjo de dois ou três
 *    retângulos, soma com pesos, e decide por um limiar. Sozinho acerta pouco
 *    mais que o acaso; somados com os pesos do treinamento, acertam muito.
 * 3. **Cascata.** Os classificadores são agrupados em 20 estágios, do mais
 *    barato ao mais caro. Uma janela que falha no estágio 1 é descartada sem
 *    passar pelos outros 19. Como a esmagadora maioria das janelas não tem
 *    rosto, quase todas morrem cedo, e é daí que vem a velocidade.
 *
 * ## Decisão de implementação: pirâmide de imagem, não de características
 *
 * O OpenCV escala as características e mantém a imagem. Aqui é o contrário: a
 * imagem é reduzida em passos e a janela fica fixa em 20x20.
 *
 * O resultado é equivalente, e a escolha é por correção: escalar característica
 * exige reproduzir exatamente como o OpenCV reescala peso e área, que é
 * detalhe sutil e fácil de errar por um fator que só aparece em certos
 * tamanhos de rosto. Reduzir a imagem não tem nenhuma sutileza. O custo é
 * refazer a imagem integral por nível, o que é barato perto de avaliar a
 * cascata.
 *
 * A equivalência não é afirmada: o teste compara a saída deste módulo com a do
 * OpenCV sobre as mesmas imagens.
 */

/**
 * Passo da pirâmide de escalas.
 *
 * 1,1 e não 1,2, e a diferença foi medida: com 1,2 o rosto de referência
 * produzia 3 detecções sobrepostas, exatamente o mínimo exigido, e nessa
 * condição a detecção some com qualquer mudança pequena de iluminação ou de
 * recorte. Com 1,1 são 5, e a margem é o que separa "funciona" de "funcionou
 * naquela foto".
 *
 * Custa 189 ms contra 111 ms no mesmo quadro. Vale, porque o detector não roda
 * a cada quadro: ele roda algumas vezes por segundo, e a caixa suavizada vale
 * entre uma execução e outra.
 */
const FATOR_DE_ESCALA = 1.1;

/**
 * Detecções sobrepostas exigidas para aceitar uma região.
 *
 * Um rosto de verdade é detectado várias vezes, em posições e escalas vizinhas.
 * Falso positivo costuma aparecer uma vez só. Exigir vizinhos é o filtro mais
 * eficaz que existe aqui, e custa nada.
 */
const VIZINHOS_MINIMOS = 4;

/** De quantos em quantos pixels a janela anda, na escala do nível. */
const PASSO_DA_JANELA = 2;

/**
 * Imagem integral e imagem integral dos quadrados.
 *
 * As duas juntas dão soma e variância de qualquer retângulo em tempo
 * constante. A variância é necessária porque a cascata compara o valor da
 * característica contra o limiar **multiplicado pelo desvio padrão da janela**:
 * sem isso, o mesmo rosto sob mais luz teria valores maiores e não passaria nos
 * mesmos limiares. É essa normalização que faz o detector funcionar com
 * iluminação variada.
 *
 * As matrizes têm uma linha e uma coluna a mais, zeradas, para a soma de
 * retângulo não precisar de condicional na borda.
 */
export function imagemIntegral(cinza, largura, altura) {
  const l = largura + 1;
  const soma = new Float64Array(l * (altura + 1));
  const somaQuadrados = new Float64Array(l * (altura + 1));

  for (let y = 0; y < altura; y++) {
    let linha = 0;
    let linhaQuadrados = 0;
    for (let x = 0; x < largura; x++) {
      const v = cinza[y * largura + x];
      linha += v;
      linhaQuadrados += v * v;
      soma[(y + 1) * l + (x + 1)] = soma[y * l + (x + 1)] + linha;
      somaQuadrados[(y + 1) * l + (x + 1)] = somaQuadrados[y * l + (x + 1)] + linhaQuadrados;
    }
  }
  return { soma, somaQuadrados, passo: l };
}

/** Soma de um retângulo, em quatro acessos. */
function somaRetangulo(integral, passo, x, y, l, a) {
  const a0 = y * passo + x;
  const a1 = a0 + l;
  const b0 = (y + a) * passo + x;
  const b1 = b0 + l;
  return integral[a0] - integral[a1] - integral[b0] + integral[b1];
}

/**
 * Converte RGBA para tons de cinza, com os coeficientes da BT.601.
 *
 * Os mesmos usados na conversão para YCrCb da segmentação de pele, de
 * propósito: duas definições de luminância no mesmo projeto seriam duas
 * respostas diferentes para a mesma pergunta.
 */
export function paraCinza(rgba, largura, altura) {
  const cinza = new Uint8ClampedArray(largura * altura);
  for (let i = 0, j = 0; i < cinza.length; i++, j += 4) {
    cinza[i] = 0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2];
  }
  return cinza;
}

/**
 * Reduz a imagem em tons de cinza por interpolação bilinear.
 *
 * A escolha do método não é indiferente, e isso foi medido. A primeira versão
 * reduzia por média de bloco, que é melhor contra serrilhado e reduz ruído. Só
 * que a cascata foi treinada e é avaliada pelo OpenCV sobre imagens reduzidas
 * por **bilinear**, e os limiares dos estágios carregam essa escolha dentro
 * deles.
 *
 * O efeito foi medido na janela exata de um rosto que o OpenCV encontra: com
 * média de bloco, ela passava os estágios 1 e 2 com folga e **morria no
 * estágio 3 por 2%**. Não era erro de fórmula, era a imagem chegando
 * ligeiramente diferente do que o treinamento esperava.
 *
 * Fica registrado porque a conclusão é contraintuitiva: aqui o método de
 * reamostragem teoricamente pior é o certo, porque é o que o modelo conhece.
 *
 * `bilinear = false` usa média de bloco, e serve para medir a diferença.
 */
export function reduzir(cinza, largura, altura, novaLargura, novaAltura, bilinear = true) {
  const saida = new Uint8ClampedArray(novaLargura * novaAltura);
  const escalaX = largura / novaLargura;
  const escalaY = altura / novaAltura;

  if (bilinear) {
    for (let y = 0; y < novaAltura; y++) {
      // Meio pixel de deslocamento: mapeia o centro do pixel de saída para o
      // centro correspondente na entrada, que é a convenção do OpenCV. Sem
      // isso a imagem reduzida sai deslocada meio pixel, e o detector erra a
      // posição por uma fração da janela.
      const sy = (y + 0.5) * escalaY - 0.5;
      const y0 = Math.max(0, Math.min(altura - 1, Math.floor(sy)));
      const y1 = Math.min(altura - 1, y0 + 1);
      const fy = Math.max(0, sy - y0);

      for (let x = 0; x < novaLargura; x++) {
        const sx = (x + 0.5) * escalaX - 0.5;
        const x0 = Math.max(0, Math.min(largura - 1, Math.floor(sx)));
        const x1 = Math.min(largura - 1, x0 + 1);
        const fx = Math.max(0, sx - x0);

        const p00 = cinza[y0 * largura + x0];
        const p01 = cinza[y0 * largura + x1];
        const p10 = cinza[y1 * largura + x0];
        const p11 = cinza[y1 * largura + x1];

        const cima = p00 + (p01 - p00) * fx;
        const baixo = p10 + (p11 - p10) * fx;
        saida[y * novaLargura + x] = cima + (baixo - cima) * fy;
      }
    }
    return saida;
  }

  for (let y = 0; y < novaAltura; y++) {
    const y0 = Math.floor(y * escalaY);
    const y1 = Math.min(altura, Math.max(y0 + 1, Math.floor((y + 1) * escalaY)));
    for (let x = 0; x < novaLargura; x++) {
      const x0 = Math.floor(x * escalaX);
      const x1 = Math.min(largura, Math.max(x0 + 1, Math.floor((x + 1) * escalaX)));
      let soma = 0;
      let n = 0;
      for (let yy = y0; yy < y1; yy++) {
        for (let xx = x0; xx < x1; xx++) {
          soma += cinza[yy * largura + xx];
          n += 1;
        }
      }
      saida[y * novaLargura + x] = n ? soma / n : 0;
    }
  }
  return saida;
}

/**
 * Fator de normalização da janela, na definição exata do OpenCV.
 *
 * Esta função existe por causa de um erro que custou uma rodada inteira: a
 * primeira versão normalizava pela área da janela cheia (20x20) e comparava
 * contra o desvio padrão simples. O detector então não achava **nenhum** rosto
 * onde o OpenCV achava um, e o sintoma não apontava a causa.
 *
 * O OpenCV faz duas coisas diferentes, e as duas importam:
 *
 * 1. A estatística é tomada sobre a janela **recuada em um pixel de cada
 *    lado**, isto é, 18x18 numa janela de 20x20. A borda fica de fora porque
 *    é onde mais entra fundo.
 * 2. O fator não é o desvio padrão, é `sqrt(area * somaDosQuadrados - soma²)`,
 *    que equivale a `area * desvioPadrão`. A comparação é
 *    `valorDaCaracteristica / fator < limiar`, sem nenhuma outra divisão.
 *
 * Misturar as duas convenções dá um erro de escala de centenas de vezes, e aí
 * nenhuma janela passa do primeiro estágio.
 */
function fatorDeNormalizacao(soma, somaQuadrados, passo, jx, jy, jl, ja) {
  const x = jx + 1;
  const y = jy + 1;
  const l = jl - 2;
  const a = ja - 2;
  const area = l * a;

  const s = somaRetangulo(soma, passo, x, y, l, a);
  const sq = somaRetangulo(somaQuadrados, passo, x, y, l, a);

  const nf = area * sq - s * s;
  // Região sem variação nenhuma: o OpenCV usa 1 em vez de pular, e manter o
  // mesmo comportamento é o que permite comparar as duas saídas.
  return nf > 0 ? Math.sqrt(nf) : 1;
}

/**
 * Avalia a cascata numa janela.
 *
 * `inversoDoFator` é `1 / fatorDeNormalizacao`, já calculado pelo chamador: ele
 * é o mesmo para todos os estágios, e uma divisão por característica seria
 * milhares de divisões por janela.
 */
function passouNaCascata(modelo, integral, passo, jx, jy, inversoDoFator) {
  const { estagios, caracteristicas } = modelo;

  for (let e = 0; e < estagios.length; e++) {
    const [limiarDoEstagio, fracos] = estagios[e];
    let soma = 0;

    for (let f = 0; f < fracos.length; f++) {
      const [nos, folhas] = fracos[f];

      /*
        Cada classificador fraco é uma **árvore**, não um toco de decisão.

        Supor que eram tocos foi o erro que mais custou aqui. O detector
        passava os dois primeiros estágios e morria no terceiro, em toda
        posição e toda escala, porque metade de cada árvore estava sendo
        ignorada. O sintoma não aponta a causa: parece ajuste de limiar.

        Convenção dos ramos, conferida contra o OpenCV:
          ramo > 0   outro nó interno desta árvore
          ramo <= 0  folha de índice -ramo
      */
      let indiceDoNo = 0;
      for (;;) {
        const [esquerda, direita, indiceDaCaracteristica, limiar] = nos[indiceDoNo];
        const rects = caracteristicas[indiceDaCaracteristica];

        let valor = 0;
        for (let r = 0; r < rects.length; r++) {
          const [rx, ry, rl, ra, peso] = rects[r];
          valor += somaRetangulo(integral, passo, jx + rx, jy + ry, rl, ra) * peso;
        }

        const ramo = valor * inversoDoFator < limiar ? esquerda : direita;
        if (ramo <= 0) {
          soma += folhas[-ramo];
          break;
        }
        indiceDoNo = ramo;
      }
    }

    // Rejeição antecipada: é daqui que vem a velocidade da cascata.
    if (soma < limiarDoEstagio) return false;
  }
  return true;
}

/**
 * Agrupa detecções sobrepostas e devolve uma caixa por rosto.
 *
 * Sem isto o mesmo rosto sai como dezenas de caixas quase iguais. O critério de
 * fusão é sobreposição relativa ao tamanho, e não distância absoluta, para
 * funcionar igual com rosto perto e longe da câmera.
 */
function agrupar(candidatos, vizinhosMinimos) {
  const grupos = [];

  for (const c of candidatos) {
    let encontrou = false;
    for (const g of grupos) {
      const dx = Math.abs(c.x + c.largura / 2 - (g.x + g.largura / 2));
      const dy = Math.abs(c.y + c.altura / 2 - (g.y + g.altura / 2));
      const tolerancia = Math.min(c.largura, g.largura) * 0.4;
      const razao = c.largura / g.largura;
      if (dx < tolerancia && dy < tolerancia && razao > 0.65 && razao < 1.55) {
        // Média corrida, para o grupo convergir para o centro das detecções.
        const n = g.n + 1;
        g.x = (g.x * g.n + c.x) / n;
        g.y = (g.y * g.n + c.y) / n;
        g.largura = (g.largura * g.n + c.largura) / n;
        g.altura = (g.altura * g.n + c.altura) / n;
        g.n = n;
        encontrou = true;
        break;
      }
    }
    if (!encontrou) grupos.push({ ...c, n: 1 });
  }

  return grupos
    .filter((g) => g.n >= vizinhosMinimos)
    .sort((a, b) => b.largura * b.altura - a.largura * a.altura);
}

/**
 * Procura rostos numa imagem em tons de cinza.
 *
 * `minimoRelativo` é o menor rosto aceito, em fração do lado menor do quadro.
 * O padrão de 0,25 parece exigente e não é concessão de desempenho: rosto
 * menor que um quarto da altura do quadro **não tem pixels suficientes** para a
 * média espacial tirar do ruído um sinal que vale 0,1% a 1% da intensidade.
 * Aceitar um seria prometer uma medição que não vai sair, e gastar tempo
 * procurando onde não adianta encontrar.
 *
 * @returns {Array<{x,y,largura,altura,n}>} caixas em pixels, da maior para a menor
 */
export function detectar(modelo, cinza, largura, altura, opcoes = {}) {
  const {
    minimoRelativo = 0.25,
    maximoRelativo = 1.0,
    fatorDeEscala = FATOR_DE_ESCALA,
    vizinhosMinimos = VIZINHOS_MINIMOS,
    passoDaJanela = PASSO_DA_JANELA,
    regiao = null,
  } = opcoes;

  const jl = modelo.largura;
  const ja = modelo.altura;
  const menorLado = Math.min(largura, altura);
  const ladoMinimo = Math.max(jl, Math.round(menorLado * minimoRelativo));
  const ladoMaximo = Math.max(ladoMinimo, Math.round(menorLado * maximoRelativo));

  const candidatos = [];

  // A pirâmide começa na escala em que o rosto mínimo cabe na janela base, e
  // sobe até a imagem ficar menor que a janela ou até passar do rosto máximo.
  let escala = ladoMinimo / jl;
  while (true) {
    if (jl * escala > ladoMaximo) break;

    const nl = Math.floor(largura / escala);
    const na = Math.floor(altura / escala);
    if (nl < jl || na < ja) break;

    const nivel = escala === 1 ? cinza : reduzir(cinza, largura, altura, nl, na);
    const { soma, somaQuadrados, passo } = imagemIntegral(nivel, nl, na);

    /*
      Limites da varredura neste nível.

      Com `regiao`, a busca cobre só o entorno do rosto anterior. É a economia
      que mais vale: a varredura cheia custa cerca de 110 ms neste quadro, e
      quase tudo disso é procurar rosto onde já se sabe que não tem. Depois da
      primeira detecção, o rosto está a poucos pixels de onde estava, e cobrir
      uma margem em volta basta.

      Quem perde o rosto volta a varrer tudo, e é o chamador que decide isso ao
      deixar de passar `regiao`.
    */
    let x0 = 0;
    let y0 = 0;
    let x1 = nl - jl - 1;
    let y1 = na - ja - 1;

    if (regiao) {
      x0 = Math.max(0, Math.floor(regiao.x / escala));
      y0 = Math.max(0, Math.floor(regiao.y / escala));
      x1 = Math.min(x1, Math.ceil((regiao.x + regiao.largura) / escala) - jl);
      y1 = Math.min(y1, Math.ceil((regiao.y + regiao.altura) / escala) - ja);
    }

    for (let y = y0; y <= y1; y += passoDaJanela) {
      for (let x = x0; x <= x1; x += passoDaJanela) {
        const fator = fatorDeNormalizacao(soma, somaQuadrados, passo, x, y, jl, ja);

        if (passouNaCascata(modelo, soma, passo, x, y, 1 / fator)) {
          candidatos.push({
            x: x * escala,
            y: y * escala,
            largura: jl * escala,
            altura: ja * escala,
          });
        }
      }
    }

    escala *= fatorDeEscala;
  }

  return agrupar(candidatos, vizinhosMinimos);
}

/**
 * Carrega o modelo do próprio site.
 *
 * Mesma origem de propósito: a política de segurança da página é
 * `connect-src 'self'`, e ela é o que garante que nada sai daqui. Buscar o
 * modelo de terceiro exigiria afrouxá-la, que é trocar uma garantia
 * verificável por conveniência.
 */
export async function carregarModelo(caminho = 'modelo/cascata-rosto.json') {
  const resposta = await fetch(caminho, { cache: 'force-cache' });
  if (!resposta.ok) {
    throw new Error(`não consegui carregar a cascata: ${resposta.status}`);
  }
  return resposta.json();
}
