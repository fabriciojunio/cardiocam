"""Comandos dos experimentos optativos, com saídas revisáveis em UTF-8."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
import cv2

from cardiocam.pesquisa.arquivos import gravar_json
from cardiocam.dominio.erros import ErroCardiocam


def _referencia(argumentos):
    if not getattr(argumentos, "referencia", None):
        return None
    from cardiocam.avaliacao.referencia import ler_referencia, valor_referencia
    t, bpm = ler_referencia(argumentos.referencia)
    return lambda instante: valor_referencia(t, bpm, instante, argumentos.lacuna_referencia)


def _opcoes(argumentos):
    from cardiocam.pesquisa.experimento import OpcoesExperimento
    return OpcoesExperimento(argumentos.janela, argumentos.passo, argumentos.grade,
                             tuple(argumentos.metodos), argumentos.estabilizar, argumentos.fotometria,
                             argumentos.corrigir_fundo, argumentos.suavizacao, argumentos.ancorar_olhos)


def _avaliar(caminho, argumentos):
    from cardiocam.fontes.arquivo import FonteArquivo
    from cardiocam.pesquisa.experimento import analisar_video
    with FonteArquivo(caminho) as fonte:
        detector = _detector(caminho, argumentos, fonte)
        return analisar_video(fonte, _opcoes(argumentos), detector, _referencia(argumentos), argumentos.offset)


def _detector(caminho, argumentos, fonte):
    if not argumentos.area:
        return None
    import cv2
    from cardiocam.fontes.arquivo import FonteArquivo
    from cardiocam.visao.detector_face import DetectorRegiaoFixa
    from cardiocam.visao.geometria import Retangulo
    area = argumentos.area
    if Path(caminho).resolve() != Path(argumentos.video).resolve():
        with FonteArquivo(argumentos.video) as original:
            fatores = [fonte._captura.get(p)/original._captura.get(p)
                       for p in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT)]
        area = [round(v*fatores[i % 2]) for i, v in enumerate(area)]
    return DetectorRegiaoFixa(Retangulo(*area))


def _executar(a):
    if a.experimento == "exposicao" and (not np.isfinite(a.duracao) or not 0 < a.duracao <= 300):
        raise ValueError("A calibração de exposição deve durar entre zero e 300 segundos.")
    if a.experimento == "video":
        relatorio = _avaliar(a.video, a)
        gravar_json(a.saida, relatorio)
        print(f"{len(relatorio['janelas'])} janelas; resultado experimental gravado em {a.saida}.")
    elif a.experimento == "compressao":
        from cardiocam.pesquisa.compressao import VarianteCompressao, comparar_compressao
        variantes = [VarianteCompressao(c, b, *r, p) for c in a.codecs for b in a.bitrates
                     for r in a.resolucoes for p in a.perdas]
        relatorio = comparar_compressao(a.video, a.saida, variantes, lambda p: _avaliar(p, a))
        destino = Path(relatorio["pasta"]) / "comparacao.json"
        gravar_json(destino, relatorio)
        print(f"Original e {len(variantes)} variantes avaliados: {destino}")
    elif a.experimento == "recalibrar":
        from cardiocam.pesquisa.calibracao import recalibrar
        relatorio = recalibrar(a.manifesto, a.saida, cobertura_minima=a.cobertura, erro_alvo_bpm=a.erro_alvo)
        print(relatorio.resumo())
    elif a.experimento == "treinar-rede":
        from cardiocam.pesquisa.treino_neural import treinar_rede
        import torch
        torch.set_num_threads(1)
        r = treinar_rede(a.manifesto, a.arquitetura, a.saida, a.epocas, a.taxa, a.semente)
        print(f"Treino experimental concluído; perda de teste: {r['perda_teste']:.6f}.")
    elif a.experimento == "rede":
        from cardiocam.pesquisa.modelos import ModeloNeural, ModeloPPGONNX, ler_manifesto
        from cardiocam.pesquisa.neural_video import avaliar_rede_video
        dados, _ = ler_manifesto(a.pesos)
        modelo = ModeloPPGONNX(a.pesos) if dados["formato"] == "onnx" else ModeloNeural(a.pesos)
        r = avaliar_rede_video(a.video, modelo, a.janela, _referencia(a), a.offset)
        gravar_json(a.saida, r)
        print(f"Avaliação neural experimental gravada em {a.saida}.")
    elif a.experimento == "ablacao":
        from cardiocam.pesquisa.perturbacoes import Perturbacao
        from cardiocam.pesquisa.experimento import analisar_video
        from cardiocam.fontes.arquivo import FonteArquivo
        from cardiocam.visao.detector_face import DetectorRegiaoFixa
        from cardiocam.visao.geometria import Retangulo
        perturbacao = Perturbacao(a.movimento, a.iluminacao, a.frequencia, a.ruido, a.congelar, a.semente)
        with FonteArquivo(a.video) as fonte:
            detector = DetectorRegiaoFixa(Retangulo(*a.area)) if a.area else None
            r = analisar_video(fonte, _opcoes(a), detector, _referencia(a), a.offset,
                               transformador=perturbacao.criar())
        gravar_json(a.saida, {"original": _avaliar(a.video, a), "perturbacao": asdict(perturbacao), "perturbado": r})
        print(f"Ablação gravada em {a.saida}.")
    elif a.experimento == "modalidades":
        from cardiocam.pesquisa.neural_video import avaliar_modalidades
        gravar_json(a.saida, avaliar_modalidades(a.video, a.janela))
        print(f"Séries de modalidades experimentais gravadas em {a.saida}.")
    elif a.experimento == "realcar":
        from cardiocam.pesquisa.modelos import RealcadorONNX, RealcadorLocal, ler_manifesto
        # O realçador é aplicado antes da extração; a ablação inclui o original.
        from cardiocam.pesquisa.experimento import analisar_video
        from cardiocam.fontes.arquivo import FonteArquivo
        dados, _ = ler_manifesto(a.pesos)
        realcador = RealcadorONNX(a.pesos) if dados["formato"] == "onnx" else RealcadorLocal(a.pesos)
        with FonteArquivo(a.video) as fonte:
            r = analisar_video(fonte, _opcoes(a), _detector(a.video, a, fonte), referencia=_referencia(a), offset_s=a.offset,
                               transformador=lambda q, t, i: realcador.aplicar(q))
        gravar_json(a.saida, {"original": _avaliar(a.video, a), "realcado": r, "modelo": realcador.procedencia})
    elif a.experimento == "exposicao":
        from cardiocam.pesquisa.exposicao import ControleExposicaoPele, LimitesExposicao
        from cardiocam.fontes.webcam import abrir_webcam
        from cardiocam.visao.detector_face import DetectorHaar
        from cardiocam.visao.pele import mascara_pele
        abertura = abrir_webcam(indice=a.camera)
        if abertura.falhou:
            raise abertura.erro
        fonte = abertura.desempacotar()
        if not fonte.ajustes_travados.get("exposicao"):
            fonte.fechar()
            raise ValueError("O driver não confirmou exposição manual; calibração recusada.")
        controle = ControleExposicaoPele(LimitesExposicao(a.minimo, a.maximo, a.incremento, a.sentido))
        registros, detector, inicio = [], DetectorHaar(), None
        try:
            for imagem, t in fonte.quadros():
                inicio = t if inicio is None else inicio
                if t-inicio >= a.duracao:
                    break
                rosto = detector.detectar(imagem)
                if rosto.ok:
                    recorte = rosto.desempacotar().recortar(imagem)
                    pixels = recorte[mascara_pele(recorte, usar_luminancia=False)]
                    if len(pixels) >= 50:
                        ajuste = controle.ajustar(fonte._captura, pixels)
                        registros.append({"instante_s": t-inicio, **asdict(ajuste)})
                        if ajuste.estavel:
                            break
        finally:
            fonte.fechar()
        gravar_json(a.saida, {"experimental": True, "ajustes": registros})
        print(f"Calibração de exposição gravada em {a.saida}.")
    return 0


def executar(a):
    try:
        return _executar(a)
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, cv2.error, ErroCardiocam) as erro:
        print(f"Experimento não concluído: {erro}", file=sys.stderr)
        return 1


def _analise(p):
    from cardiocam.pesquisa.experimento import METODOS
    p.add_argument("video")
    p.add_argument("--saida", required=True, help="arquivo novo, ou pasta para compressão")
    p.add_argument("--janela", type=float, default=10)
    p.add_argument("--passo", type=float, default=1)
    p.add_argument("--grade", type=int, default=3)
    p.add_argument("--metodos", nargs="+", choices=METODOS, default=["pos", "chrom", "lgi", "omit", "pbv_adaptativo", "ssr"])
    p.add_argument("--area", type=int, nargs=4, metavar=("X", "Y", "LARGURA", "ALTURA"), help="recorte explícito fixo, sem identificação de pessoa")
    p.add_argument("--estabilizar", action="store_true")
    p.add_argument("--ancorar-olhos", action="store_true", help="alinha centros observados e recusa inclinação excessiva")
    p.add_argument("--fotometria", choices=("nenhum", "retinex", "crominancia"), default="nenhum")
    p.add_argument("--corrigir-fundo", action="store_true")
    p.add_argument("--suavizacao", type=float, default=0)
    _referencia_opcoes(p)


def _referencia_opcoes(p):
    p.add_argument("--referencia", help="CSV instante_s,bpm derivado de ECG/PPG sincronizado")
    p.add_argument("--offset", type=float, default=0)
    p.add_argument("--lacuna-referencia", type=float, default=2)


def _resolucao(texto):
    try:
        numeros = tuple(map(int, texto.lower().split("x")))
        if len(numeros) != 2 or min(numeros) < 16 or any(n % 2 for n in numeros):
            raise ValueError
        return numeros
    except ValueError as erro:
        raise argparse.ArgumentTypeError("Use LARGURAxALTURA com dimensões pares de ao menos 16 pixels.") from erro


def adicionar_comandos(subcomandos):
    pesquisa = subcomandos.add_parser("pesquisa", help="experimentos optativos com vídeo, modelos e compressão")
    s = pesquisa.add_subparsers(dest="experimento", required=True)
    video = s.add_parser("video", help="compara métodos, regiões e estimadores")
    _analise(video)
    compressao = s.add_parser("compressao", help="codifica e avalia variantes reais com FFmpeg")
    _analise(compressao)
    compressao.add_argument("--codecs", nargs="+", choices=("h264", "h265", "vp9"), default=["h264", "h265", "vp9"])
    compressao.add_argument("--bitrates", nargs="+", type=int, default=[400, 1000])
    compressao.add_argument("--resolucoes", nargs="+", type=_resolucao, default=[(320, 240)])
    compressao.add_argument("--perdas", nargs="+", type=int, default=[0])
    ablacao = s.add_parser("ablacao", help="compara original e perturbações reproduzíveis")
    _analise(ablacao)
    for nome, padrao in (("movimento", 0), ("iluminacao", 0), ("frequencia", .2), ("ruido", 0)):
        ablacao.add_argument("--"+nome, type=float, default=padrao)
    ablacao.add_argument("--congelar", type=int, default=0)
    ablacao.add_argument("--semente", type=int, default=0)
    realcar = s.add_parser("realcar", help="compara original e realçador ONNX licenciado")
    _analise(realcar)
    realcar.add_argument("--pesos", required=True, help="manifesto com SHA-256 e licença")
    recalibrar = s.add_parser("recalibrar", help="ajusta qualidade com referência e partições por participante")
    recalibrar.add_argument("manifesto")
    recalibrar.add_argument("--saida", required=True)
    recalibrar.add_argument("--cobertura", type=float, default=.5)
    recalibrar.add_argument("--erro-alvo", type=float, default=2)
    treino = s.add_parser("treinar-rede", help="treina rede local com onda PPG sincronizada")
    treino.add_argument("manifesto")
    treino.add_argument("--arquitetura", choices=("deepphys", "physnet", "efficientphys"), required=True)
    treino.add_argument("--saida", required=True)
    treino.add_argument("--epocas", type=int, default=10)
    treino.add_argument("--taxa", type=float, default=.001)
    treino.add_argument("--semente", type=int, default=0)
    rede = s.add_parser("rede", help="avalia pesos locais verificados, sem download automático")
    rede.add_argument("video")
    rede.add_argument("--pesos", required=True)
    rede.add_argument("--saida", required=True)
    rede.add_argument("--janela", type=float, default=10)
    _referencia_opcoes(rede)
    modalidades = s.add_parser("modalidades", help="séries de pupila e movimento de cabeça")
    modalidades.add_argument("video")
    modalidades.add_argument("--saida", required=True)
    modalidades.add_argument("--janela", type=float, default=10)
    exposicao = s.add_parser("exposicao", help="calibra exposição de pele antes de iniciar medição")
    exposicao.add_argument("--camera", type=int, default=0)
    exposicao.add_argument("--minimo", type=float, required=True)
    exposicao.add_argument("--maximo", type=float, required=True)
    exposicao.add_argument("--incremento", type=float, required=True)
    exposicao.add_argument("--sentido", type=int, choices=(-1, 1), default=1)
    exposicao.add_argument("--duracao", type=float, default=30)
    exposicao.add_argument("--saida", required=True)
    pesquisa.set_defaults(funcao=executar)
