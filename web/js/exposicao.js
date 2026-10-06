/**
 * Equilibra exposição e taxa de quadros, que disputam o mesmo recurso.
 *
 * A troca é física e não tem como ser evitada: a câmera não entrega um quadro
 * antes de terminar de expô-lo, então integrar por 125 ms limita a entrega a
 * oito quadros por segundo, e nenhuma escolha de resolução muda isso. Mais luz
 * por quadro custa menos quadros por segundo. Os dois lados importam para medir
 * pulso, por motivos diferentes: pouca luz deixa o pulso abaixo do passo de
 * quantização do sensor, e poucos quadros deixam a série curta e irregular
 * demais para a análise espectral.
 *
 * O código deste projeto tinha os dois lados, escritos em lugares diferentes e
 * sem saber um do outro. Um limitava a taxa a 20 para comprar exposição, citando
 * a medição de Odinaev et al. (CVPRW 2023), que achou o ótimo em 1/16 de
 * segundo. O outro reprovava a captura abaixo de 14 quadros por segundo e
 * **reabria a câmera numa resolução menor**. Numa webcam que abre com a
 * exposição no máximo, os dois juntos produziam um ciclo: taxa baixa, reabre;
 * taxa baixa de novo, porque a causa nunca foi a resolução; reabre de novo. Do
 * lado de quem olha, a câmera desliga e liga sozinha.
 *
 * As medidas que motivaram este módulo, numa EMEET SmartCam S600, por
 * `testes/navegador/medir_exposicao.mjs`:
 *
 * | exposição | taxa entregue |
 * | ---: | ---: |
 * | 5000, o máximo e o padrão dela | 8,0 |
 * | 2500 | 8,0 |
 * | 1250 | 8,0 |
 * | 625 | 15,9 |
 * | 312 | 30,0 |
 *
 * E `medir_taxas.mjs` deu a mesma taxa, 8,0, em 1920x1080 e em 320x240. Isso
 * elimina banda e processamento: as duas se comportam de outro jeito.
 */

/**
 * Luminância alvo da pele, de 0 a 255.
 *
 * Abaixo de 60 o pulso, que vale de 0,1% a 1% da intensidade, fica menor que um
 * nível inteiro, e o sensor entrega inteiros. 110 dá folga sem chegar perto de
 * estourar a pele, que começa a saturar por volta de 200 e aí perde a modulação
 * inteira.
 */
export const LUMINANCIA_ALVO = 110;

/** Abaixo disto, a imagem é escura demais para o pulso ter chance. */
export const LUMINANCIA_MINIMA = 60;

/**
 * Taxa de quadros abaixo da qual a exposição deixa de valer a pena.
 *
 * Não vem de Nyquist, que para 3,3 Hz pediria 6,6. Vem de que a análise usa
 * subjanelas e mede a dispersão entre elas, e abaixo disto cada subjanela fica
 * com poucas dezenas de amostras. A revisão sistemática da área dá 19,9 como
 * mínimo recomendado; 15 é o ponto em que ainda se mede com ressalva, e é o
 * ponto em que vale mais ganhar quadro do que ganhar luz.
 */
export const TAXA_MINIMA = 15;

/**
 * Unidades de `exposureTime` em um segundo.
 *
 * A especificação de Image Capture do W3C define `exposureTime` em passos de
 * 100 microssegundos, então um segundo são dez mil unidades. Esse número é o
 * que torna o ajuste determinístico em vez de tateado: a taxa máxima possível é
 * o inverso da exposição, logo a exposição máxima compatível com uma taxa é
 * `UNIDADES_POR_SEGUNDO / taxa`.
 *
 * Conferido na EMEET SmartCam S600: 625 unidades são 62,5 ms, que preveem 16
 * quadros por segundo, e a medição deu 15,9. Com 312,5 a previsão é 32 e a
 * medição deu 30,0, que é o teto próprio dela.
 *
 * Esta constante substituiu um modelo pior, que estimava a relação a partir da
 * taxa medida. Ele falhava justamente no caso que importa: com a exposição em
 * 5000 a câmera entrega 8 quadros por segundo em vez dos 2 que a conta prevê,
 * porque ela limita a própria taxa em outro ponto, e calibrar ali dava um alvo
 * de 2310, que não resolve nada.
 */
