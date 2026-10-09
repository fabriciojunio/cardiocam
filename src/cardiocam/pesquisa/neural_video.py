"""Avaliação de redes e modalidades sem armazenar o vídeo completo."""

from collections import deque
from dataclasses import asdict

import cv2
import numpy as np
from scipy import signal

from cardiocam.dominio.sinal import SinalPulso
from cardiocam.fontes.arquivo import FonteArquivo
from cardiocam.pesquisa.estimacao import comparar_estimadores
from cardiocam.pesquisa.espacial import extrair_regioes
from cardiocam.pesquisa.modalidades import extrair_bcg, medir_pupila, regioes_perioculares
from cardiocam.visao.detector_face import DetectorHaar
from cardiocam.visao.olhos import DetectorOlhos
from cardiocam.visao.rastreador import RastreadorRosto


def _pulso_filtrado(x, fps, nome):
    if fps <= 8 or not np.isfinite(x).all() or np.std(x) < 1e-10:
        raise ValueError("Sinal insuficiente, constante ou FPS incompatível com a banda.")
    sos = signal.butter(4, [.7, 4], fs=fps, btype="bandpass", output="sos")
    return SinalPulso(signal.sosfiltfilt(sos, x), fps, nome)


def avaliar_rede_video(caminho, modelo, janela_s=10, referencia=None, offset_s=0, detector=None):
    if not np.isfinite([janela_s, offset_s]).all() or not 4 <= janela_s <= 20:
        raise ValueError("Janela neural entre 4 e 20 segundos e offset finito são necessários.")
    if modelo.nome == "zero_dce":
        raise ValueError("Zero-DCE realça imagens; não produz onda PPG.")
    rastreador = RastreadorRosto(detector or DetectorHaar(), tolerancia_quadros=0)
    buffer, linhas = deque(maxlen=600), []
    anterior, inicio = None, None
    with FonteArquivo(caminho) as fonte:
        for imagem, t in fonte.quadros():
            rosto = rastreador.atualizar(imagem)
            lacuna = anterior is not None and t-anterior > .3
            anterior = t
            if rosto.falhou or rastreador.contexto_alterado or lacuna:
                buffer.clear()
                inicio = None
                continue
            inicio = t if inicio is None else inicio
            buffer.append((t, rosto.desempacotar().recortar(imagem).copy()))
            if t-inicio < janela_s:
                continue
            tempos = np.array([q[0] for q in buffer])
            fps = (len(tempos)-1)/(tempos[-1]-tempos[0])
            linha = {"instante_s": t, "estimadores": None, "referencia_bpm": referencia(t+offset_s) if referencia else None}
            try:
                if tempos[-1]-tempos[0] < janela_s-.2 or np.diff(tempos).max() > .3:
                    raise ValueError("Janela neural incompleta.")
                tamanho = getattr(modelo, "tamanho", 64 if modelo.nome == "physnet" else 36)
                video = np.array([cv2.resize(q[1], (tamanho, tamanho)) for q in buffer])
                onda = modelo.prever(video)
                if len(onda) not in (len(video), len(video)-1):
                    raise ValueError("Comprimento da saída neural incompatível.")
                t_onda = tempos if len(onda) == len(video) else tempos[:-1]
                onda = np.interp(np.linspace(t_onda[0], t_onda[-1], len(onda)), t_onda, onda)
                fps_onda = (len(onda)-1)/(t_onda[-1]-t_onda[0])
                linha["estimadores"] = comparar_estimadores(_pulso_filtrado(onda, fps_onda, modelo.nome))
            except ValueError as erro:
                linha["motivo"] = str(erro)
            linhas.append(linha)
            buffer.clear()
            inicio = None
    return {"experimental": True, "modelo": modelo.procedencia, "janelas": linhas}


