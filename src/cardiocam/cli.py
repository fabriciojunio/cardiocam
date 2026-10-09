"""Linha de comando do Cardiocam."""

from __future__ import annotations

import argparse
import sys

import numpy as np

from cardiocam import __version__
from cardiocam.avaliacao import (
    avaliar,
    cenarios_padrao,
    formatar_por_cenario,
    formatar_tabela,
    por_cenario,
)
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import BandaCardiaca
from cardiocam.fontes.arquivo import abrir_arquivo
from cardiocam.qualidade.persistencia import CAMINHO_PADRAO as CAMINHO_DO_MODELO
from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao
from cardiocam.fontes.webcam import abrir_webcam
from cardiocam.pipeline.analisador import RelatorioSessao, analisar_fonte
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS
from cardiocam.ui.app import executar, salvar_serie


def _configuracao(argumentos: argparse.Namespace) -> ConfiguracaoAnalise:
    return ConfiguracaoAnalise(
        janela_s=argumentos.janela,
        passo_s=argumentos.passo,
        banda=BandaCardiaca(argumentos.bpm_minimo / 60.0, argumentos.bpm_maximo / 60.0),
        algoritmo=argumentos.algoritmo,
    )


def _resumir(relatorio: RelatorioSessao) -> str:
    if relatorio.total_estimativas == 0:
        return (
            "Nenhuma janela produziu estimativa aproveitável.\n"
            "Causas comuns: rosto fora do quadro, iluminação insuficiente ou "
            "vídeo mais curto que a janela de análise."
        )
    linhas = [
        f"Frequência cardíaca: {relatorio.bpm_mediano:.1f} bpm",
        f"Dispersão entre janelas: {relatorio.desvio_bpm:.2f} bpm",
        f"Relação sinal-ruído mediana: {relatorio.snr_mediano_db:.1f} dB",
        f"Confiança predominante: {relatorio.confianca_predominante.value}",
        f"Janelas analisadas: {relatorio.total_estimativas}",
        f"Quadros com rosto: {relatorio.taxa_deteccao * 100:.0f}%",
    ]
    return "\n".join(linhas)


def _comando_ao_vivo(argumentos: argparse.Namespace) -> int:
    abertura = abrir_webcam(
        indice=argumentos.camera,
        largura=argumentos.largura,
        altura=argumentos.altura,
    )
    if abertura.falhou:
        print(f"Erro: {abertura.erro}", file=sys.stderr)
        return 1

    fonte = abertura.desempacotar()
    print(
        f"Câmera {argumentos.camera} aberta a {fonte.fps:.0f} quadros por segundo "
        f"pelo {fonte.backend}."
    )

    travados = fonte.ajustes_travados
    if travados.get("exposicao") or travados.get("balanco_de_branco"):
        quais = [
            nome
            for nome, chave in (("exposição", "exposicao"), ("balanço de branco", "balanco_de_branco"))
            if travados.get(chave)
        ]
        print(f"Ajuste automático de {' e de '.join(quais)} desligado.")
    else:
        print(
            "Esta câmera não permite desligar exposição e balanço de branco\n"
            "automáticos. Eles trabalham contra a medição, mas a correção por\n"
            "referência de fundo compensa boa parte disso."
        )

    print(
        "Fique de frente para a câmera, bem iluminado e o mais parado possível.\n"
        "A primeira leitura aparece depois de encher a janela de análise."
    )
    sessao = executar(fonte, _configuracao(argumentos))
    print()
    print(_resumir(sessao.relatorio))
    print(f"Desempenho: {sessao.quadros_por_segundo:.1f} quadros por segundo.")

    if argumentos.salvar:
        salvar_serie(argumentos.salvar, sessao.relatorio)
        print(f"Série gravada em {argumentos.salvar}.")
    return 0


def _comando_arquivo(argumentos: argparse.Namespace) -> int:
    abertura = abrir_arquivo(argumentos.caminho)
    if abertura.falhou:
        print(f"Erro: {abertura.erro}", file=sys.stderr)
        return 1

    fonte = abertura.desempacotar()
    print(f"Analisando {argumentos.caminho} a {fonte.fps:.1f} quadros por segundo.")

    if argumentos.mostrar:
        sessao = executar(fonte, _configuracao(argumentos))
        relatorio = sessao.relatorio
    else:
        relatorio = analisar_fonte(fonte, _configuracao(argumentos))
        fonte.fechar()

    print()
    print(_resumir(relatorio))
    if argumentos.salvar:
        salvar_serie(argumentos.salvar, relatorio)
        print(f"Série gravada em {argumentos.salvar}.")
    return 0