export const UNIDADES_POR_SEGUNDO = 10000;

/** Quantos quadros contar para estimar a taxa entregue. */
const QUADROS_PARA_MEDIR = 14;
/** Teto de tempo da medição, para não travar a abertura numa câmera morta. */
const PRAZO_DA_MEDIDA_MS = 1900;
/** Intervalo da amostragem de reserva, em milissegundos. */
const PASSO_DA_RESERVA_MS = 8;
/** Quantas vezes o tempo pode cair pela metade atrás do teto. */
const RODADAS_DE_METADE = 3;

/**
 * Conta quadros de verdade durante um instante e devolve a taxa entregue.
 *
 * Caminho principal: `requestVideoFrameCallback`, que dispara uma vez por
 * quadro novo e entrega o `mediaTime` de cada um. Contar com
 * `requestAnimationFrame` mediria a taxa do monitor, que é o engano que já
 * custou caro neste projeto.
 *
 * Caminho de reserva: amostrar `currentTime` num temporizador e contar valores
 * distintos. Existe porque o principal **devolveu nada** em parte das execuções
 * de teste, e a causa é entendível: o elemento de vídeo ainda está escondido
 * nesse ponto da abertura, e o navegador não é obrigado a compor quadro de
 * elemento que ninguém vê. Medição que às vezes não mede é pior que medição
 * grosseira, porque o valor ausente vira decisão errada em silêncio.
 */
export function medirTaxaEntregue(video, {
  quadros = QUADROS_PARA_MEDIR,
  prazoMs = PRAZO_DA_MEDIDA_MS,
} = {}) {
  return new Promise((resolve) => {
    const marcas = [];
    let encerrado = false;
    let temporizador = null;

    const taxa = () => {
      if (marcas.length < 3) return Number.NaN;
      const duracao = marcas[marcas.length - 1] - marcas[0];
      return duracao > 0 ? (marcas.length - 1) / duracao : Number.NaN;
    };

    const anotar = (tempo) => {
      if (Number.isFinite(tempo) && tempo !== marcas[marcas.length - 1]) marcas.push(tempo);
    };

    const terminar = () => {
      if (encerrado) return;
      encerrado = true;
      clearTimeout(relogio);
      if (temporizador !== null) clearInterval(temporizador);
      resolve(taxa());
    };

    const relogio = setTimeout(() => {
      // Sem quadro pelo caminho principal: tenta o de reserva antes de desistir.
      if (marcas.length >= 3 || encerrado) { terminar(); return; }
      temporizador = setInterval(() => {
        anotar(video?.currentTime);
        if (marcas.length >= quadros) terminar();
      }, PASSO_DA_RESERVA_MS);
      setTimeout(terminar, prazoMs);
    }, prazoMs);

    if (typeof video?.requestVideoFrameCallback === 'function') {
      const passo = (_horario, dados) => {
        if (encerrado) return;
        anotar(Number.isFinite(dados?.mediaTime) ? dados.mediaTime : video.currentTime);
        if (marcas.length >= quadros) { terminar(); return; }
        video.requestVideoFrameCallback(passo);
      };
      video.requestVideoFrameCallback(passo);
    }
  });
}

/** Encaixa um valor na faixa e no passo que a câmera aceita. */
export function encaixarNaFaixa(valor, faixa) {
  const minimo = Number.isFinite(faixa?.min) ? faixa.min : 0;
  const maximo = Number.isFinite(faixa?.max) ? faixa.max : 0;
  if (!(maximo > minimo) || !Number.isFinite(valor)) return null;
  const passo = Number.isFinite(faixa.step) && faixa.step > 0 ? faixa.step : null;
  let alvo = Math.min(maximo, Math.max(minimo, valor));
  if (passo) alvo = Math.round(alvo / passo) * passo;
  return Math.min(maximo, Math.max(minimo, alvo));
}

