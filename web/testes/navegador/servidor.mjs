/**
 * Servidor estático só para o teste de navegador.
 *
 * `127.0.0.1` é contexto seguro para o navegador, então `getUserMedia` funciona
 * sem certificado. Servir de `file://` não funcionaria: módulo ES por `file://`
 * esbarra na política de mesma origem.
 */

import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, sep as SEPARADOR } from 'node:path';

const TIPOS = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

export function servir(raiz) {
  const servidor = createServer((pedido, resposta) => {
    const caminho = decodeURIComponent(pedido.url.split('?')[0]);
    // Normaliza antes de juntar: sem isso, `/../` sairia da raiz.
    // Sem expressao regular com contrabarra: este arquivo ja foi escrito por
    // heredoc uma vez e a contrabarra sumiu no caminho.
    let relativo = normalize(caminho);
    while (relativo.startsWith('/') || relativo.startsWith(SEPARADOR)) relativo = relativo.slice(1);
    const alvo = join(raiz, relativo || 'index.html');
    if (!alvo.startsWith(raiz)) {
      resposta.writeHead(403).end('fora da raiz');
      return;
    }
    const arquivo = existsSync(alvo) && statSync(alvo).isDirectory()
      ? join(alvo, 'index.html')
      : alvo;
    if (!existsSync(arquivo)) {
      resposta.writeHead(404).end('não encontrado');
      return;
    }
    resposta.writeHead(200, {
      'content-type': TIPOS[extname(arquivo)] || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    createReadStream(arquivo).pipe(resposta);
  });

  return new Promise((resolve) => {
    servidor.listen(0, '127.0.0.1', () => {
      const { port } = servidor.address();
      resolve({
        url: `http://127.0.0.1:${port}`,
        fechar: () => new Promise((r) => servidor.close(r)),
      });
    });
  });
}
