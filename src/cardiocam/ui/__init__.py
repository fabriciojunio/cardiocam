"""Interface: painel sobreposto ao vídeo e laço de execução."""

from cardiocam.ui.app import ResultadoSessao, executar, salvar_serie
from cardiocam.ui.hud import compor, construir_painel, desenhar_regioes
from cardiocam.ui.texto import ItemTexto, PincelTexto

__all__ = [
    "ItemTexto",
    "PincelTexto",
    "ResultadoSessao",
    "compor",
    "construir_painel",
    "desenhar_regioes",
    "executar",
    "salvar_serie",
]