/**
 * Exposição mais longa compatível com uma taxa de quadros.
 *
 * Direto da física, sem calibração: expor por mais tempo que o intervalo entre
 * quadros é impossível, então a exposição máxima é o inverso da taxa.
 */
export function exposicaoParaTaxa(taxaDesejada) {
  if (!(taxaDesejada > 0)) return null;
  return UNIDADES_POR_SEGUNDO / taxaDesejada;
}

/**
 * Deixa a câmera num ponto em que dá para medir, ou diz por que não dá.
 *
 * Devolve um relato com os números, porque é ele que vira a mensagem na tela e
 * a linha do registro. Função que ajusta a câmera em silêncio é função que
 * ninguém consegue depurar depois.
 *
 * O desenho tem uma propriedade que vale declarar: **a decisão principal não
 * depende de medir a taxa**. Ela sai de comparar o tempo de exposição com o
 * teto calculado, dois números que a câmera entrega na hora. A medição entra só
 * no relato, e no caso em que a câmera não expõe `exposureTime`. Isso importa
 * porque medir taxa é a parte frágil: depende de o navegador estar compondo
 * quadro, e ele nem sempre está.
 *
 * @param {object} contexto
 * @param {MediaStreamTrack} contexto.trilha
 * @param {HTMLVideoElement} contexto.video
 * @param {() => number} contexto.luminancia  luminância do quadro atual
 * @param {(ms: number) => Promise<void>} contexto.espera
 * @param {(evento: string, dados?: object) => void} [contexto.registrar]
 */
