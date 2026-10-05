"""Confere a documentacao de IC antes de ela ir para o comite.

Documento que vai para comite de etica e lido com atencao, e erro de acentuacao
ou link quebrado custa credibilidade justamente onde ela importa. Este script
confere o que da para conferir por maquina:

1. travessao, que e regra do projeto nao usar;
2. espaco duplo e espaco no fim da linha, que o Markdown as vezes transforma em
   quebra de linha involuntaria;
3. palavra comum escrita sem acento, por lista fechada;
4. link interno apontando para arquivo que nao existe;
5. caractere de codificacao errada, o tipico "Ã§" de arquivo lido como Latin-1;
6. tabela com numero de colunas inconsistente entre linhas;
7. chave de preenchimento `{...}` sem fechar;
8. cabecalho fora de ordem, pulando nivel.

O que ele NAO confere, e vale dizer: concordancia, regencia, pontuacao e
sentido. Para isso nao existe atalho de maquina, e o texto foi revisado a mao.

Uso:
    python validar_documentos.py
    python validar_documentos.py --corrigir   # arruma espaco e travessao
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

PASTA = Path(__file__).resolve().parent

# Palavras que aparecem muito neste material e que erram acento com facilidade.
# A chave e a forma errada; o valor, a certa. Lista fechada de proposito: um
# corretor generico daria falso positivo em nome proprio e em termo tecnico.
ACENTOS = {
    "etica": "ética",
    "comite": "comité (ou comitê)",
    "pesquisa cientifica": "pesquisa científica",
    "cientifica": "científica",
    "cientifico": "científico",
    "frequencia": "frequência",
    "cardiaca": "cardíaca",
    "cardiaco": "cardíaco",
    "orientacao": "orientação",
    "submissao": "submissão",
    "aprovacao": "aprovação",
    "participacao": "participação",
    "identificacao": "identificação",
    "informacao": "informação",
    "iluminacao": "iluminação",
    "variacao": "variação",
    "medicao": "medição",
    "deteccao": "detecção",
    "regiao": "região",
    "relatorio": "relatório",
    "cronograma de 12 meses": None,  # só para não ficar vazio, ignorado
    "voluntaria": "voluntária",
    "obrigatoria": "obrigatória",
    "necessaria": "necessária",
    "proprio": "próprio",
    "propria": "própria",
    "codigo": "código",
    "video": "vídeo",
    "numero": "número",
    "analise": "análise",
    "metodo": "método",
    "hipotese": "hipótese",
    "estatistica": "estatística",
    "automatico": "automático",
    "especifico": "específico",
    "tecnica": "técnica",
    "fisico": "físico",
    "fisica": "física",
    "optico": "óptico",
    "sanguineo": "sanguíneo",
    "possivel": "possível",
    "disponivel": "disponível",
    "responsavel": "responsável",
    "nivel": "nível",
    "util": "útil",
    "ultimo": "último",
    "proximo": "próximo",
    "maquina": "máquina",
    "pagina": "página",
    "ja ": "já ",
    "nao ": "não ",
    "sao ": "são ",
    "tambem": "também",
    "porem": "porém",
    "apos": "após",
    "atraves": "através",
    "ate ": "até ",
    "so ": "só ",
    "tres": "três",
    "seculo": "século",
}

# Formas erradas que não devem disparar quando fazem parte de algo legítimo.
# `etica` dentro de `cosmetica`, por exemplo; ou termo em inglês.
PERDOADOS = re.compile(
    r"(?i)\b("
    r"https?://\S+"              # endereço
    r"|[\w.-]+@[\w.-]+"          # e-mail
    r"|plataformabrasil\S*"
    r"|fapesp\S*"
    r"|unesp\S*"
    r")\b"
)

# Palavras funcionais que praticamente nao aparecem em portugues e aparecem
# muito em titulo de artigo em ingles.
#
# Servem para decidir que uma linha esta em ingles e, portanto, nao deve passar
# pelo corretor de acento. Sem isso, a bibliografia acusava 12 problemas, todos
# a palavra "video" dentro de titulo como "video-based physiological
# measurement", onde ela esta certa justamente por nao levar acento.
#
# O criterio e duas ocorrencias na mesma linha, e nao uma. Com uma so, "a",
# "e" e "using" apareceriam em frase portuguesa por coincidencia; com duas, o
# falso positivo fica raro e o falso negativo e aceitavel, porque pior do que
# deixar passar um titulo e acusar erro onde nao ha.
PALAVRAS_INGLES = frozenset({
    "the", "of", "for", "with", "using", "from", "and", "based", "through",
    "toward", "towards", "across", "into", "under", "via",
    "remote", "measurement", "measurements", "imaging", "signal", "signals",
    "video", "videos", "heart", "rate", "pulse", "skin", "tone", "tones",
    "motion", "robustness", "robust", "fairness", "bias", "biases",
    "deep", "learning", "networks", "network", "attention", "model", "models",
    "dataset", "datasets", "toolbox", "framework", "evaluation", "impact",
    "effects", "compression", "encoding", "subjects", "diverse", "ambient",
    "light", "color", "colour", "reflection", "components", "separation",
    "blind", "source", "principles", "algorithmic", "unsupervised",
    "segmentation", "tissue", "advanced", "method", "application", "analysis",
    "conference", "proceedings", "transactions", "journal", "letters",
    "available", "practicality", "validity", "types", "sun", "reactive",
})

# Minimo de palavras inglesas numa linha para considerar a linha inglesa.
LIMIAR_DE_INGLES = 2


def parece_ingles(texto: str) -> bool:
    """Decide se a linha esta em ingles, para nao corrigir acento nela."""
    palavras = re.findall(r"[a-z]+", texto.lower())
    encontradas = {p for p in palavras if p in PALAVRAS_INGLES}
    return len(encontradas) >= LIMIAR_DE_INGLES


def linhas_de_codigo(texto: str) -> set[int]:
    """Numeros de linha dentro de bloco de codigo ou de citacao de modelo.

    Dentro de bloco de codigo nao se corrige acento nem espaco: o conteudo e
    literal, e mexer nele muda o significado.
    """
    dentro = False
    marcadas: set[int] = set()
    for i, linha in enumerate(texto.splitlines(), start=1):
        if linha.lstrip().startswith("```"):
            dentro = not dentro
            marcadas.add(i)
            continue
        if dentro:
            marcadas.add(i)
    return marcadas


def conferir(caminho: Path, arquivos_da_pasta: set[str]) -> list[tuple[int, str, str]]:
    """Devolve (linha, categoria, detalhe) de cada problema encontrado."""
    bruto = caminho.read_bytes()
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        return [(0, "codificacao", "o arquivo nao esta em UTF-8")]

    achados: list[tuple[int, str, str]] = []
    protegidas = linhas_de_codigo(texto)
    linhas = texto.splitlines()

    if bruto.startswith(b"\xef\xbb\xbf"):
        achados.append((1, "codificacao", "o arquivo comeca com marca de ordem de byte"))

    # mojibake: sequencia tipica de UTF-8 lido como Latin-1
    for i, linha in enumerate(linhas, start=1):
        if re.search(r"Ã[\u0080-¿]|Â[\u0080-¿]", linha):
            achados.append((i, "codificacao", "parece texto UTF-8 lido como Latin-1"))

    nivel_anterior = 0
    for i, linha in enumerate(linhas, start=1):
        if i in protegidas:
            continue

        if "—" in linha:
            achados.append((i, "travessao", "travessao: usar virgula, dois pontos ou parenteses"))
        if "\t" in linha:
            achados.append((i, "espaco", "tabulacao no meio do texto"))
        if linha != linha.rstrip():
            achados.append((i, "espaco", "espaco sobrando no fim da linha"))

        # espaco duplo fora de tabela e fora de indentacao
        corpo = linha.lstrip()
        if "|" not in linha and re.search(r"\S {2,}\S", corpo):
            achados.append((i, "espaco", "dois ou mais espacos entre palavras"))

        # espaco antes de pontuacao
        if re.search(r"\s+[,.;:!?](\s|$)", linha):
            achados.append((i, "pontuacao", "espaco antes de sinal de pontuacao"))

        # chave de preenchimento sem fechar
        if linha.count("{") != linha.count("}"):
            achados.append((i, "preenchimento", "chave de preenchimento sem fechar"))

        # cabecalho pulando nivel
        cabecalho = re.match(r"^(#{1,6})\s", linha)
        if cabecalho:
            nivel = len(cabecalho.group(1))
            if nivel_anterior and nivel > nivel_anterior + 1:
                achados.append(
                    (i, "estrutura", f"cabecalho salta de nivel {nivel_anterior} para {nivel}")
                )
            nivel_anterior = nivel

        # link interno para arquivo que nao existe
        for alvo in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", linha):
            if alvo.startswith("http"):
                continue
            if alvo not in arquivos_da_pasta:
                achados.append((i, "link", f"link para arquivo inexistente: {alvo}"))

        # Acentuacao. A limpeza antes da busca e o que separa achado de ruido, e
        # as tres exclusoes abaixo sairam de falso positivo medido na primeira
        # execucao deste script sobre esta propria pasta:
        #
        # - alvo de link: `06-etica-plataforma-brasil.md` casava com "etica",
        #   e nome de arquivo nao leva acento;
        # - trecho entre crases: e codigo, e literal;
        # - **fronteira no fim da palavra**: sem ela, "apos" casava dentro de
        #   "apostar", "metodo" dentro de "metodologico" e "video" dentro de
        #   "videochamada". Era o defeito que mais gerava ruido, e o mais
        #   traicoeiro, porque cada achado parecia plausivel lido fora de
        #   contexto.
        limpa = PERDOADOS.sub(" ", linha)
        limpa = re.sub(r"\]\([^)]*\)", "] ", limpa)      # alvo de link
        limpa = re.sub(r"`[^`]*`", " ", limpa)           # codigo em linha
        if parece_ingles(limpa):
            continue
        minuscula = limpa.lower()
        for errada, certa in ACENTOS.items():
            if certa is None:
                continue
            # A forma com espaco no fim ja traz a propria fronteira.
            fim = r"" if errada.endswith(" ") else r"(?![\wÀ-ɏ])"
            padrao = rf"(?<![\wÀ-ɏ]){re.escape(errada)}{fim}"
            if re.search(padrao, minuscula):
                achados.append(
                    (i, "acento", f"'{errada.strip()}' deveria ser '{certa.strip()}'")
                )

    # linha em branco dupla no fim, e falta de quebra final
    if texto and not texto.endswith("\n"):
        achados.append((len(linhas), "espaco", "arquivo nao termina com quebra de linha"))
    if texto.endswith("\n\n\n"):
        achados.append((len(linhas), "espaco", "linhas em branco sobrando no fim"))

    # tabela com numero de colunas inconsistente
    achados.extend(_conferir_tabelas(linhas, protegidas))

    return sorted(set(achados))


def _conferir_tabelas(
    linhas: list[str], protegidas: set[int]
) -> list[tuple[int, str, str]]:
    """Linha de tabela com numero de colunas diferente do cabecalho.

    Tabela desalinhada em Markdown nao da erro: ela renderiza errado, com
    coluna faltando, e quem le o PDF ve um dado no lugar do outro.
    """
    achados: list[tuple[int, str, str]] = []
    colunas_esperadas: int | None = None
    linha_do_cabecalho = 0

    for i, linha in enumerate(linhas, start=1):
        if i in protegidas:
            continue
        crua = linha.strip()
        if not crua.startswith("|"):
            colunas_esperadas = None
            continue
        # conta separadores que nao estao escapados
        colunas = len(re.findall(r"(?<!\\)\|", crua)) - 1
        if colunas_esperadas is None:
            colunas_esperadas = colunas
            linha_do_cabecalho = i
            continue
        if re.fullmatch(r"\|[\s:|-]+\|", crua):
            if colunas != colunas_esperadas:
                achados.append(
                    (i, "tabela", f"separador com {colunas} colunas, cabecalho tem {colunas_esperadas}")
                )
            continue
        if colunas != colunas_esperadas:
            achados.append(
                (
                    i,
                    "tabela",
                    f"{colunas} colunas, mas o cabecalho da linha {linha_do_cabecalho} "
                    f"tem {colunas_esperadas}",
                )
            )
    return achados


def corrigir(caminho: Path) -> int:
    """Arruma o que da para arrumar sem risco: espaco e travessao.

    Acento NAO e corrigido automaticamente de proposito: a troca depende do
    contexto, e corretor automatico de acento erra em nome proprio e em citacao.
    """
    texto = caminho.read_text(encoding="utf-8")
    original = texto
    protegidas = linhas_de_codigo(texto)

    saida: list[str] = []
    for i, linha in enumerate(texto.splitlines(), start=1):
        if i in protegidas:
            saida.append(linha)
            continue
        nova = linha.replace("—", ",").replace("\t", "    ").rstrip()
        if "|" not in nova:
            nova = re.sub(r"(\S) {2,}(\S)", r"\1 \2", nova)
        nova = re.sub(r"\s+([,.;:!?])(\s|$)", r"\1\2", nova)
        saida.append(nova)

    texto = "\n".join(saida).rstrip("\n") + "\n"
    if texto != original:
        caminho.write_text(texto, encoding="utf-8")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrigir", action="store_true")
    argumentos = ap.parse_args()

    arquivos = sorted(PASTA.glob("*.md"))
    nomes = {a.name for a in arquivos}
    if not arquivos:
        print("nenhum documento encontrado")
        return 1

    if argumentos.corrigir:
        mexidos = sum(corrigir(a) for a in arquivos)
        print(f"{mexidos} arquivo(s) ajustado(s)\n")

    total = 0
    for arquivo in arquivos:
        achados = conferir(arquivo, nomes)
        if not achados:
            print(f"  ok   {arquivo.name}")
            continue
        total += len(achados)
        print(f"  {len(achados):>3}  {arquivo.name}")
        for linha, categoria, detalhe in achados[:25]:
            print(f"        linha {linha:>4}  [{categoria}] {detalhe}")
        if len(achados) > 25:
            print(f"        ... e mais {len(achados) - 25}")

    # estatistica de legibilidade, so informativa
    print()
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        linhas = texto.splitlines()
        longas = [i for i, l in enumerate(linhas, 1) if len(l) > 80 and "|" not in l
                  and "http" not in l]
        palavras = len(re.findall(r"\b[\wÀ-ɏ]+\b", texto))
        print(f"  {arquivo.name:<34} {palavras:>6} palavras   "
              f"{len(linhas):>4} linhas   {len(longas):>3} acima de 80 colunas")

    print(f"\n{total} problema(s) no total")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
