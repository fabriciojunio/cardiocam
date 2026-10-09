"""A distribuição preserva arquivos e inclui os recursos de medição."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def script():
    caminho = Path(__file__).resolve().parents[2] / "empacotar.py"
    especificacao = importlib.util.spec_from_file_location("empacotar", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def test_comando_inclui_modelo_e_cascatas_em_pastas_explicitas(tmp_path):
    modulo = script()
    comando = modulo.montar_comando(tmp_path / "saída", tmp_path / "trabalho")
    assert comando[comando.index("--distpath") + 1] == str(tmp_path / "saída")
    assert comando[comando.index("--specpath") + 1] == str(tmp_path / "trabalho")
    assert any("modelo.json" in item for item in comando)
    assert any("cv2/data" in item for item in comando)
    assert Path(comando[-1]).is_file()


def test_falha_do_empacotador_preserva_saida_anterior(tmp_path, monkeypatch):
    modulo = script()
    saida = tmp_path / "saída"
    saida.mkdir()
    anterior = saida / "arquivo-do-usuário.txt"
    anterior.write_text("resultado anterior", encoding="utf-8")
    monkeypatch.setattr(modulo.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=2))
    monkeypatch.setattr(modulo.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "construção"))
    assert modulo.main(["--saida", str(saida)]) == 2
    assert anterior.read_text(encoding="utf-8") == "resultado anterior"


def test_sucesso_explica_interface_correta(tmp_path, monkeypatch, capsys):
    modulo = script()
    nome = "Cardiocam.exe" if modulo.sys.platform.startswith("win") else "Cardiocam"
    (tmp_path / nome).write_bytes(b"artefato de teste")
    monkeypatch.setattr(modulo.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(modulo.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "construção"))
    assert modulo.main(["--saida", str(tmp_path)]) == 0
    assert "escolha a origem" in capsys.readouterr().out