export async function equilibrar({
  trilha,
  video,
  luminancia,
  espera,
  registrar = () => {},
  taxaMinima = TAXA_MINIMA,
  luminanciaAlvo = LUMINANCIA_ALVO,
  // Entra por parâmetro para o teste poder substituí-la. Medir taxa de verdade
  // leva segundos, e uma suíte que leva segundos por caso deixa de ser rodada.
  medirTaxa = medirTaxaEntregue,
}) {
  const relato = {
    ajustou: false,
    taxa: Number.NaN,
    exposicaoAntes: null,
    exposicaoDepois: null,
    teto: null,
    luz: Number.NaN,
    passos: 0,
    motivo: '',
  };

  if (!trilha?.getCapabilities || !trilha.applyConstraints) {
    relato.motivo = 'a câmera não deixa ajustar nada pelo navegador';
    relato.taxa = await medirTaxa(video);
    relato.luz = luminancia();
    return relato;
  }

  let capacidades;
  try {
    capacidades = trilha.getCapabilities();
  } catch {
    relato.motivo = 'a câmera não respondeu sobre o que sabe fazer';
    return relato;
  }

  const faixa = capacidades.exposureTime;
  const temManual = Boolean(capacidades.exposureMode?.includes('manual'));
  relato.exposicaoAntes = trilha.getSettings?.().exposureTime ?? null;
  relato.teto = encaixarNaFaixa(exposicaoParaTaxa(taxaMinima), faixa);

  if (!faixa || !temManual) {
    relato.motivo = 'a câmera não expõe o tempo de exposição ao navegador';
    relato.taxa = await medirTaxa(video);
    relato.luz = luminancia();
    registrar('exposicao.indisponivel', {
      temManual,
      temExposureTime: Boolean(faixa),
      taxa: relato.taxa,
      luz: relato.luz,
    });
    return relato;
  }

  // O travamento vem antes de qualquer mudança de tempo: em modo contínuo a
  // câmera desfaz o pedido no quadro seguinte.
  try {
    await trilha.applyConstraints({ advanced: [{ exposureMode: 'manual' }] });
  } catch {
    relato.motivo = 'a câmera recusou o modo manual de exposição';
    relato.taxa = await medirTaxa(video);
    return relato;
  }

  let atual = trilha.getSettings?.().exposureTime ?? relato.exposicaoAntes;
  relato.exposicaoAntes = atual;
  relato.luz = luminancia();

  const aplicar = async (valor) => {
    const alvo = encaixarNaFaixa(valor, faixa);
    if (alvo === null) return false;
    if (Math.abs(alvo - atual) / Math.max(atual, 1) < 0.05) return false;
    try {
      await trilha.applyConstraints({ advanced: [{ exposureTime: alvo }] });
    } catch {
      return false;
    }
    await espera(300);
    atual = trilha.getSettings?.().exposureTime ?? alvo;
    relato.passos += 1;
    relato.ajustou = true;
    return true;
  };

  /*
    Garante que a exposição ficou abaixo do teto, custe quantos pedidos custar.

    Isto existe porque a câmera **arredonda o pedido para cima**.
    `getCapabilities` desta webcam declara passo de 1,22 unidades, sugerindo
    ajuste fino, e a escada que ela assume de fato é 5000, 2500, 1250, 625.
    Pedir 666 devolveu 625 numa execução e 1250 em outra.

    Cortar pela metade garante descer um degrau dessa escada por rodada, e três
    rodadas cobrem uma escada de oito para um.

    E a conferência não mede taxa nenhuma: compara dois números que a câmera
    entrega na hora. Isso é de propósito, porque medir taxa é a parte frágil, e
    foi medido que ela falha: em parte das execuções com navegador,
    `requestVideoFrameCallback` não disparou nenhuma vez durante a abertura,
    porque o elemento de vídeo ainda está escondido nesse ponto.
  */
  const garantirAbaixoDoTeto = async () => {
    if (relato.teto === null) return;
    for (let rodada = 0; rodada < RODADAS_DE_METADE && atual > relato.teto; rodada++) {
      const anterior = atual;
      if (!await aplicar(atual / 2)) break;
      if (atual >= anterior) break;
    }
    if (atual > relato.teto) relato.motivo += ', e a câmera não desceu até o necessário';
  };

  /*
    Um teto só, e ele vem da taxa mínima.

    O erro da primeira versão foi tratar luz e taxa como duas decisões que se
    alternam. Elas não se alternam: a taxa define um **teto** de exposição, e a
    procura por luz acontece debaixo dele. Com o teto explícito, os dois casos
    viram o mesmo caso, e não há como um desfazer o outro.
  */
  if (relato.teto !== null && atual > relato.teto) {
    relato.motivo = 'exposição longa demais para a taxa de quadros mínima';
    await aplicar(relato.teto);
  } else if (Number.isFinite(relato.luz) && relato.luz < luminanciaAlvo && atual > 0) {
    const fator = Math.min(2.5, Math.max(1.2, luminanciaAlvo / Math.max(relato.luz, 1)));
    const desejada = Math.min(atual * fator, relato.teto ?? atual * fator);
    relato.motivo = 'imagem escura, com folga de exposição abaixo do teto';
    await aplicar(desejada);
  } else {
    relato.motivo = 'nada a ajustar';
  }

  /*
    Depois dos dois ramos, e não dentro de um só.

    Este era o furo: a conferência estava só no ramo que desce. O ramo que sobe
    atrás de luz pedia exatamente o teto, a câmera arredondava para o degrau de
    cima, e a captura ia de 15,9 para 8,0 quadros por segundo caçando uma luz
    que ela nem ganhava. Foi pego pelo teste com a câmera real, duas horas
    depois de o módulo ter sido escrito para impedir precisamente isso.
  */
  await garantirAbaixoDoTeto();

  relato.exposicaoDepois = atual;
  relato.luz = luminancia();
  relato.taxa = await medirTaxa(video);
  registrar('exposicao.ajustada', {
    de: relato.exposicaoAntes ?? 0,
    para: relato.exposicaoDepois ?? 0,
    teto: relato.teto ?? 0,
    passos: relato.passos,
    taxa: relato.taxa,
    luz: relato.luz,
    motivo: relato.motivo,
  });
  return relato;
}
