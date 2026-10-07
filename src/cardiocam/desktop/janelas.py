"""Lista as janelas abertas do Windows e diz onde cada uma está na tela.

Escrito em `ctypes` sobre a API do sistema, sem `pywin32`. A razão é a mesma que
levou o rastreador do navegador a ser escrito em vez de baixado: o que se precisa
aqui são cinco chamadas, e uma dependência de 10 MB para cinco chamadas é
dependência que se carrega no empacotamento, no `requirements` e na superfície de
segurança sem contrapartida.

Três detalhes do Windows que, ignorados, dão um retângulo errado em silêncio, que
é o pior tipo de erro aqui: a captura sai torta e nada avisa.

**O retângulo da janela não é o que se vê.** `GetWindowRect` devolve a área
incluindo a sombra que o compositor desenha em volta, que pode passar de dez
pixels por lado. Capturar por ele traz faixa do que está atrás da janela.
`DwmGetWindowAttribute` com `EXTENDED_FRAME_BOUNDS` devolve a borda visível de
verdade.

**Janela escondida não é janela minimizada.** Aplicativo da Loja fica "cloaked"
quando está em outra área de trabalho virtual ou suspenso: continua visível para
`IsWindowVisible`, tem título, tem retângulo, e não desenha nada. Sem conferir
isso, a lista enche de nomes que capturam preto.

**Escala de tela muda as coordenadas.** Em monitor a 125% ou 150%, um processo
que não declara conhecer DPI recebe coordenadas lógicas, enquanto a captura de
tela devolve pixels físicos. A conta não fecha, e a janela capturada aparece
deslocada e cortada. Por isso `declarar_ciencia_de_dpi` é chamada antes de
qualquer coisa.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

NO_WINDOWS = sys.platform == "win32"

# Borda visível da janela, sem a sombra do compositor.
DWMWA_EXTENDED_FRAME_BOUNDS = 9
# Janela que existe mas não está sendo desenhada (outra área de trabalho, app
# da Loja suspenso).
DWMWA_CLOAKED = 14
# Por monitor, versão 2: a forma moderna, que também acerta a barra de título.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# Janelas de sistema que aparecem na enumeração e nunca interessam.
TITULOS_IGNORADOS = frozenset(
    {
        "Program Manager",
        "Windows Input Experience",
        "Configurações",
        "Settings",
        "Microsoft Text Input Application",
    }
)

# Pedaço de janela pequeno demais para ter rosto mensurável dentro. O limiar sai
# do mesmo lugar que o da versão web: abaixo de cem pixels de largura de rosto a
# média espacial não tem pixels suficientes para tirar o pulso do ruído, e um
# rosto costuma ocupar um quinto da largura de uma janela de reunião.
LARGURA_MINIMA = 320
ALTURA_MINIMA = 240


@dataclass(frozen=True)
class JanelaDaTela:
    """Uma janela aberta, com a área que ela ocupa em pixels físicos."""

    identificador: int
    titulo: str
    x: int
    y: int
    largura: int
    altura: int

    @property
    def regiao(self) -> dict[str, int]:
        """No formato que a captura de tela espera."""
        return {"left": self.x, "top": self.y, "width": self.largura, "height": self.altura}

    def __str__(self) -> str:
        return f"{self.titulo} ({self.largura}x{self.altura})"


def declarar_ciencia_de_dpi() -> bool:
    """Diz ao Windows que este processo trabalha em pixels físicos.

    Precisa ser chamada **antes** de criar qualquer janela, e antes de ler
    qualquer retângulo. Depois disso o sistema ignora o pedido.

    Devolve se conseguiu. Em versão antiga do Windows a função moderna não
    existe, e aí a anterior serve; não existindo nenhuma, a tela não tem escala
    e não há o que declarar.
    """
    if not NO_WINDOWS:
        return False
    try:
        usuario = ctypes.windll.user32
        if hasattr(usuario, "SetProcessDpiAwarenessContext"):
            usuario.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            usuario.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
            if usuario.SetProcessDpiAwarenessContext(
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            ):
                return True
        # 2 é PROCESS_PER_MONITOR_DPI_AWARE, da API anterior.
        return bool(ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0)
    except (AttributeError, OSError):
        return False


def _esta_escondida(identificador: int) -> bool:
    valor = ctypes.c_int(0)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(identificador),
            ctypes.c_uint(DWMWA_CLOAKED),
            ctypes.byref(valor),
            ctypes.sizeof(valor),
        )
    except (AttributeError, OSError):
        return False
    return valor.value != 0


def _borda_visivel(identificador: int) -> tuple[int, int, int, int] | None:
    """Retângulo sem a sombra do compositor, em pixels físicos."""
    retangulo = wintypes.RECT()
    try:
        resultado = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(identificador),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(retangulo),
            ctypes.sizeof(retangulo),
        )
    except (AttributeError, OSError):
        resultado = 1
    if resultado != 0:
        # Sem o compositor, resta o retângulo com sombra. É pior e não é inútil.
        if not ctypes.windll.user32.GetWindowRect(
            wintypes.HWND(identificador), ctypes.byref(retangulo)
        ):
            return None
    return (
        int(retangulo.left),
        int(retangulo.top),
        int(retangulo.right - retangulo.left),
        int(retangulo.bottom - retangulo.top),
    )


def _titulo(identificador: int) -> str:
    comprimento = ctypes.windll.user32.GetWindowTextLengthW(wintypes.HWND(identificador))
    if comprimento <= 0:
        return ""
    reservado = ctypes.create_unicode_buffer(comprimento + 1)
    ctypes.windll.user32.GetWindowTextW(
        wintypes.HWND(identificador), reservado, comprimento + 1
    )
    return reservado.value


def listar_janelas(
    largura_minima: int = LARGURA_MINIMA, altura_minima: int = ALTURA_MINIMA
) -> list[JanelaDaTela]:
    """Janelas visíveis, com título e tamanho suficiente para ter rosto dentro.

    A ordem é a que o sistema devolve, que é a ordem de empilhamento: a janela
    em primeiro plano vem primeiro. Isso é útil e é de propósito, porque a
    reunião que a pessoa quer medir costuma ser justamente a que está na frente.
    """
    if not NO_WINDOWS:
        return []

    encontradas: list[JanelaDaTela] = []
    assinatura = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visitar(identificador, _parametro):  # type: ignore[no-untyped-def]
        numero = int(identificador)
        if not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(numero)):
            return True
        if ctypes.windll.user32.IsIconic(wintypes.HWND(numero)):
            return True
        if _esta_escondida(numero):
            return True
        titulo = _titulo(numero)
        if not titulo or titulo in TITULOS_IGNORADOS:
            return True
        borda = _borda_visivel(numero)
        if borda is None:
            return True
        x, y, largura, altura = borda
        if largura < largura_minima or altura < altura_minima:
            return True
        encontradas.append(JanelaDaTela(numero, titulo, x, y, largura, altura))
        return True

    ctypes.windll.user32.EnumWindows(assinatura(visitar), 0)
    return encontradas


# Nomes que identificam uma janela de reunião. A lista cobre o que é comum no
# Brasil; o título dessas janelas sempre carrega o nome do programa, porque é
# assim que a barra de tarefas as distingue.
PROGRAMAS_DE_REUNIAO = (
    "teams",
    "meet",
    "zoom",
    "whatsapp",
    "discord",
    "webex",
    "hangouts",
    "skype",
    "jitsi",
    "chime",
)


def provavel_reuniao(janelas: list[JanelaDaTela] | None = None) -> JanelaDaTela | None:
    """A janela mais provável de ser a reunião, se houver uma.

    Existe por uma observação de uso: durante a reunião a câmera **já está
    aberta pelo programa da reunião**, e pedir a mesma câmera disputa o
    dispositivo com ele. A imagem que interessa, inclusive a do próprio rosto,
    já está na tela. Então o padrão certo é ler a janela, e não abrir a câmera.

    A ordem da enumeração é a de empilhamento, então a primeira que casar é a
    que está mais à frente, que é a que a pessoa está olhando.
    """
    for janela in janelas if janelas is not None else listar_janelas():
        titulo = janela.titulo.lower()
        if any(programa in titulo for programa in PROGRAMAS_DE_REUNIAO):
            return janela
    return None


def reler(janela: JanelaDaTela) -> JanelaDaTela | None:
    """Atualiza a posição de uma janela, que o usuário pode ter movido.

    Devolve `None` quando ela foi fechada ou minimizada. Capturar o retângulo
    antigo nesse caso leria o que ficou por baixo, e a medição continuaria
    rodando sobre outra coisa sem nada indicar isso.
    """
    if not NO_WINDOWS:
        return None
    alvo = wintypes.HWND(janela.identificador)
    if not ctypes.windll.user32.IsWindow(alvo):
        return None
    if not ctypes.windll.user32.IsWindowVisible(alvo):
        return None
    if ctypes.windll.user32.IsIconic(alvo):
        return None
    borda = _borda_visivel(janela.identificador)
    if borda is None:
        return None
    x, y, largura, altura = borda
    if largura <= 0 or altura <= 0:
        return None
    return JanelaDaTela(janela.identificador, _titulo(janela.identificador) or janela.titulo,
                        x, y, largura, altura)
