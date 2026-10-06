/**
 * Testes da cadência de quadros.
 *
 * Esta é a parte do sistema que já falhou duas vezes em produção, e as duas
 * vezes em silêncio: a imagem congelava, a barra parava, e nada na tela dizia
 * que tinha parado. Nenhuma das duas falhas era detectável sem navegador,
 * porque a lógica morava dentro de `app.js`, amarrada a elemento de vídeo, a
 * `requestVideoFrameCallback` e ao relógio do navegador.
 *
 * Agora as três coisas entram por parâmetro, e a bancada abaixo simula o que
 * de fato acontece na máquina do usuário: câmera que para de entregar quadro,
 * aba que volta do segundo plano, trilha que o sistema pausou, navegador sem a
 * API de quadro.
 *
 * O teste mais importante é `o vigia é armado também no caminho do callback`.
 * Ele cobre exatamente o defeito relatado: o vigia existia, estava escrito,
 * tinha comentário explicando para que servia, e era armado só no ramo de
 * reserva, que é o ramo que nenhum navegador atual usa. Defesa escrita e não
 * instalada passa em revisão de código e falha na mão de quem mede.
 */

import { CadenciaDeQuadros, RESGATES_ATE_DESISTIR } from '../js/cadencia.js';

let passaram = 0;
let falharam = 0;
const falhas = [];

function verificar(nome, condicao, detalhe = '') {
  if (condicao) {
    passaram++;
  } else {
    falharam++;
    falhas.push(`${nome}${detalhe ? `: ${detalhe}` : ''}`);
  }
}

function igual(nome, obtido, esperado) {
  verificar(nome, obtido === esperado, `esperado ${esperado}, obtido ${obtido}`);
}

/**
 * Bancada com relógio, fila de animação e fila de quadro sob controle.
 *
 * Nada aqui é assíncrono de verdade: o tempo só anda quando o teste manda, o
 * que torna cada asserção determinística. Teste de agendamento que depende do
 * relógio real falha sozinho em máquina carregada, e aí ninguém mais confia
 * nele.
 */
function montarBancada({ comCallback = true, limiteDeSilencioMs = 500 } = {}) {
  let ms = 0;
  let proximoDeAnimacao = 1;
  let proximoDeQuadro = 1;
  const filaDeAnimacao = new Map();
  const filaDeQuadro = new Map();
  const cancelados = { animacao: [], quadro: [] };

  const video = {
    currentTime: 0,
    paused: false,
    chamadasDePlay: 0,
    play() {
      this.chamadasDePlay += 1;
      this.paused = false;
      return Promise.resolve();
    },
  };
  if (comCallback) {
    video.requestVideoFrameCallback = (fn) => {
      const id = proximoDeQuadro++;
      filaDeQuadro.set(id, fn);
      return id;
    };
    video.cancelVideoFrameCallback = (id) => {
      cancelados.quadro.push(id);
      filaDeQuadro.delete(id);
    };
  }

  const quadros = [];
  const silencios = [];
  let aoQuadro = (q) => quadros.push(q);

  const cadencia = new CadenciaDeQuadros({
    video,
    aoQuadro: (q) => aoQuadro(q),
    // O relatado primeiro, o estado depois e sem sobrescrevê-lo: o `estado`
    // também traz um `silencioMs`, só que recontado depois do resgate, e aí
    // vale zero. Espalhar por cima apagaria justamente o número sob teste.
    aoSilencio: (silencioMs, estado) => silencios.push({ ...estado, silencioMs }),
    agora: () => ms,
    pedirAnimacao: (fn) => {
      const id = proximoDeAnimacao++;
      filaDeAnimacao.set(id, fn);
      return id;
    },
    cancelarAnimacao: (id) => {
      cancelados.animacao.push(id);
      filaDeAnimacao.delete(id);
    },
    limiteDeSilencioMs,
  });

  /** Um quadro de tela: anda o relógio e drena a fila de animação. */
  function telaBate(passoMs = 16) {
    ms += passoMs;
    const pendentes = [...filaDeAnimacao.values()];
    filaDeAnimacao.clear();
    for (const fn of pendentes) fn(ms);
  }

  /** Um quadro de câmera, pelo caminho que estiver em uso. */
  function cameraEntrega(tempoS, { comMediaTime = true, passoMs = 16 } = {}) {
    video.currentTime = tempoS;
    if (filaDeQuadro.size) {
      ms += passoMs;
      const pendentes = [...filaDeQuadro.values()];
      filaDeQuadro.clear();
      for (const fn of pendentes) fn(ms, comMediaTime ? { mediaTime: tempoS } : {});
      return;
    }
    telaBate(passoMs);
  }

  function esperarEmSilencio(totalMs, passoMs = 16) {
    for (let gasto = 0; gasto < totalMs; gasto += passoMs) telaBate(passoMs);
  }

  return {
    cadencia,
    video,
    quadros,
    silencios,
    cancelados,
    telaBate,
    cameraEntrega,
    esperarEmSilencio,
    get relogio() { return ms; },
    get quadrosPendentes() { return filaDeQuadro.size; },
    get animacoesPendentes() { return filaDeAnimacao.size; },
    trocarConsumidor(fn) { aoQuadro = fn; },
  };
}

