"""Avaliação de vídeo por região, com manifesto e janelas auditáveis."""

from collections import deque
from dataclasses import asdict, dataclass
from time import perf_counter

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.qualidade.caracteristicas import correlacao, extrair
from cardiocam.rppg import criar_algoritmo
from cardiocam.rppg.base import finalizar
from cardiocam.rppg.experimentais import ALGORITMOS_EXPERIMENTAIS
from cardiocam.sinais.espectro import analisar
from cardiocam.visao.detector_face import DetectorHaar
from cardiocam.visao.rastreador import RastreadorRosto
from cardiocam.pesquisa.espacial import extrair_regioes, extrair_ssr
from cardiocam.pesquisa.estabilizacao import EstabilizadorOptico, alinhar_pelos_olhos, pose_aproveitavel
from cardiocam.visao.olhos import DetectorOlhos
from cardiocam.pesquisa.estimacao import Candidato, RastreadorTemporal, comparar_estimadores, fundir
from cardiocam.pesquisa.fotometria import corrigir_temporal, normalizar_imagem

METODOS = ("verde", "pos", "chrom", "ica", "lgi", "omit", "pbv_adaptativo", "ssr")


@dataclass(frozen=True)
class OpcoesExperimento:
    janela_s: float = 10
    passo_s: float = 1
    grade: int = 3
    metodos: tuple[str, ...] = ("pos", "chrom", "lgi", "omit", "pbv_adaptativo", "ssr")
    estabilizar: bool = False
    fotometria: str = "nenhum"
    corrigir_fundo: bool = False
    suavizacao_s: float = 0
    ancorar_olhos: bool = False

    def __post_init__(self):
        if (not np.isfinite([self.janela_s, self.passo_s, self.suavizacao_s]).all()
                or self.janela_s < 4 or self.passo_s <= 0 or not 0 <= self.suavizacao_s <= .2
                or not 1 <= self.grade <= 8 or not self.metodos
                or len(set(self.metodos)) != len(self.metodos) or set(self.metodos)-set(METODOS)
                or self.fotometria not in ("nenhum", "retinex", "crominancia")):
            raise ValueError("Opções de pesquisa inválidas.")


def _algoritmo(nome):
    for tipo in ALGORITMOS_EXPERIMENTAIS:
        if tipo.nome == nome:
            return tipo()
    return criar_algoritmo(nome)


