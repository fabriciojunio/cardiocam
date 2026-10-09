"""Compatibilidade da captura com as versões declaradas do mss."""


def criar_captura(modulo=None):
    if modulo is None:
        import mss as modulo
    fabrica = getattr(modulo, "MSS", None) or modulo.mss
    return fabrica()
