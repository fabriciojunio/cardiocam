"""Comandos do protótipo consentido de telemetria."""

import csv
import json
import os
from pathlib import Path
import sys
import time
from cardiocam.dominio.erros import ErroCardiocam


def executar(a):
    from cardiocam.teleconsulta.transporte import SessaoTelemetria, criar_servidor, enviar
    try:
        token = os.environ.get(a.token_env, "")
        if a.operacao == "receber":
            sessao = SessaoTelemetria(a.sessao, token, a.consentimento, a.duracao)
            servidor = criar_servidor(sessao, a.porta)
            servidor.timeout = .5
            inicio = time.monotonic()
            print(f"Receptor local: http://127.0.0.1:{servidor.server_port}/leituras", flush=True)
            try:
                while time.monotonic()-inicio < a.duracao:
                    servidor.handle_request()
            finally:
                servidor.server_close()
                sessao.revogar()
        elif a.operacao == "camera":
            from cardiocam.fontes.webcam import abrir_webcam
            from cardiocam.teleconsulta.medicao_local import Transmissor, medir_e_transmitir
            from cardiocam.dominio.config import ConfiguracaoAnalise
            # Valida autorização e credencial antes de abrir o dispositivo.
            SessaoTelemetria(a.sessao, token, a.consentimento, a.duracao)
            abertura = abrir_webcam(indice=a.camera)
            if abertura.falhou:
                raise abertura.erro
            fonte = abertura.desempacotar()
            transmissor = Transmissor(a.url, token, a.consentimento)
            try:
                medir_e_transmitir(fonte, transmissor, a.sessao, a.duracao,
                                   ConfiguracaoAnalise(janela_s=a.janela, modelo_qualidade=a.modelo_qualidade))
            finally:
                fonte.fechar()
                transmissor.fechar()
            print(f"Leituras confirmadas: {transmissor.confirmadas}; falhas de rede: {transmissor.falhas}.")
            if transmissor.falhas:
                return 1
        else:
            with Path(a.leituras).open(encoding="utf-8-sig", newline="") as arquivo:
                for i, linha in enumerate(csv.DictReader(arquivo)):
                    aceita = linha["aceita"].strip().lower()
                    if aceita not in ("true", "false"):
                        raise ValueError("A decisão precisa ser True ou False.")
                    leitura = {"sessao": a.sessao, "sequencia": i, "instante_s": float(linha["instante_s"]),
                               "bpm": float(linha["bpm"]) if aceita == "true" else None,
                               "qualidade": float(linha["qualidade"]) if linha.get("qualidade") else None,
                               "aceita": aceita == "true"}
                    enviar(a.url, token, leitura, a.consentimento)
            print("Leituras confirmadas pelo receptor.")
        return 0
    except (OSError, ValueError, RuntimeError, ErroCardiocam) as erro:
        print(f"Transmissão não concluída: {erro}", file=sys.stderr)
        return 1


def adicionar_comandos(subcomandos):
    p = subcomandos.add_parser("teleconsulta", help="protótipo de leituras locais com consentimento")
    s = p.add_subparsers(dest="operacao", required=True)
    receber = s.add_parser("receber")
    receber.add_argument("--porta", type=int, default=8765)
    receber.add_argument("--duracao", type=float, default=1800)
    transmitir = s.add_parser("transmitir")
    transmitir.add_argument("leituras", help="CSV exportado pela medição local")
    transmitir.add_argument("--url", required=True)
    camera = s.add_parser("camera", help="mede e transmite antes da compressão de vídeo")
    camera.add_argument("--camera", type=int, default=0)
    camera.add_argument("--duracao", type=float, default=300)
    camera.add_argument("--janela", type=float, default=25)
    camera.add_argument("--url", required=True)
    from cardiocam.cli import _modelo_qualidade
    camera.add_argument("--modelo-qualidade", type=_modelo_qualidade)
    for parser in (receber, transmitir, camera):
        parser.add_argument("--sessao", required=True, help="identificador pseudônimo combinado")
        parser.add_argument("--token-env", default="CARDIOCAM_TOKEN", help="nome da variável de ambiente com token de 32+ caracteres")
        parser.add_argument("--consentimento", action="store_true", help="confirma consentimento explícito do participante")
    p.set_defaults(funcao=executar)
