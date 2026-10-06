/**
 * Registro de eventos da captura, para quando ela falhar na máquina de outro.
 *
 * Existe porque duas correções seguidas erraram o alvo. O relato possível era
 * "a câmera desliga e liga", e a partir dele qualquer explicação cabe: o
 * dispositivo reiniciando, o agendamento morrendo, a página reabrindo a câmera
 * sozinha, o sistema tomando o aparelho. São causas diferentes, com soluções
 * diferentes, e nenhuma delas se distingue das outras olhando a tela.
 *
 * Então o programa passou a anotar o que fez, com o instante de cada coisa. Não
 * é log de depuração espalhado: é a linha do tempo das decisões que afetam a
 * captura, e ela é a primeira coisa a pedir quando alguém disser que não
 * funciona.
 *
 * Fica em memória, num anel, e nunca sai do aparelho sozinho: quem copia é o
 * usuário, apertando o botão. Não entra nome, não entra imagem, não entra
 * identificador de dispositivo, pelo mesmo motivo que o resto do sistema não
 * manda nada para servidor nenhum. O rótulo da câmera entra porque é o que
 * distingue a câmera virtual da real, e é informação do equipamento e não da
 * pessoa.
 */

/** Quantos eventos ficam guardados. Passou disso, o mais antigo sai. */
export const CAPACIDADE = 400;

const eventos = [];
const inicio = Date.now();

/**
 * Anota um evento.
 *
 * @param {string} evento  nome curto e estável, em minúsculas
 * @param {object} [dados] só números, textos curtos e booleanos
 */
export function registrar(evento, dados = {}) {
  eventos.push({
    ms: Math.round(performance.now()),
    evento,
    dados,
  });
  if (eventos.length > CAPACIDADE) eventos.shift();
}

/** Devolve os eventos crus, para teste e para a página de diagnóstico. */
export function listar() {
  return eventos.slice();
}

export function limpar() {
  eventos.length = 0;
}

/**
 * Monta o texto que vai para a área de transferência.
 *
 * Texto e não JSON de propósito: quem vai colar isso numa conversa precisa
 * conseguir ler, e eu preciso conseguir ler junto com ele sem ferramenta.
 */
export function comoTexto(ambiente = {}) {
  const cabecalho = [
    `Cardiocam, diagnóstico de captura`,
    `início da página: ${new Date(inicio).toISOString()}`,
    `gerado em: ${new Date().toISOString()}`,
    ...Object.entries(ambiente).map(([chave, valor]) => `${chave}: ${valor}`),
    `eventos: ${eventos.length}${eventos.length >= CAPACIDADE ? ' (os mais antigos foram descartados)' : ''}`,
    '',
  ];

  const linhas = eventos.map(({ ms, evento, dados }) => {
    const partes = Object.entries(dados)
      .map(([chave, valor]) => `${chave}=${formatar(valor)}`)
      .join(' ');
    const segundos = (ms / 1000).toFixed(2).padStart(9, ' ');
    return `${segundos}s  ${evento}${partes ? `  ${partes}` : ''}`;
  });

  return [...cabecalho, ...linhas].join('\n');
}

function formatar(valor) {
  if (typeof valor === 'number') {
    return Number.isInteger(valor) ? String(valor) : valor.toFixed(3);
  }
  if (typeof valor === 'string') return valor.length > 90 ? `${valor.slice(0, 90)}…` : valor;
  return String(valor);
}