// --------------------------------------------------------- quadro a quadro
{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  b.cameraEntrega(0.10);
  b.cameraEntrega(0.15);
  igual('cada quadro novo vira uma chamada', b.quadros.length, 3);
  igual('o tempo entregue é o da mídia', b.quadros[2].tempoS, 0.15);
  igual('o número do quadro acompanha', b.quadros[2].numero, 3);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  b.cameraEntrega(0.05);
  b.cameraEntrega(0.05);
  igual('quadro repetido não entra duas vezes', b.quadros.length, 1);
}

{
  // `mediaTime` é o instante de apresentação daquele quadro; `currentTime` é
  // onde a mídia está quando por acaso se olhou. Quando os dois discordam, o
  // certo é o primeiro.
  const b = montarBancada();
  b.cadencia.iniciar();
  b.video.currentTime = 9.9;
  b.cameraEntrega(0.2);
  igual('mediaTime tem precedência sobre currentTime', b.quadros[0].tempoS, 0.2);
}

{
  const b = montarBancada({ comCallback: false });
  b.cadencia.iniciar();
  igual('sem a API de quadro, não usa o callback', b.cadencia.estado.usandoCallback, false);
  b.cameraEntrega(0.05);
  b.cameraEntrega(0.05);
  b.cameraEntrega(0.10);
  igual('no caminho de reserva o repetido também é rejeitado', b.quadros.length, 2);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(3.0);
  b.cameraEntrega(0.1);
  igual('tempo andando para trás é sinalizado', b.quadros[1].retrocedeu, true);
  igual('o primeiro quadro nunca é retrocesso', b.quadros[0].retrocedeu, false);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.video.currentTime = Number.NaN;
  b.cameraEntrega(Number.NaN, { comMediaTime: false });
  igual('tempo não finito é descartado', b.quadros.length, 0);
}