def _comando_simular(argumentos: argparse.Namespace) -> int:
    parametros = ParametrosSimulacao(
        bpm=argumentos.bpm,
        duracao_s=argumentos.duracao,
        fps=argumentos.fps,
        amplitude_pulso=argumentos.amplitude,
        ruido_sensor=argumentos.ruido,
        deriva_iluminacao=argumentos.deriva,
        movimento_px=argumentos.movimento,
    )
    fonte = FonteSintetica(parametros)
    print(
        f"Simulando {argumentos.duracao:.0f} s de vídeo com pulso de "
        f"{argumentos.bpm:.0f} bpm."
    )

    if argumentos.mostrar:
        sessao = executar(fonte, _configuracao(argumentos))
        relatorio = sessao.relatorio
    else:
        relatorio = analisar_fonte(fonte, _configuracao(argumentos))

    print()
    print(_resumir(relatorio))
    if relatorio.total_estimativas:
        erro = abs(relatorio.bpm_mediano - argumentos.bpm)
        print(f"Valor verdadeiro: {argumentos.bpm:.1f} bpm")
        print(f"Erro absoluto: {erro:.2f} bpm")
    return 0


def _comando_tela(argumentos: argparse.Namespace) -> int:
    from cardiocam.fontes.tela import abrir_tela

    abertura = abrir_tela(
        x=argumentos.x,
        y=argumentos.y,
        largura=argumentos.largura,
        altura=argumentos.altura,
        fps_alvo=argumentos.fps,
    )
    if abertura.falhou:
        print(f"Erro: {abertura.erro}", file=sys.stderr)
        return 1

    print(
        "Capturando a região "
        f"{argumentos.largura}x{argumentos.altura} a partir de "
        f"({argumentos.x}, {argumentos.y}).\n"
        "Atenção: medir sinal fisiológico de outra pessoa exige consentimento "
        "explícito dela.\n"
        "O sinal vindo de videochamada passou por compressão com perdas, então "
        "espere precisão menor que a da câmera local."
    )
    sessao = executar(abertura.desempacotar(), _configuracao(argumentos))
    print()
    print(_resumir(sessao.relatorio))
    if argumentos.salvar:
        salvar_serie(argumentos.salvar, sessao.relatorio)
        print(f"Série gravada em {argumentos.salvar}.")
    return 0


def _comando_diagnostico(argumentos: argparse.Namespace) -> int:
    from cardiocam.avaliacao.diagnostico import (
        avaliar_captura,
        capturar,
        formatar_relatorio,
        gravar_csv,
    )

    if argumentos.arquivo:
        abertura = abrir_arquivo(argumentos.arquivo)
    else:
        abertura = abrir_webcam(indice=argumentos.camera)
    if abertura.falhou:
        print(f"Erro: {abertura.erro}", file=sys.stderr)
        return 1

    print(
        f"Capturando {argumentos.duracao:.0f} segundos para diagnóstico.\n"
        "Fique de frente para a câmera, com luz vindo da frente, e o mais parado\n"
        "possível. Se der, apoie a cabeça em algo firme.\n"
        "Nenhuma imagem é gravada, apenas médias de cor.\n"
    )

    ultimo = [-1]

    def progresso(fracao: float) -> None:
        passo = int(fracao * 10)
        if passo != ultimo[0]:
            ultimo[0] = passo
            print(f"  {fracao * 100:3.0f}%", end="\r", flush=True)

    captura = capturar(abertura.desempacotar(), argumentos.duracao, progresso)
    print("  100%")
    print()

    if captura.total < 64:
        print(
            "Quadros de menos para diagnosticar. O rosto precisa ficar enquadrado\n"
            "durante a captura inteira.",
            file=sys.stderr,
        )
        return 1

    resultados = avaliar_captura(captura, janela_s=argumentos.janela)
    print(formatar_relatorio(captura, resultados))

    if argumentos.saida:
        gravar_csv(captura, argumentos.saida)
        print(f"\nSéries gravadas em {argumentos.saida}.")
    return 0


