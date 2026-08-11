/**
 * Persistência local das medições.
 *
 * Tudo fica no armazenamento do próprio navegador. Nenhuma medição sai do
 * aparelho, e não existe servidor para onde mandar. Isso não é só conveniência:
 * frequência cardíaca é dado pessoal sensível pela LGPD, e a forma mais simples
 * de tratar dado sensível com responsabilidade é não centralizá-lo.
 */

const CHAVE = 'cardiocam.medicoes.v1';
const LIMITE = 500;

function ler() {
  try {
    const bruto = localStorage.getItem(CHAVE);
    if (!bruto) return [];
    const dados = JSON.parse(bruto);
    return Array.isArray(dados) ? dados : [];
  } catch (erro) {
    // Armazenamento corrompido ou bloqueado (navegação anônima com restrição)
    // não pode derrubar a aplicação: a medição continua funcionando sem
    // histórico.
    console.warn('Não foi possível ler o histórico:', erro);
    return [];
  }
}

function gravar(lista) {
  try {
    localStorage.setItem(CHAVE, JSON.stringify(lista.slice(0, LIMITE)));
    return true;
  } catch (erro) {
    console.warn('Não foi possível gravar o histórico:', erro);
    return false;
  }
}

export function listarMedicoes() {
  return ler().sort((a, b) => b.instante - a.instante);
}

export function salvarMedicao(medicao) {
  const lista = ler();
  const registro = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    instante: Date.now(),
    ...medicao,
  };
  lista.unshift(registro);
  gravar(lista);
  return registro;
}

export function removerMedicao(id) {
  gravar(ler().filter((m) => m.id !== id));
}

export function limparTudo() {
  gravar([]);
}

/** Nomes já usados, para sugerir no campo em vez de digitar de novo. */
export function listarPessoas() {
  const nomes = new Map();
  for (const m of ler()) {
    const chave = (m.pessoa || '').trim();
    if (!chave) continue;
    const atual = nomes.get(chave);
    if (!atual || m.instante > atual.ultima) {
      nomes.set(chave, { nome: chave, ultima: m.instante, total: (atual?.total || 0) + 1 });
    } else {
      atual.total += 1;
    }
  }
  return [...nomes.values()].sort((a, b) => b.ultima - a.ultima);
}

export function medicoesDe(pessoa) {
  return listarMedicoes().filter((m) => (m.pessoa || '') === pessoa);
}

/** Exporta o histórico em CSV, com ponto e vírgula para abrir no Excel do Brasil. */
export function exportarCsv() {
  const linhas = [
    'pessoa;data;hora;bpm;confianca;relacao_sinal_ruido_db;algoritmo;duracao_s;origem;observacao',
  ];
  for (const m of listarMedicoes()) {
    const d = new Date(m.instante);
    const data = d.toLocaleDateString('pt-BR');
    const hora = d.toLocaleTimeString('pt-BR');
    const limpar = (t) => String(t ?? '').replace(/[;\n\r]/g, ' ');
    linhas.push(
      [
        limpar(m.pessoa),
        data,
        hora,
        Number(m.bpm).toFixed(1).replace('.', ','),
        limpar(m.confianca),
        Number(m.snrDb).toFixed(1).replace('.', ','),
        limpar(m.algoritmo),
        Number(m.duracaoS || 0).toFixed(0),
        limpar(m.origem),
        limpar(m.observacao),
      ].join(';'),
    );
  }
  return linhas.join('\r\n');
}

export function baixarCsv() {
  const conteudo = exportarCsv();
  // O BOM faz o Excel reconhecer a acentuação sem precisar configurar nada.
  const blob = new Blob(['﻿' + conteudo], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `cardiocam-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
