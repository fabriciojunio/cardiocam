/**
 * Compara o detector em cascata deste projeto com o do OpenCV.
 *
 * Este é o teste que decide se o porte está certo. A implementação em
 * JavaScript usa pirâmide de imagem onde o OpenCV escala as características, e
 * os dois caminhos deveriam ser equivalentes. "Deveriam" não basta: aqui os
 * dois rodam sobre **o mesmo quadro, byte a byte**, e as caixas são comparadas.
 *
 * O quadro vem de `ferramentas/exportar_quadro.py`, que grava os pixels em
 * tons de cinza crus e o resultado do OpenCV num JSON. Node não decodifica PNG
 * sem dependência, e acrescentar uma só para teste seria peso desnecessário;
 * além disso, pixel cru deixa explícito que o que está sob teste é o detector e
 * não o decodificador de imagem.
 *
 * As imagens de referência são capturas reais, de cena real. A primeira é a que
 * derrubou a localização por cor: um quarto com parede bege, que a segmentação
 * de pele classificava como rosto por ser a maior mancha na faixa de
 * crominância.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { detectar, imagemIntegral, reduzir } from '../js/cascata.js';
import { RastreadorDeRosto } from '../js/rosto.js';

const AQUI = dirname(fileURLToPath(import.meta.url));
const QUADROS = join(AQUI, 'quadros');

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) {
    passaram += 1;
  } else {
    falharam += 1;
    falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
  }
}

function grupo(titulo) {
  process.stdout.write(`\n${titulo}\n`);
}

// ---------------------------------------------------------------------------
grupo('Imagem integral');

{
  /* Imagem 3x3 com valores conhecidos. A soma de qualquer retângulo tem de
     bater com a soma feita na mão, senão todo o resto está errado e os erros
     vão aparecer como "não acha rosto", que é um sintoma que não aponta a
     causa. */
  const cinza = new Uint8ClampedArray([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  const { soma, passo } = imagemIntegral(cinza, 3, 3);

  const retangulo = (x, y, l, a) =>
    soma[y * passo + x] - soma[y * passo + x + l]
    - soma[(y + a) * passo + x] + soma[(y + a) * passo + x + l];

  verificar('soma da imagem inteira', retangulo(0, 0, 3, 3) === 45);
  verificar('soma da primeira linha', retangulo(0, 0, 3, 1) === 6);
  verificar('soma da primeira coluna', retangulo(0, 0, 1, 3) === 12);
  verificar('soma do canto inferior direito 2x2', retangulo(1, 1, 2, 2) === 28);
  verificar('soma de um pixel só', retangulo(1, 1, 1, 1) === 5);
  verificar('soma de retângulo vazio', retangulo(1, 1, 0, 0) === 0);
}

{
  /* A soma dos quadrados é o que permite normalizar pela variância da janela,
     e é ela que faz o detector funcionar com iluminação diferente. Sem este
     teste, um erro aqui apareceria como "acha rosto em imagem clara e não em
     imagem escura", que é difícil de ligar à causa. */
  const cinza = new Uint8ClampedArray([2, 4, 6, 8]);
  const { somaQuadrados, passo } = imagemIntegral(cinza, 2, 2);
  const total = somaQuadrados[2 * passo + 2];
  verificar('soma dos quadrados', total === 4 + 16 + 36 + 64,
    `deu ${total}, esperado 120`);
}

// ---------------------------------------------------------------------------
grupo('Redução por média de bloco');

{
  const cinza = new Uint8ClampedArray([
    10, 20, 30, 40,
    10, 20, 30, 40,
    50, 60, 70, 80,
    50, 60, 70, 80,
  ]);
  const metade = reduzir(cinza, 4, 4, 2, 2);
  verificar('reduzir pela metade promedia o bloco 2x2',
    metade[0] === 15 && metade[1] === 35 && metade[2] === 55 && metade[3] === 75,
    `deu [${[...metade].join(', ')}]`);

  /* Média e não amostragem: amostrar perderia o padrão de contraste fino que
     as características de Haar procuram, e o detector pararia de achar rosto
     pequeno. Se alguém "otimizar" isto para amostragem, este teste quebra. */
  const degrade = new Uint8ClampedArray([0, 100, 0, 100]);
  const reduzido = reduzir(degrade, 4, 1, 2, 1);
  verificar('a redução promedia em vez de amostrar',
    reduzido[0] === 50 && reduzido[1] === 50,
    `deu [${[...reduzido].join(', ')}]`);

  verificar('reduzir para o mesmo tamanho preserva os valores',
    [...reduzir(cinza, 4, 4, 4, 4)].join() === [...cinza].join());
}

// ---------------------------------------------------------------------------
grupo('Detecção comparada com o OpenCV, em imagem real');

const modelo = JSON.parse(readFileSync(join(AQUI, '..', 'modelo', 'cascata-rosto.json'), 'utf8'));

verificar('o modelo tem janela base 20x20',
  modelo.largura === 20 && modelo.altura === 20);
verificar('o modelo tem 20 estágios', modelo.estagios.length === 20);
verificar('o modelo tem características', modelo.caracteristicas.length > 1000);

const indice = JSON.parse(readFileSync(join(QUADROS, 'indice.json'), 'utf8'));

for (const caso of indice) {
  const cinza = new Uint8ClampedArray(readFileSync(join(QUADROS, caso.arquivo)));
  verificar(`${caso.nome}: o arquivo tem o tamanho declarado`,
    cinza.length === caso.largura * caso.altura,
    `${cinza.length} bytes para ${caso.largura}x${caso.altura}`);

  // Padrões do módulo, de propósito: o teste precisa exercitar o que o
  // aplicativo usa, e não uma configuração escolhida para passar.
  //
  // Mediana de três execuções, e não uma. Uma medição isolada de tempo numa
  // máquina que está fazendo outra coisa é ruído, e esse ruído já reprovou o
  // teste uma vez por 27 ms sem nada ter piorado. Teste que falha por acaso
  // treina quem o lê a ignorá-lo.
  const tempos = [];
  let achados = [];
  for (let i = 0; i < 3; i++) {
    const inicio = Date.now();
    achados = detectar(modelo, cinza, caso.largura, caso.altura);
    tempos.push(Date.now() - inicio);
  }
  tempos.sort((a, b) => a - b);
  const duracao = tempos[1];

  process.stdout.write(
    `  ${caso.nome}: ${achados.length} rosto(s) em ${duracao} ms, `
    + `OpenCV achou ${caso.opencv.length}\n`,
  );
  for (const a of achados) {
    process.stdout.write(
      `    nosso:  x=${a.x.toFixed(0)} y=${a.y.toFixed(0)} `
      + `l=${a.largura.toFixed(0)} a=${a.altura.toFixed(0)} (${a.n} vizinhos)\n`,
    );
  }
  for (const o of caso.opencv) {
    process.stdout.write(
      `    OpenCV: x=${o.x} y=${o.y} l=${o.largura} a=${o.altura}\n`,
    );
  }

  verificar(`${caso.nome}: acha a mesma quantidade de rostos que o OpenCV`,
    achados.length === caso.opencv.length,
    `nosso ${achados.length}, OpenCV ${caso.opencv.length}`);

  /* Tolerância de 25% do lado do rosto.
     Não é frouxidão: as duas implementações percorrem a pirâmide em passos
     diferentes e agrupam vizinhos por critérios diferentes, então a caixa cai
     alguns pixels ao lado por construção. O que precisa bater é o rosto, e
     25% do lado é menos que a folga que as regiões de interesse já têm dentro
     da caixa. */
  for (const esperado of caso.opencv) {
    const tolerancia = esperado.largura * 0.25;
    const perto = achados.find((a) =>
      Math.abs(a.x + a.largura / 2 - (esperado.x + esperado.largura / 2)) < tolerancia
      && Math.abs(a.y + a.altura / 2 - (esperado.y + esperado.altura / 2)) < tolerancia
      && Math.abs(a.largura - esperado.largura) < esperado.largura * 0.35);
    verificar(`${caso.nome}: a caixa bate com a do OpenCV`, Boolean(perto),
      perto
        ? ''
        : `nenhuma das ${achados.length} caixas caiu perto de `
          + `x=${esperado.x} y=${esperado.y} l=${esperado.largura}`);
  }

  /* O que motivou todo este módulo: a localização por cor punha a caixa na
     parede bege, que é a maior mancha na faixa de crominância da pele. A caixa
     certa ocupa uma fração pequena do quadro. */
  if (achados.length > 0) {
    const maior = achados[0];
    const fracao = (maior.largura * maior.altura) / (caso.largura * caso.altura);
    verificar(`${caso.nome}: a caixa é de um rosto e não da cena inteira`,
      fracao < 0.35, `ocupa ${(fracao * 100).toFixed(0)}% do quadro`);
  }

  /* Orçamento de tempo.
     O detector **não** roda a cada quadro: roda algumas vezes por segundo, e a
     caixa suavizada vale entre uma execução e outra. Medido nesta máquina, a
     configuração padrão leva cerca de 190 ms neste quadro. O limite de 400 ms
     existe para pegar regressão de ordem de grandeza, não para cobrar
     otimização: apertar mais só produziria um teste que falha em máquina
     modesta sem nada ter piorado. */
  verificar(`${caso.nome}: cabe no orçamento de tempo`,
    duracao < 400, `levou ${duracao} ms`);

  /* Margem da detecção, que é diferente de acertar.
     Uma configuração que acha o rosto com exatamente o mínimo de detecções
     sobrepostas está no limiar, e some na primeira mudança de iluminação.
     Medir a margem é o que separa "funciona" de "funcionou naquela foto". */
  if (achados.length > 0) {
    verificar(`${caso.nome}: a detecção tem margem, e não passa no limiar`,
      achados[0].n >= 5, `só ${achados[0].n} detecções sobrepostas`);
  }
}

// ---------------------------------------------------------------------------
grupo('Casos em que não pode achar rosto');

{
  const liso = new Uint8ClampedArray(200 * 150).fill(128);
  verificar('parede lisa não produz rosto',
    detectar(modelo, liso, 200, 150).length === 0);

  const preto = new Uint8ClampedArray(200 * 150).fill(0);
  verificar('imagem preta não produz rosto',
    detectar(modelo, preto, 200, 150).length === 0);

  const estourado = new Uint8ClampedArray(200 * 150).fill(255);
  verificar('imagem saturada não produz rosto',
    detectar(modelo, estourado, 200, 150).length === 0);

  const ruido = new Uint8ClampedArray(200 * 150);
  let semente = 12345;
  for (let i = 0; i < ruido.length; i++) {
    semente = (semente * 1103515245 + 12345) & 0x7fffffff;
    ruido[i] = semente % 256;
  }
  verificar('ruído aleatório não produz rosto',
    detectar(modelo, ruido, 200, 150).length === 0,
    `achou ${detectar(modelo, ruido, 200, 150).length}`);

  verificar('quadro menor que a janela base não quebra',
    detectar(modelo, new Uint8ClampedArray(10 * 10), 10, 10).length === 0);
}

// ---------------------------------------------------------------------------
grupo('Estabilidade da caixa ao longo do tempo');

{
  /* O rastreador roda sobre a imagem real, que é a única em que a detecção de
     fato acontece. Os quadros sintéticos do resto da suíte não têm estrutura
     de rosto, e a cascata, corretamente, não acha nada neles. */
  const caso = indice[0];
  const cinza = new Uint8ClampedArray(readFileSync(join(QUADROS, caso.arquivo)));

  // O rastreador recebe RGBA; monta a partir do cinza.
  const rgba = new Uint8ClampedArray(caso.largura * caso.altura * 4);
  for (let i = 0, j = 0; i < cinza.length; i++, j += 4) {
    rgba[j] = cinza[i];
    rgba[j + 1] = cinza[i];
    rgba[j + 2] = cinza[i];
    rgba[j + 3] = 255;
  }

  const rastreador = new RastreadorDeRosto(modelo);
  const primeira = rastreador.atualizar(rgba, caso.largura, caso.altura);
  verificar('acha o rosto no primeiro quadro', primeira !== null);

  if (primeira) {
    verificar('a caixa está em fração do quadro, e não em pixels',
      primeira.x > 0 && primeira.x < 1 && primeira.largura > 0 && primeira.largura < 1);

    /* Mesmo quadro de novo: a caixa não pode andar, porque a entrada é
       idêntica. Se andar, há estado sujo entre execuções. */
    const segunda = rastreador.atualizar(rgba, caso.largura, caso.altura);
    verificar('quadro idêntico não move a caixa',
      Math.abs(segunda.x - primeira.x) < 1e-9,
      `foi de ${primeira.x.toFixed(5)} para ${segunda.x.toFixed(5)}`);
  }

  /* Quadro sem rosto: a caixa anterior vale por algumas execuções, porque
     piscar ou virar de leve não deveria zerar o sinal acumulado. */
  const liso = new Uint8ClampedArray(caso.largura * caso.altura * 4).fill(128);
  const mantida = rastreador.atualizar(liso, caso.largura, caso.altura);
  verificar('perda momentânea mantém a última caixa',
    mantida !== null && Math.abs(mantida.x - primeira.x) < 1e-9);
  verificar('perda momentânea não é tratada como perda definitiva',
    !rastreador.perdeuORosto);

  /* Perda prolongada: aí a caixa é descartada. Continuar medindo onde o rosto
     não está produz um número sem significado, e número sem significado é pior
     que ausência de número. */
  for (let i = 0; i < 10; i++) rastreador.atualizar(liso, caso.largura, caso.altura);
  verificar('perda prolongada descarta a caixa',
    rastreador.atualizar(liso, caso.largura, caso.altura) === null);
  verificar('o rastreador relata que perdeu o rosto', rastreador.perdeuORosto);

  rastreador.reiniciar();
  verificar('reiniciar zera o estado',
    rastreador.caixa === null && !rastreador.perdeuORosto);

  /* As regiões saem da caixa e ficam dentro do quadro. */
  rastreador.atualizar(rgba, caso.largura, caso.altura);
  const regioes = rastreador.regioes();
  verificar('o rastreador entrega três regiões', regioes?.length === 3);
  verificar('as regiões ficam dentro do quadro',
    regioes.every((r) => r.x >= 0 && r.y >= 0
      && r.x + r.largura <= 1 + 1e-9 && r.y + r.altura <= 1 + 1e-9));

  /* Sem modelo o rastreador não quebra: devolve null. É o caminho que o
     aplicativo percorre enquanto o modelo ainda está sendo baixado. */
  const semModelo = new RastreadorDeRosto(null);
  verificar('sem modelo devolve null em vez de quebrar',
    semModelo.atualizar(rgba, caso.largura, caso.altura) === null);
}

// ---------------------------------------------------------------------------
process.stdout.write(`\n${'-'.repeat(62)}\n`);
if (falharam) {
  process.stdout.write(`FALHAS (${falharam}):\n`);
  falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
}
process.stdout.write(`${passaram} passaram, ${falharam} falharam\n`);
process.exit(falharam ? 1 : 0);
