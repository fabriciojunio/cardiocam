/**
 * Cliente mínimo do protocolo de depuração do Chromium.
 *
 * Sem dependência de pacote: o Node já traz `WebSocket` global desde a 22, e o
 * que falta são umas quarenta linhas. A alternativa seria instalar um
 * automatizador de navegador inteiro, com o seu próprio ciclo de atualização,
 * para fazer três chamadas.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ESPERA_DA_PORTA_MS = 20000;

/** Acha um Chromium utilizável, nesta ordem de preferência. */
export function acharNavegador() {
  if (process.env.CHROME && existsSync(process.env.CHROME)) return process.env.CHROME;

  const candidatos = [];
  const playwright = join(
    process.env.LOCALAPPDATA || join(process.env.HOME || '', 'AppData', 'Local'),
    'ms-playwright',
  );
  if (existsSync(playwright)) {
    // O mais novo primeiro: os diretórios são `chromium-<build>`.
    const versoes = readdirSeguro(playwright)
      .filter((nome) => nome.startsWith('chromium-'))
      .sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]));
    for (const versao of versoes) {
      candidatos.push(join(playwright, versao, 'chrome-win64', 'chrome.exe'));
      candidatos.push(join(playwright, versao, 'chrome-linux', 'chrome'));
    }
  }
  candidatos.push(
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  );
  return candidatos.find((caminho) => existsSync(caminho)) || null;
}

function readdirSeguro(caminho) {
  try {
    return readdirSync(caminho);
  } catch {
    return [];
  }
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

export async function abrirNavegador({ executavel, argumentos = [] }) {
  const perfil = mkdtempSync(join(tmpdir(), 'cardiocam-perfil-'));
  const processo = spawn(executavel, [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${perfil}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    '--mute-audio',
    '--autoplay-policy=no-user-gesture-required',
    '--use-fake-ui-for-media-stream',
    ...argumentos,
    'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });

  const erros = [];
  processo.stderr.on('data', (d) => erros.push(String(d)));

  const arquivoDaPorta = join(perfil, 'DevToolsActivePort');
  const limite = Date.now() + ESPERA_DA_PORTA_MS;
  let porta = null;
  while (Date.now() < limite) {
    if (processo.exitCode !== null) {
      throw new Error(`o navegador saiu com ${processo.exitCode}: ${erros.join('').slice(-500)}`);
    }
    if (existsSync(arquivoDaPorta)) {
      const conteudo = readFileSync(arquivoDaPorta, 'utf8').split('\n');
      if (conteudo[0]?.trim()) { porta = Number(conteudo[0].trim()); break; }
    }
    await espera(100);
  }
  if (!porta) throw new Error(`o navegador não abriu a porta de depuração: ${erros.join('').slice(-500)}`);

  const versao = await (await fetch(`http://127.0.0.1:${porta}/json/version`)).json();
  const sessao = await conectar(versao.webSocketDebuggerUrl);

  return {
    porta,
    sessao,
    erros,
    async fechar() {
      try { sessao.fechar(); } catch { /* já caiu */ }
      processo.kill();
      await espera(300);
      try { rmSync(perfil, { recursive: true, force: true }); } catch { /* o Windows às vezes segura */ }
    },
  };
}

function conectar(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    let proximo = 1;
    const pendentes = new Map();

    const ouvintes = new Map();

    ws.addEventListener('message', (evento) => {
      const mensagem = JSON.parse(evento.data);
      if (mensagem.method && mensagem.sessionId) {
        // Erro de página e chamada ao console chegam como evento, sem `id`.
        // Sem repassá-los, uma falha de carregamento vira silêncio e o teste
        // reporta "a câmera não abriu" quando o módulo nem chegou a rodar.
        const ouvinte = ouvintes.get(mensagem.sessionId);
        if (ouvinte) ouvinte(mensagem);
        return;
      }
      const aguardando = pendentes.get(mensagem.id);
      if (!aguardando) return;
      pendentes.delete(mensagem.id);
      if (mensagem.error) aguardando.reject(new Error(JSON.stringify(mensagem.error)));
      else aguardando.resolve(mensagem.result);
    });
    ws.addEventListener('error', () => reject(new Error('falha ao conectar no navegador')));
    ws.addEventListener('close', () => {
      for (const { reject: r } of pendentes.values()) r(new Error('a conexão caiu'));
      pendentes.clear();
    });

    ws.addEventListener('open', () => resolve({
      enviar(metodo, parametros = {}, sessionId) {
        const id = proximo++;
        return new Promise((res, rej) => {
          pendentes.set(id, { resolve: res, reject: rej });
          ws.send(JSON.stringify({ id, method: metodo, params: parametros, sessionId }));
        });
      },
      escutar(sessionId, retorno) { ouvintes.set(sessionId, retorno); },
      fechar() { ws.close(); },
    }));
  });
}

/** Abre uma aba e devolve um avaliador já amarrado a ela. */
export async function abrirAba(sessao, url, { aoErro = null } = {}) {
  const { targetId } = await sessao.enviar('Target.createTarget', { url });
  const { sessionId } = await sessao.enviar('Target.attachToTarget', { targetId, flatten: true });
  await sessao.enviar('Runtime.enable', {}, sessionId);
  if (aoErro) sessao.escutar(sessionId, aoErro);

  const aba = {
    targetId,
    sessionId,
    async avaliar(expressao, { aguardarPromessa = true } = {}) {
      const resposta = await sessao.enviar('Runtime.evaluate', {
        expression: expressao,
        awaitPromise: aguardarPromessa,
        returnByValue: true,
      }, sessionId);
      if (resposta.exceptionDetails) {
        const detalhe = resposta.exceptionDetails;
        throw new Error(detalhe.exception?.description || detalhe.text || 'erro na página');
      }
      return resposta.result?.value;
    },
  };

  /*
    Esperar a navegacao terminar antes de devolver a aba.

    `Target.createTarget` responde assim que o alvo existe, e nesse instante o
    documento ainda e `about:blank`. Avaliar ali da um erro desnorteante:
    `navigator.mediaDevices` e indefinido, porque `about:blank` nao e contexto
    seguro, e a mensagem fala de camera quando o problema e de navegacao.
  */
  const limite = Date.now() + 15000;
  while (Date.now() < limite) {
    const pronto = await aba.avaliar(
      'document.readyState === "complete" && location.href !== "about:blank"',
    );
    if (pronto) break;
    await espera(80);
  }
  return aba;
}
