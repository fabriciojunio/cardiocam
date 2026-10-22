"""Amostragem de visibilidade usa a área e o identificador escolhidos."""

from cardiocam.desktop.janelas import JanelaDaTela, area_coberta


def test_area_coberta_e_reconhecida(monkeypatch):
    monkeypatch.setattr("cardiocam.desktop.janelas.NO_WINDOWS", True)
    monkeypatch.setattr("cardiocam.desktop.janelas._janela_na_posicao", lambda x, y: 99)
    assert area_coberta(JanelaDaTela(7, "Reunião", -1920, 0, 1920, 1080))


def test_pontos_ficam_dentro_do_participante(monkeypatch):
    monkeypatch.setattr("cardiocam.desktop.janelas.NO_WINDOWS", True)
    pontos = []
    def encontrar(x, y):
        pontos.append((x, y))
        return 7
    monkeypatch.setattr("cardiocam.desktop.janelas._janela_na_posicao", encontrar)
    assert not area_coberta(JanelaDaTela(7, "Reunião", 100, 200, 1000, 800), (.5, .5, 1, 1))
    assert all(600 <= x <= 1100 and 600 <= y <= 1000 for x, y in pontos)


def test_falta_de_suporte_nao_e_declarada_visibilidade(monkeypatch):
    monkeypatch.setattr("cardiocam.desktop.janelas.NO_WINDOWS", False)
    assert area_coberta(JanelaDaTela(7, "Reunião", 0, 0, 1000, 800)) is None