def avaliar_modalidades(caminho, janela_s=10, detector=None, detector_olhos=None):
    if not np.isfinite(janela_s) or not 4 <= janela_s <= 20:
        raise ValueError("Janela entre 4 e 20 segundos é necessária.")
    rastreador = RastreadorRosto(detector or DetectorHaar(), tolerancia_quadros=0)
    olhos_detector = detector_olhos or DetectorOlhos()
    pupilas, bcg, periocular = [], [], []
    anterior = pontos = None
    trajetorias, tempos = [], []
    with FonteArquivo(caminho) as fonte:
        for imagem, t in fonte.quadros():
            rosto = rastreador.atualizar(imagem)
            if rosto.falhou or rastreador.contexto_alterado or (tempos and t-tempos[-1] > .3):
                anterior = pontos = None
                trajetorias, tempos = [], []
            if rosto.falhou:
                continue
            caixa = rosto.desempacotar()
            olhos = olhos_detector.detectar(imagem, caixa)
            if olhos is not None:
                d = olhos.separacao
                from cardiocam.visao.geometria import Retangulo
                for lado, (x, y) in enumerate((olhos.esquerdo, olhos.direito)):
                    area = Retangulo(round(x-.2*d), round(y-.13*d), round(.4*d), round(.26*d))
                    p = medir_pupila(area.recortar(imagem))
                    pupilas.append({"instante_s": t, "olho": lado, "pupila": None if p is None else asdict(p)})
                regioes = regioes_perioculares(olhos)
                periocular.append({"instante_s": t, "rgb": [
                    next(iter(extrair_regioes(imagem, r, 1).values())).rgb.tolist()
                    if extrair_regioes(imagem, r, 1) else None for r in regioes]})
            cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
            if anterior is None or pontos is None:
                mascara = np.zeros(cinza.shape, np.uint8)
                segura = caixa.limitar(cinza.shape[1], cinza.shape[0])
                mascara[segura.y:segura.base, segura.x:segura.direita] = 255
                pontos = cv2.goodFeaturesToTrack(cinza, 80, .01, 5, mask=mascara)
                if pontos is not None:
                    trajetorias, tempos = [pontos.reshape(-1, 2)], [t]
            else:
                novos, st, _ = cv2.calcOpticalFlowPyrLK(anterior, cinza, pontos, None)
                if novos is None:
                    pontos = None
                else:
                    voltaram, stb, _ = cv2.calcOpticalFlowPyrLK(cinza, anterior, novos, None)
                    bons = np.zeros(len(pontos), bool) if voltaram is None else (
                        (st.ravel() == 1) & (stb.ravel() == 1)
                        & (np.linalg.norm((voltaram-pontos).reshape(-1, 2), axis=1) < 1.5))
                    if bons.sum() < 3:
                        pontos = None
                        trajetorias, tempos = [], []
                    else:
                        trajetorias = [q[bons] for q in trajetorias]
                        pontos = novos[bons]
                        trajetorias.append(pontos.reshape(-1, 2))
                        tempos.append(t)
            anterior = cinza
            if tempos and t-tempos[0] >= janela_s:
                linha = {"instante_s": t, "estimadores": None}
                try:
                    fps = (len(tempos)-1)/(tempos[-1]-tempos[0])
                    trajetoria = np.array(trajetorias)
                    uniformes = np.linspace(tempos[0], tempos[-1], len(tempos))
                    trajetoria = np.array([[np.interp(uniformes, tempos, trajetoria[:, p, c])
                                            for c in range(2)] for p in range(trajetoria.shape[1])]).transpose(2, 0, 1)
                    pulso = extrair_bcg(trajetoria, fps)
                    linha["estimadores"] = comparar_estimadores(_pulso_filtrado(pulso.amostras, fps, "video_bcg"))
                except ValueError as erro:
                    linha["motivo"] = str(erro)
                bcg.append(linha)
                anterior = pontos = None
                trajetorias, tempos = [], []
            if len(tempos) >= 600:
                anterior = pontos = None
                trajetorias, tempos = [], []
    return {"experimental": True, "pupilas": pupilas, "periocular": periocular, "video_bcg": bcg,
            "aviso": "Pupila e movimento não são referência cardíaca; séries não entram na medição padrão."}
