"""Versões 9 e 10 podem oferecer fábricas com nomes diferentes."""

from types import SimpleNamespace

from cardiocam.fontes.captura_tela import criar_captura


def test_fabrica_antiga_e_suportada():
    captura = object()
    assert criar_captura(SimpleNamespace(mss=lambda: captura)) is captura


def test_fabrica_nova_e_preferida():
    captura = object()
    def antiga():
        raise AssertionError("A fábrica antiga não deve ser chamada nesta versão.")
    assert criar_captura(SimpleNamespace(MSS=lambda: captura, mss=antiga)) is captura


def test_modulo_somente_com_nova_fabrica_funciona():
    captura = object()
    assert criar_captura(SimpleNamespace(MSS=lambda: captura)) is captura