def analisar_video(fonte, opcoes: OpcoesExperimento = OpcoesExperimento(), detector=None,
                   referencia=None, offset_s: float = 0, lacuna_referencia_s: float = 2,
                   transformador=None) -> dict:
    """Consome uma fonte finita. Memória limitada à janela; imagens não são salvas.

    `referencia` é uma função instante→BPM ou None, usada SOMENTE após estimar.
    `transformador` aplica uma perturbação determinística para ablação.
    """
    if not np.isfinite(offset_s) or not np.isfinite(lacuna_referencia_s) or lacuna_referencia_s <= 0:
        raise ValueError("Alinhamento inválido.")
    rastreador = RastreadorRosto(detector or DetectorHaar(), tolerancia_quadros=0)
    estabilizador, temporal = EstabilizadorOptico(), RastreadorTemporal()
    janela = deque(maxlen=round(opcoes.janela_s*120)+1)
    registros, caracteristicas = [], []
    ultimo = proxima = None
    referencia_espacial = None
    olhos_referencia = caixa_referencia = None
    detector_olhos = DetectorOlhos() if opcoes.ancorar_olhos else None
    anterior = None
    quadros = perdas = reinicios = 0
    inicio = perf_counter()
    for imagem, instante in fonte.quadros():
        if not np.isfinite(instante) or (ultimo is not None and instante <= ultimo):
            raise ValueError("Os quadros precisam ter instantes finitos e crescentes.")
        quadros += 1
        lacuna = ultimo is not None and instante-ultimo > .3
        ultimo = instante
        if proxima is None:
            proxima = instante + opcoes.janela_s
        if transformador is not None:
            imagem = transformador(imagem, instante, quadros-1)
        repetido = anterior is not None and anterior.shape == imagem.shape and np.array_equal(imagem, anterior)
        anterior = imagem.copy()
        rosto = rastreador.atualizar(imagem)
        reiniciar = lacuna or rastreador.contexto_alterado or rosto.falhou or repetido
        if reiniciar:
            janela.clear()
            temporal.reiniciar()
            estabilizador.reiniciar()
            referencia_espacial = None
            olhos_referencia = caixa_referencia = None
            reinicios += 1
        if rosto.falhou or repetido:
            perdas += 1
        else:
            caixa = rosto.desempacotar()
            aproveitavel = True
            if opcoes.ancorar_olhos:
                olhos = detector_olhos.detectar(imagem, caixa)
                aproveitavel = olhos is not None and pose_aproveitavel(olhos, caixa)
                if aproveitavel:
                    if olhos_referencia is None:
                        olhos_referencia, caixa_referencia = olhos, caixa
                    imagem = alinhar_pelos_olhos(imagem, olhos, olhos_referencia)
                    caixa = caixa_referencia
                else:
                    janela.clear()
                    temporal.reiniciar()
                    perdas += 1
            if opcoes.estabilizar:
                estabilizada = estabilizador.atualizar(imagem, caixa, instante)
                if estabilizada.reiniciado:
                    janela.clear()
                    temporal.reiniciar()
                    referencia_espacial = caixa
                if not estabilizada.valido:
                    perdas += 1
                    aproveitavel = False
                imagem = estabilizada.imagem
                caixa = referencia_espacial
            mascara_fundo = np.ones(imagem.shape[:2], bool)
            segura = caixa.limitar(imagem.shape[1], imagem.shape[0])
            mascara_fundo[segura.y:segura.base, segura.x:segura.direita] = False
            fundo = imagem[mascara_fundo][:, ::-1].mean(axis=0)/255 if mascara_fundo.any() else None
            normalizada = normalizar_imagem(imagem, opcoes.fotometria)
            regioes = extrair_regioes(normalizada, caixa, opcoes.grade) if aproveitavel else {}
            janela.append((instante, regioes, caixa.centro[0]/imagem.shape[1], fundo))
            while janela and instante-janela[0][0] > opcoes.janela_s:
                janela.popleft()
        if instante < proxima:
            continue
        proxima = instante + opcoes.passo_s
        candidatos, falhas = [], []
        completa = len(janela) >= 32 and janela[-1][0]-janela[0][0] >= opcoes.janela_s-.2
        if completa:
            tempos = np.array([q[0] for q in janela])
            fps = (len(tempos)-1)/(tempos[-1]-tempos[0])
            if fps < 8 or fps > 120 or np.diff(tempos).max() > .3:
                completa = False
            else:
                uniformes = np.linspace(tempos[0], tempos[-1], len(tempos))
                comuns = set.intersection(*(set(q[1]) for q in janela))
                b = np.array([q[3] for q in janela]).T if all(q[3] is not None for q in janela) else None
                fundo = None if b is None else np.array([np.interp(uniformes, tempos, c) for c in b])
                for regiao in sorted(comuns):
                    amostras = [q[1][regiao] for q in janela]
                    rgb_original = np.array([a.rgb for a in amostras]).T
                    rgb = np.array([np.interp(uniformes, tempos, c) for c in rgb_original])
                    rgb = corrigir_temporal(rgb, fps, fundo if opcoes.corrigir_fundo else None, opcoes.suavizacao_s)
                    serie = SerieRGB(*rgb, fps, uniformes)
                    # Exporta também estimativas de baixo SNR para não treinar
                    # qualidade apenas nas janelas que já passaram pelo filtro.
                    config = ConfiguracaoAnalise(janela_s=opcoes.janela_s, usar_fundo=False, snr_minimo_db=-60)
                    for metodo in opcoes.metodos:
                        try:
                            if metodo == "ssr":
                                momentos = np.array([a.segundo_momento for a in amostras])
                                momentos = np.array([[np.interp(uniformes, tempos, momentos[:, i, j])
                                                      for j in range(3)] for i in range(3)]).transpose(2, 0, 1)
                                bruto = extrair_ssr(momentos, fps)
                                pulso = finalizar(bruto.amostras, serie, config, "ssr").desempacotar()
                            else:
                                pulso = estimar_de_serie(serie, config, _algoritmo(metodo)).desempacotar().pulso
                            estimadores = comparar_estimadores(pulso, config.banda)
                            espectral = analisar(pulso).desempacotar()
                            pele = float(np.mean([a.fracao_pele for a in amostras]))
                            saturacao = float(np.mean([a.fracao_saturada for a in amostras]))
                            acoplamento = correlacao(pulso.amostras, fundo[1]) if fundo is not None else None
                            candidato = Candidato(regiao, metodo, espectral.bpm, espectral.snr_db,
                                                  pele, saturacao, acoplamento)
                            # Discordância de estimadores é motivo para não votar.
                            if max(estimadores.values())-min(estimadores.values()) <= 8:
                                candidatos.append(candidato)
                            f = extrair(pulso, espectral.espectro, espectral.frequencia_hz, espectral.snr_db,
                                        fracao_de_pele=pele, fracao_saturada=saturacao,
                                        posicoes_roi=np.array([q[2] for q in janela]),
                                        sinal_do_fundo=None if fundo is None else fundo[1],
                                        instantes=tempos, serie_rgb=rgb)
                            verdade = referencia(instante+offset_s) if referencia else None
                            caracteristicas.append({"instante_s": instante, "regiao": regiao, "algoritmo": metodo,
                                                    "bpm": espectral.bpm, "referencia_bpm": verdade,
                                                    "erro_bpm": None if verdade is None else espectral.bpm-verdade,
                                                    **{k: float(v) if np.isfinite(v) else None for k, v in asdict(f).items()},
                                                    "caracteristicas_ausentes": [] if fundo is not None else ["correlacao_com_fundo"]})
                        except (ValueError, np.linalg.LinAlgError) as erro:
                            falhas.append({"regiao": regiao, "algoritmo": metodo, "motivo": str(erro)})
                        except Exception as erro:
                            from cardiocam.dominio.erros import ErroCardiocam
                            if not isinstance(erro, ErroCardiocam):
                                raise
                            falhas.append({"regiao": regiao, "algoritmo": metodo, "motivo": str(erro)})
        consenso = fundir(candidatos)
        bpm = temporal.atualizar(instante, consenso)
        verdade = referencia(instante+offset_s) if referencia else None
        registros.append({"instante_s": instante, "bpm": bpm, "aceita": bpm is not None,
                          "referencia_bpm": verdade, "erro_bpm": None if bpm is None or verdade is None else bpm-verdade,
                          "motivo": consenso.motivo if completa else "Janela incompleta ou descontínua.",
                          "candidatos": [asdict(c) for c in candidatos], "falhas": falhas})
    decorrido = perf_counter()-inicio
    erros = [r["erro_bpm"] for r in registros if r["erro_bpm"] is not None]
    metricas = {"cobertura_registros": sum(r["aceita"] for r in registros)/len(registros) if registros else 0,
                "aceitas_com_referencia": len(erros), "mae_bpm": float(np.mean(np.abs(erros))) if erros else None,
                "rmse_bpm": float(np.sqrt(np.mean(np.square(erros)))) if erros else None,
                "vies_bpm": float(np.mean(erros)) if erros else None}
    return {"versao": 1, "experimental": True, "opcoes": asdict(opcoes),
            "quadros": quadros, "perdas": perdas, "reinicios": reinicios,
            "tempo_processamento_s": decorrido, "fps_processamento": quadros/max(decorrido, 1e-9),
            "janelas": registros, "caracteristicas": caracteristicas, "metricas": metricas}
