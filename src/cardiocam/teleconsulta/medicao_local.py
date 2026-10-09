"""Medição na câmera do paciente antes da codificação de uma videochamada."""

from queue import Empty, Full, Queue
import threading

import numpy as np

from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade, aplicar_veredito
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.pipeline.analisador import MonitorCardiaco
from cardiocam.teleconsulta.transporte import enviar


class Transmissor:
    """Fila de uma leitura; transmissão lenta não paralisa a câmera."""
    def __init__(self, url, token, consentimento, remetente=enviar):
        if consentimento is not True:
            raise ValueError("É necessário consentimento explícito.")
        self._url, self._token, self._consentimento, self._remetente = url, token, consentimento, remetente
        self._fila = Queue(maxsize=1)
        self._fim = threading.Event()
        self.confirmadas = self.falhas = self.descartadas = 0
        self._thread = threading.Thread(target=self._executar, daemon=True)
        self._thread.start()

    def publicar(self, leitura):
        from cardiocam.teleconsulta.transporte import validar_leitura
        validar_leitura(leitura)
        if self._fim.is_set():
            raise RuntimeError("O transmissor já foi encerrado.")
        try:
            self._fila.put_nowait(dict(leitura))
        except Full:
            try:
                self._fila.get_nowait()
                self.descartadas += 1
            except Empty:
                pass
            self._fila.put_nowait(dict(leitura))

    def _executar(self):
        while not self._fim.is_set() or not self._fila.empty():
            try:
                leitura = self._fila.get(timeout=.1)
            except Empty:
                continue
            try:
                self._remetente(self._url, self._token, leitura, self._consentimento)
                self.confirmadas += 1
            except (OSError, ValueError):
                self.falhas += 1

    def fechar(self):
        self._fim.set()
        self._thread.join(timeout=6)
        if self._thread.is_alive():
            raise RuntimeError("A transmissão não encerrou no prazo de rede.")


def medir_e_transmitir(fonte, transmissor, sessao, duracao_s=300, config=None, detector=None):
    if not np.isfinite(duracao_s) or not 0 < duracao_s <= 3600:
        raise ValueError("Duração da sessão inválida.")
    config = config or ConfiguracaoAnalise(janela_s=25)
    monitor = MonitorCardiaco(fps=fonte.fps, config=config, detector=detector)
    juiz = JuizDeQualidade(config.amostras_por_janela(fonte.fps), caminho_modelo=config.modelo_qualidade)
    inicio = ultimo_envio = None
    sequencia = 0
    for imagem, instante in fonte.quadros():
        inicio = instante if inicio is None else inicio
        if instante-inicio >= duracao_s:
            break
        estado = monitor.processar(imagem, instante)
        juiz.registrar_quadro(imagem, estado)
        aplicar_veredito(juiz, estado)
        if ultimo_envio is not None and instante-ultimo_envio < 1:
            continue
        ultimo_envio = instante
        aceita = estado.bpm_exibido is not None and not estado.recusada
        transmissor.publicar({"sessao": sessao, "sequencia": sequencia, "instante_s": instante-inicio,
                               "aceita": aceita, "bpm": float(estado.bpm_exibido) if aceita else None,
                               "qualidade": estado.qualidade})
        sequencia += 1
    return {"publicadas": sequencia, "experimental": True}
