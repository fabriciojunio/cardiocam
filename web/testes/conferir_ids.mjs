/**
 * Confere que todo identificador buscado no JavaScript existe no HTML.
 *
 * Este teste existe por causa de um modo de falha específico e desagradável:
 * `document.getElementById` devolve `null` para identificador inexistente, sem
 * erro nenhum. O erro aparece depois, na primeira vez que alguém faz
 * `el.coisa.addEventListener`, e aí ele é um `TypeError` no carregamento do
 * módulo, que derruba **a página inteira**: nenhum botão responde, e o console
 * mostra uma linha que não tem relação óbvia com o que está errado.
 *
 * Renomear um elemento no HTML e esquecer o JavaScript, ou o contrário, é a
 * forma mais fácil de causar isso. Dá trinta segundos para conferir por
 * máquina e horas para achar na mão.
 *
 * Roda com `npm test`, sem navegador.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, '..');

/** Cada pagina com o modulo que a controla. */
const PAGINAS = [
  { html: 'index.html', js: join('js', 'app.js') },
  { html: 'diagnostico.html', js: join('js', 'diagnostico.js') },
];

process.stdout.write('\nConferencia de identificadores entre HTML e JavaScript\n');

let houveFalha = false;

for (const pagina of PAGINAS) {
  const html = readFileSync(join(RAIZ, pagina.html), 'utf8');
  const js = readFileSync(join(RAIZ, pagina.js), 'utf8');

  /** Identificadores declarados no HTML. */
  const declarados = new Set(
    [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]),
  );

  /** Identificadores buscados no JavaScript, pelos dois caminhos usados. */
  const buscados = new Map();
  for (const m of js.matchAll(/\$\('([^']+)'\)/g)) {
    buscados.set(m[1], (buscados.get(m[1]) || 0) + 1);
  }
  for (const m of js.matchAll(/getElementById\('([^']+)'\)/g)) {
    buscados.set(m[1], (buscados.get(m[1]) || 0) + 1);
  }

  const faltando = [...buscados.keys()].filter((id) => !declarados.has(id));

  /**
   * Identificadores que existem no HTML e ninguem busca.
   *
   * Nao e erro: varios servem de alvo de seletor em CSS ou de rotulo de
   * acessibilidade, e alguns sao buscados por template, que esta expressao
   * regular nao enxerga. Listamos como informacao, sem reprovar.
   */
  const orfaos = [...declarados].filter((id) => !buscados.has(id));

  process.stdout.write(`\n  ${pagina.html} com ${pagina.js}\n`);
  process.stdout.write(`    ${declarados.size} declarados, ${buscados.size} buscados\n`);
  if (orfaos.length) {
    process.stdout.write(`    ${orfaos.length} sem uso: ${orfaos.join(', ')}\n`);
  }

  if (faltando.length) {
    houveFalha = true;
    process.stdout.write('    FALHA, buscados no JavaScript e ausentes no HTML:\n');
    for (const id of faltando) {
      process.stdout.write(`      - ${id}\n`);
    }
  } else {
    process.stdout.write('    nenhum identificador faltando\n');
  }
}

if (houveFalha) {
  process.stdout.write(
    '\nQualquer um destes derruba a pagina no carregamento, '
    + 'porque o modulo registra evento em null.\n',
  );
  process.exit(1);
}
