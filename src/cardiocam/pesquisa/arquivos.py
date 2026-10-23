"""Saídas UTF-8 e identidade dos arquivos de um experimento."""

import hashlib
import json
from pathlib import Path


def sha256(caminho):
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024*1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def gravar_json(caminho, dados):
    destino = Path(caminho)
    texto = json.dumps(dados, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("x", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    return destino
