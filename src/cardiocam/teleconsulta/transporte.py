"""Telemetria consentida, autenticada e limitada à duração da sessão.

Transmite leituras escalares, sem imagens. HTTP é restrito ao loopback;
destinos remotos precisam de HTTPS com a validação TLS padrão do sistema.
Não é prontuário, servidor público ou validação clínica.
"""

from collections import deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import secrets
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def validar_leitura(dados):
    campos = {"sessao", "sequencia", "instante_s", "bpm", "qualidade", "aceita"}
    if not isinstance(dados, dict) or set(dados) != campos:
        raise ValueError("Leitura deve conter apenas os campos de telemetria.")
    if (not isinstance(dados["sessao"], str) or not 1 <= len(dados["sessao"]) <= 80
            or type(dados["sequencia"]) is not int or dados["sequencia"] < 0
            or type(dados["aceita"]) is not bool):
        raise ValueError("Identificação ou decisão inválida.")
    for nome in ("instante_s", "bpm", "qualidade"):
        valor = dados[nome]
        if valor is not None and (type(valor) not in (int, float) or not math.isfinite(valor)):
            raise ValueError("Valores de telemetria precisam ser finitos.")
    if dados["instante_s"] is None or dados["instante_s"] < 0:
        raise ValueError("Instante inválido.")
    if dados["qualidade"] is not None and not 0 <= dados["qualidade"] <= 1:
        raise ValueError("Qualidade fora de zero a um.")
    if dados["aceita"] and (dados["bpm"] is None or not 20 <= dados["bpm"] <= 300):
        raise ValueError("Leitura aceita sem BPM válido.")
    if not dados["aceita"] and dados["bpm"] is not None:
        raise ValueError("Leitura recusada deve apagar o BPM.")


class SessaoTelemetria:
    def __init__(self, identificador, token, consentimento: bool, duracao_s=1800, relogio=time.monotonic):
        if consentimento is not True:
            raise ValueError("Registre o consentimento explícito antes de transmitir.")
        if (not isinstance(identificador, str) or not 1 <= len(identificador) <= 80
                or not isinstance(token, str) or len(token) < 32
                or not math.isfinite(duracao_s) or not 0 < duracao_s <= 3600):
            raise ValueError("Sessão, token ou duração inválidos.")
        self.identificador, self._token, self._relogio = identificador, token, relogio
        self._expira = relogio()+duracao_s
        self._revogada = False
        self._ultima_sequencia = -1
        self._ultimo_instante = -1.
        self._leituras = deque(maxlen=1000)
        self._lock = threading.Lock()

    def revogar(self):
        with self._lock:
            self._revogada = True
            self._leituras.clear()

    def receber(self, token, leitura):
        validar_leitura(leitura)
        with self._lock:
            if not isinstance(token, str) or not secrets.compare_digest(token, self._token):
                raise PermissionError("Autenticação recusada.")
            if self._revogada or self._relogio() >= self._expira:
                raise PermissionError("Sessão encerrada.")
            if (leitura["sessao"] != self.identificador or leitura["sequencia"] <= self._ultima_sequencia
                    or leitura["instante_s"] <= self._ultimo_instante):
                raise ValueError("Sessão divergente ou leitura repetida/fora de ordem.")
            self._ultima_sequencia, self._ultimo_instante = leitura["sequencia"], leitura["instante_s"]
            self._leituras.append(dict(leitura))

    def leituras(self):
        with self._lock:
            if self._revogada or self._relogio() >= self._expira:
                self._leituras.clear()
            return [dict(l) for l in self._leituras]


def criar_servidor(sessao, porta=0):
    class Receptor(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # Tokens e leituras não entram em logs HTTP.

        def do_POST(self):
            status = 204
            try:
                if self.path != "/leituras":
                    status = 404
                else:
                    tamanho = int(self.headers.get("Content-Length", "0"))
                    if not 0 < tamanho <= 2048 or self.headers.get_content_type() != "application/json":
                        raise ValueError("Corpo inválido.")
                    autorizacao = self.headers.get("Authorization", "")
                    if not autorizacao.startswith("Bearer "):
                        raise PermissionError("Sem credencial.")
                    sessao.receber(autorizacao[7:], json.loads(self.rfile.read(tamanho)))
            except PermissionError:
                status = 401
            except (ValueError, UnicodeError, TypeError, OverflowError):
                status = 400
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Receptor)
    servidor.daemon_threads = True
    return servidor


@contextmanager
def receptor_local(sessao, porta=0):
    servidor = criar_servidor(sessao, porta)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}/leituras"
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)
        sessao.revogar()


def enviar(url, token, leitura, consentimento: bool):
    if consentimento is not True or not isinstance(token, str) or len(token) < 32:
        raise ValueError("Consentimento e token de sessão são obrigatórios.")
    destino = urlsplit(url)
    if (destino.username or destino.password or destino.fragment or destino.query
            or destino.path != "/leituras" or not destino.hostname
            or destino.scheme not in ("http", "https")
            or (destino.scheme == "http" and destino.hostname not in ("127.0.0.1", "localhost", "::1"))):
        raise ValueError("Use HTTPS para destino remoto e /leituras sem credenciais na URL.")
    validar_leitura(leitura)
    corpo = json.dumps(leitura, allow_nan=False).encode("utf-8")
    pedido = Request(url, data=corpo, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + token})
    # Redirecionamentos poderiam enviar o token a outro destino. Recusamos.
    from urllib.request import HTTPRedirectHandler, build_opener
    class SemRedirecionamento(HTTPRedirectHandler):
        def redirect_request(self, *_):
            return None
    with build_opener(SemRedirecionamento()).open(pedido, timeout=5) as resposta:
        if resposta.status != 204:
            raise ValueError("O receptor não confirmou a leitura.")
