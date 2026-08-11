/**
 * Algoritmos de extração de pulso a partir das três séries de cor.
 *
 * Porte fiel dos mesmos métodos da versão em Python. A diferença entre eles é
 * uma só: como combinam os canais para separar sangue de iluminação.
 *
 * O movimento e a variação de luz mudam a intensidade dos três canais na mesma
 * proporção. O pulso muda a proporção entre eles, porque a hemoglobina absorve
 * muito mais no verde que no vermelho. Os métodos cromáticos exploram
 * exatamente essa assimetria; o método do canal verde não tem como.
 */

import { desvioPadrao, media, passaFaixa, removerMedia } from './dsp.js';

function normalizarPelaMedia(canal) {
  const m = media(canal);
  const seguro = Math.abs(m) < 1e-12 ? 1 : m;
  return canal.map((x) => x / seguro);
}

/**
 * GREEN (Verkruysse et al., 2008). Usa apenas o canal verde, onde a
 * hemoglobina mais absorve. Invertido para que os picos coincidam com a
 * sístole: mais sangue significa mais absorção e menos luz refletida.
 */
export function verde({ verde: g }) {
  return g.map((x) => -x);
}

/**
 * CHROM (de Haan e Jeanne, 2013). Monta duas projeções cromáticas e as combina
 * com um peso que cancela a distorção comum às duas.
 */
export function chrom({ vermelho, verde: g, azul }, fps, minHz, maxHz) {
  const r = normalizarPelaMedia(vermelho);
  const v = normalizarPelaMedia(g);
  const b = normalizarPelaMedia(azul);

  const x = r.map((_, i) => 3 * r[i] - 2 * v[i]);
  const y = r.map((_, i) => 1.5 * r[i] + v[i] - 1.5 * b[i]);

  // O peso precisa refletir a energia dentro da banda cardíaca, e não a
  // energia total, que seria dominada pela tendência de iluminação. Por isso
  // as projeções são filtradas antes de calcular alfa.
  const xf = passaFaixa(x, fps, minHz, maxHz);
  const yf = passaFaixa(y, fps, minHz, maxHz);

  const dy = desvioPadrao(yf);
  const alfa = dy > 1e-12 ? desvioPadrao(xf) / dy : 0;
  return xf.map((_, i) => xf[i] - alfa * yf[i]);
}

/**
 * POS (Wang et al., 2017). Projeta num plano ortogonal à direção do tom de
 * pele, de modo que variação pura de intensidade desaparece por construção.
 *
 * A normalização roda em sub-janelas curtas deslizando sobre o sinal, para que
 * a hipótese de tom de pele constante só precise valer por um instante, e as
 * sub-janelas são somadas com sobreposição para que as bordas de uma compensem
 * as da outra.
 */
export function pos({ vermelho, verde: g, azul }, fps) {
  const n = g.length;
  const comprimento = Math.max(2, Math.round(1.6 * fps));
  const saida = new Array(n).fill(0);

  const combinar = (inicio, fim) => {
    const tamanho = fim - inicio;
    let mr = 0;
    let mg = 0;
    let mb = 0;
    for (let i = inicio; i < fim; i++) {
      mr += vermelho[i];
      mg += g[i];
      mb += azul[i];
    }
    mr = Math.abs(mr / tamanho) < 1e-12 ? 1 : mr / tamanho;
    mg = Math.abs(mg / tamanho) < 1e-12 ? 1 : mg / tamanho;
    mb = Math.abs(mb / tamanho) < 1e-12 ? 1 : mb / tamanho;

    const s1 = new Array(tamanho);
    const s2 = new Array(tamanho);
    for (let k = 0; k < tamanho; k++) {
      const i = inicio + k;
      const rn = vermelho[i] / mr;
      const gn = g[i] / mg;
      const bn = azul[i] / mb;
      s1[k] = gn - bn;
      s2[k] = -2 * rn + gn + bn;
    }

    const d2 = desvioPadrao(s2);
    const alfa = d2 > 1e-12 ? desvioPadrao(s1) / d2 : 0;
    let h = s1.map((_, k) => s1[k] + alfa * s2[k]);
    h = removerMedia(h);
    const dh = desvioPadrao(h);
    if (dh > 1e-12) h = h.map((x) => x / dh);
    return h;
  };

  if (n <= comprimento) return combinar(0, n);

  for (let fim = comprimento; fim <= n; fim++) {
    const inicio = fim - comprimento;
    const bloco = combinar(inicio, fim);
    for (let k = 0; k < bloco.length; k++) saida[inicio + k] += bloco[k];
  }
  return saida;
}

export const ALGORITMOS = {
  pos: { nome: 'POS', rotulo: 'POS (plano ortogonal à pele)', executar: pos },
  chrom: { nome: 'CHROM', rotulo: 'CHROM (crominância)', executar: chrom },
  verde: { nome: 'GREEN', rotulo: 'GREEN (só o canal verde)', executar: verde },
};

/**
 * Aplica o algoritmo escolhido e devolve o sinal de pulso já filtrado na banda
 * cardíaca. O pós-processamento é o mesmo para todos, para que a comparação
 * entre eles seja honesta.
 */
export function extrairPulso(serie, fps, algoritmo = 'pos', minHz = 0.75, maxHz = 3.3) {
  const escolhido = ALGORITMOS[algoritmo] ?? ALGORITMOS.pos;
  const bruto = escolhido.executar(serie, fps, minHz, maxHz);
  return passaFaixa(bruto, fps, minHz, maxHz);
}