def _comando_avaliar(argumentos: argparse.Namespace) -> int:
    cenarios = cenarios_padrao()
    print(
        f"Avaliando {len(ALGORITMOS_DISPONIVEIS)} algoritmos em {len(cenarios)} "
        f"cenários{' com vídeo completo' if argumentos.video else ''}.\n"
    )

    resultados = avaliar(cenarios, usar_video=argumentos.video)
    print("## Desempenho geral\n")
    print(formatar_tabela(resultados))

    if not argumentos.video:
        print("\n## Erro médio por cenário (bpm)\n")
        print(formatar_por_cenario(por_cenario(cenarios)))

    if argumentos.saida:
        with open(argumentos.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write("# Avaliação dos algoritmos\n\n")
            arquivo.write("## Desempenho geral\n\n")
            arquivo.write(formatar_tabela(resultados) + "\n")
            if not argumentos.video:
                arquivo.write("\n## Erro médio por cenário (bpm)\n\n")
                arquivo.write(formatar_por_cenario(por_cenario(cenarios)) + "\n")
        print(f"\nRelatório gravado em {argumentos.saida}.")
    return 0


# Quebra de linha como constante: este arquivo e montado por script e um
# literal de escape dentro de f-string ja foi corrompido uma vez.
NOVA_LINHA = chr(10)


def _comando_qualidade(argumentos: argparse.Namespace) -> int:
    """Treina o modelo de abstenção e imprime a curva de erro contra cobertura.

    É o comando que materializa a hipótese H4: medir se recusar janela ruim
    compra mais erro do que qualquer correção de sinal, e a que custo de
    cobertura.
    """
    from cardiocam.avaliacao.benchmark import cenarios_de_robustez
    from cardiocam.qualidade.coleta import coletar
    from cardiocam.qualidade.coleta_de_video import coletar_de_video
    from cardiocam.qualidade.treino import treinar

    cenarios = cenarios_padrao() + cenarios_de_robustez()
    caminho = "vídeo, quadro a quadro" if argumentos.com_video else "analítico"
    print(
        f"Coletando janelas de {len(cenarios)} cenários "
        f"x {len(ALGORITMOS_DISPONIVEIS)} algoritmos pelo caminho {caminho}. "
        f"Isso roda o pipeline inteiro e demora." + NOVA_LINHA
    )
    coletora = coletar_de_video if argumentos.com_video else coletar
    amostras, falhas = coletora(cenarios, agrupar_por=argumentos.agrupar_por)
    print(
        f"{len(amostras)} janelas com estimativa, "
        f"{falhas} recusadas pelo pipeline." + NOVA_LINHA
    )

    relatorio = treinar(
        amostras,
        tolerancia_bpm=argumentos.tolerancia,
        cobertura_minima=argumentos.cobertura_minima,
        erro_alvo_bpm=argumentos.erro_alvo,
    )

    print("## Resumo" + NOVA_LINHA)
    print(relatorio.resumo())
    print(NOVA_LINHA + "## Peso de cada característica" + NOVA_LINHA)
    print("| Característica | Peso | Desvio | Sustentado pelo dado |")
    print("| --- | ---: | ---: | :---: |")
    regressao = relatorio.modelo.regressao
    for nome, peso in regressao.pesos.items():
        desvio = regressao.desvios_dos_pesos[nome]
        sustenta = "sim" if abs(peso) > desvio else "não"
        print(f"| {nome} | {peso:+.3f} | {desvio:.3f} | {sustenta} |")
    print(NOVA_LINHA + "## Curva de erro contra cobertura" + NOVA_LINHA)
    print(relatorio.curva_no_teste.tabela())
    print(NOVA_LINHA + "## Diagrama de confiabilidade" + NOVA_LINHA)
    print(relatorio.calibracao_no_teste.tabela())

    if argumentos.gravar_modelo:
        from cardiocam.qualidade.persistencia import Procedencia, agora_em_texto, salvar

        destino = salvar(
            relatorio.modelo,
            Procedencia(
                treinado_em=agora_em_texto(),
                janelas=len(amostras),
                bateria=f"{len(cenarios)} cenários, caminho {caminho}",
                erro_respondendo_sempre=float(relatorio.curva_no_teste.erro_sem_abstencao),
                erro_com_abstencao=float(relatorio.ponto_adotado.erro_medio),
                cobertura=float(relatorio.ponto_adotado.cobertura),
                observacao=(
                    "Treinado em bateria sintética. O modo de falha medido é o "
                    "artefato inédito: com um tipo que não estava no treino, o "
                    "ganho some em cobertura razoável."
                ),
            ),
            argumentos.gravar_modelo,
        )
        print(NOVA_LINHA + f"Modelo gravado em {destino}.")

    if argumentos.saida:
        partes = [
            "# Abstenção com incerteza calibrada",
            "## Resumo",
            relatorio.resumo(),
            "## Curva de erro contra cobertura",
            relatorio.curva_no_teste.tabela(),
            "## Diagrama de confiabilidade",
            relatorio.calibracao_no_teste.tabela(),
        ]
        texto = (NOVA_LINHA * 2).join(partes) + NOVA_LINHA
        with open(argumentos.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
        print(NOVA_LINHA + f"Relatório gravado em {argumentos.saida}.")
    return 0


def _adicionar_opcoes_analise(analisador: argparse.ArgumentParser) -> None:
    analisador.add_argument(
        "--algoritmo",
        choices=ALGORITMOS_DISPONIVEIS,
        default="pos",
        help="método de extração do pulso (padrão: pos)",
    )
    # Janela de 25 s, escolhida por medição em rosto real e não por estimativa.
    # Numa captura de 45 segundos com webcam sem controle de exposição, passar
    # de 15 para 25 s derrubou a dispersão entre janelas de 8,7 para 3,2 bpm. O
    # custo é a primeira leitura demorar 25 s para aparecer e a estimativa
    # reagir mais devagar a uma mudança de frequência, o que é aceitável para
    # medir alguém em repouso.
    analisador.add_argument(
        "--janela", type=float, default=25.0, help="tamanho da janela em segundos"
    )
    analisador.add_argument(
        "--passo", type=float, default=1.0, help="intervalo entre estimativas"
    )
    # A banda começa em 45 e não em 42 bpm de propósito: logo acima de zero
    # sobra energia de deriva de iluminação que o detrend não removeu por
    # completo, e ela compete com o pulso quando o sinal está fraco.
    analisador.add_argument(
        "--bpm-minimo", type=float, default=45.0, help="limite inferior da banda"
    )
    analisador.add_argument(
        "--bpm-maximo", type=float, default=200.0, help="limite superior da banda"
    )
    analisador.add_argument("--salvar", help="grava as estimativas em CSV")


def construir_analisador() -> argparse.ArgumentParser:
    """Monta o analisador de argumentos completo."""
    analisador = argparse.ArgumentParser(
        prog="cardiocam",
        description=(
            "Mede a frequência cardíaca sem contato, a partir da variação de cor "
            "da pele captada por uma câmera comum."
        ),
    )
    analisador.add_argument("--versao", action="version", version=f"cardiocam {__version__}")
    subcomandos = analisador.add_subparsers(dest="comando", required=True)

    ao_vivo = subcomandos.add_parser("ao-vivo", help="mede pela webcam em tempo real")
    ao_vivo.add_argument("--camera", type=int, default=0, help="índice da câmera")
    ao_vivo.add_argument("--largura", type=int, default=640)
    ao_vivo.add_argument("--altura", type=int, default=480)
    _adicionar_opcoes_analise(ao_vivo)
    ao_vivo.set_defaults(funcao=_comando_ao_vivo)

    arquivo = subcomandos.add_parser("arquivo", help="analisa um vídeo gravado")
    arquivo.add_argument("caminho", help="caminho do arquivo de vídeo")
    arquivo.add_argument(
        "--mostrar", action="store_true", help="exibe a janela durante a análise"
    )
    _adicionar_opcoes_analise(arquivo)
    arquivo.set_defaults(funcao=_comando_arquivo)

    simular = subcomandos.add_parser(
        "simular", help="gera um vídeo sintético com pulso conhecido e o analisa"
    )
    simular.add_argument("--bpm", type=float, default=72.0)
    simular.add_argument("--duracao", type=float, default=20.0)
    simular.add_argument("--fps", type=float, default=30.0)
    simular.add_argument("--amplitude", type=float, default=0.02)
    simular.add_argument("--ruido", type=float, default=2.0)
    simular.add_argument("--deriva", type=float, default=0.0)
    simular.add_argument("--movimento", type=float, default=0.0)
    simular.add_argument("--mostrar", action="store_true")
    _adicionar_opcoes_analise(simular)
    # A demonstração padrão dura 20 s e precisa conter uma janela completa.
    simular.set_defaults(funcao=_comando_simular, janela=10.0)

    tela = subcomandos.add_parser(
        "tela",
        help="mede a partir de uma região da tela, como uma janela de videochamada",
    )
    tela.add_argument("--x", type=int, default=0, help="canto esquerdo da região")
    tela.add_argument("--y", type=int, default=0, help="topo da região")
    tela.add_argument("--largura", type=int, default=640)
    tela.add_argument("--altura", type=int, default=480)
    tela.add_argument("--fps", type=float, default=30.0)
    _adicionar_opcoes_analise(tela)
    tela.set_defaults(funcao=_comando_tela)

    diagnostico = subcomandos.add_parser(
        "diagnostico",
        help="captura uma sessão real e compara configurações sobre os mesmos quadros",
    )
    diagnostico.add_argument("--camera", type=int, default=0)
    diagnostico.add_argument("--arquivo", help="usa um vídeo em vez da câmera")
    diagnostico.add_argument("--duracao", type=float, default=45.0)
    diagnostico.add_argument("--janela", type=float, default=15.0)
    diagnostico.add_argument(
        "--saida", default="diagnostico.csv", help="onde gravar as séries"
    )
    diagnostico.set_defaults(funcao=_comando_diagnostico)

    avaliacao = subcomandos.add_parser(
        "avaliar", help="compara os algoritmos e imprime as métricas"
    )
    avaliacao.add_argument(
        "--video", action="store_true", help="usa o pipeline completo com imagem"
    )
    avaliacao.add_argument("--saida", help="grava o relatório em Markdown")
    avaliacao.set_defaults(funcao=_comando_avaliar)

    qualidade = subcomandos.add_parser(
        "qualidade",
        help="treina o modelo de abstenção e mede erro contra cobertura",
    )
    qualidade.add_argument(
        "--tolerancia",
        type=float,
        default=3.0,
        help="erro em bpm abaixo do qual a janela conta como acerto",
    )
    qualidade.add_argument(
        "--cobertura-minima",
        type=float,
        default=0.4,
        dest="cobertura_minima",
        help="fração mínima de janelas em que o sistema aceita responder",
    )
    qualidade.add_argument(
        "--erro-alvo",
        type=float,
        default=2.0,
        dest="erro_alvo",
        help="erro médio em bpm que se quer atingir entre as janelas aceitas",
    )
    qualidade.add_argument(
        "--agrupar-por",
        choices=("condicao", "frequencia"),
        default="condicao",
        dest="agrupar_por",
        help="o que não pode aparecer em duas partições ao mesmo tempo",
    )
    qualidade.add_argument(
        "--com-video",
        action="store_true",
        help=(
            "coleta percorrendo o caminho completo, com imagem, em vez do "
            "analítico. Quatro das onze características só variam assim, e são "
            "justamente as que descrevem os modos de falha que o espectro não "
            "vê. Custa duas ordens de grandeza mais caro."
        ),
    )
    qualidade.add_argument(
        "--gravar-modelo",
        nargs="?",
        const=str(CAMINHO_DO_MODELO),
        help=(
            "grava o modelo treinado em JSON, para o aplicativo carregar. Sem "
            "caminho, grava dentro do pacote, que é de onde o executável o lê."
        ),
    )
    qualidade.add_argument("--saida", help="grava o relatório em Markdown")
    qualidade.set_defaults(funcao=_comando_qualidade)

    return analisador


def main(argumentos: list[str] | None = None) -> int:
    """Ponto de entrada."""
    analisador = construir_analisador()
    opcoes = analisador.parse_args(argumentos)
    try:
        return int(opcoes.funcao(opcoes))
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