// ------------------------------------------------------------------ o vigia
{
  /*
    A regressão relatada, em forma de teste.

    Com o callback de quadro disponível, que é o caso de todo navegador atual,
    a câmera para de entregar imagem e nada mais religa a cadeia. Antes desta
    correção o vigia era armado só dentro do ramo de reserva, então aqui ele
    nunca chegava a existir e a medição morria para sempre.
  */
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  verificar('o vigia é armado também no caminho do callback', b.animacoesPendentes > 0);

  b.esperarEmSilencio(600);
  igual('o vigia percebe o silêncio e resgata', b.silencios.length, 1);
  verificar('o silêncio relatado é o medido', (b.silencios[0]?.silencioMs ?? 0) > 500);

  // E a cadeia volta a funcionar depois do resgate.
  b.cameraEntrega(1.0);
  igual('depois do resgate o quadro volta a chegar', b.quadros.length, 2);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.esperarEmSilencio(600);
  igual('um resgate só, e não uma rajada deles', b.silencios.length, 1);
  b.esperarEmSilencio(300);
  igual('dentro do limite não resgata de novo', b.silencios.length, 1);
  b.esperarEmSilencio(300);
  igual('passado o limite, resgata de novo', b.silencios.length, 2);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  for (let i = 0; i < RESGATES_ATE_DESISTIR; i++) b.esperarEmSilencio(600);
  igual('resgates seguidos fazem desistir do callback', b.cadencia.estado.usandoCallback, false);
  igual('e os resgates são contados', b.cadencia.estado.resgates, RESGATES_ATE_DESISTIR);
  verificar('nada ficou pendente na fila de quadro', b.quadrosPendentes === 0);

  // E a medição segue pelo caminho de reserva, na taxa do monitor.
  const antes = b.quadros.length;
  b.video.currentTime = 2.0;
  b.telaBate();
  igual('o caminho de reserva assume e entrega quadro', b.quadros.length, antes + 1);
  igual('pelo tempo da mídia', b.quadros[b.quadros.length - 1].tempoS, 2.0);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  // Resgate, quadro, resgate, quadro: falha esparsa não é motivo para desistir
  // do caminho bom.
  for (let i = 0; i < RESGATES_ATE_DESISTIR + 1; i++) {
    b.esperarEmSilencio(600);
    b.cameraEntrega(0.1 * (i + 1));
  }
  igual('quadro que chega zera a contagem de resgates seguidos',
    b.cadencia.estado.usandoCallback, true);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.video.paused = true;
  b.esperarEmSilencio(600);
  verificar('vídeo pausado é despertado no resgate', b.video.chamadasDePlay >= 1);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.video.paused = false;
  b.esperarEmSilencio(600);
  igual('vídeo tocando não leva play à toa', b.video.chamadasDePlay, 0);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  b.cadencia.resgatar();
  igual('resgatar força sem esperar o limite', b.silencios.length, 1);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  igual('parado, resgatar não faz nada', (b.cadencia.parar(), b.cadencia.resgatar(), b.silencios.length), 0);
}

// ------------------------------------------------------------------ parada
{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  b.cadencia.parar();
  b.cameraEntrega(0.10);
  b.esperarEmSilencio(2000);
  igual('depois de parar não chega mais quadro', b.quadros.length, 1);
  igual('nem resgate', b.silencios.length, 0);
  igual('e nada fica agendado', b.animacoesPendentes + b.quadrosPendentes, 0);
}

{
  const b = montarBancada();
  b.cadencia.iniciar();
  b.cameraEntrega(0.05);
  b.cadencia.iniciar();
  igual('iniciar duas vezes não duplica a cadeia', b.quadrosPendentes, 1);
}

// ---------------------------------------------------- robustez do consumidor
{
  /*
    Exceção no consumidor não pode levar a cadeia junto.

    É por isso que o reagendamento acontece antes de qualquer trabalho: um erro
    ao desenhar o gráfico, ou um canvas que o navegador recusou, derrubaria a
    captura inteira e o sintoma seria de novo "parou sozinha".
  */
  const b = montarBancada();
  let chamadas = 0;
  b.trocarConsumidor(() => { chamadas += 1; throw new Error('falha de propósito'); });
  b.cadencia.iniciar();
  try { b.cameraEntrega(0.05); } catch { /* a exceção sobe pelo callback falso */ }
  try { b.cameraEntrega(0.10); } catch { /* idem */ }
  igual('o quadro seguinte ainda é entregue depois de uma exceção', chamadas, 2);
}

{
  // O identificador do callback de vídeo não pode ir parar em
  // `cancelAnimationFrame`: são filas diferentes, e cancelar na errada deixa a
  // chamada antiga viva, que é como se ganha dois laços rodando ao mesmo tempo.
  const b = montarBancada();
  b.cadencia.iniciar();
  b.esperarEmSilencio(600);
  verificar('o cancelamento usa a fila do callback de vídeo',
    b.cancelados.quadro.length === 1, `cancelados ${JSON.stringify(b.cancelados)}`);
}

// ---------------------------------------------------------------------------
process.stdout.write(`\n${'-'.repeat(62)}\n`);
if (falharam) {
  process.stdout.write(`FALHAS (${falharam}):\n`);
  falhas.forEach((f) => process.stdout.write(`  - ${f}\n`));
}
process.stdout.write(`cadência: ${passaram} passaram, ${falharam} falharam\n`);
process.exit(falharam ? 1 : 0);
