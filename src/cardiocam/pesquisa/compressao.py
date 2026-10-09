"""Benchmark real de codecs, resolução, bitrate e perdas com FFmpeg."""

from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

from cardiocam.pesquisa.arquivos import sha256


@dataclass(frozen=True)
class VarianteCompressao:
    codec: str = "h264"
    bitrate_kbps: int = 800
    largura: int = 320
    altura: int = 240
    perder_cada: int = 0

    def __post_init__(self):
        if (self.codec not in ("h264", "h265", "vp9") or self.bitrate_kbps <= 0
                or min(self.largura, self.altura) < 16 or self.largura % 2 or self.altura % 2
                or self.perder_cada not in (0, *range(2, 101))):
            raise ValueError("Configuração de compressão inválida.")


def transcodificar(origem, destino, variante: VarianteCompressao, executavel=None):
    ffmpeg = executavel or shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("Instale FFmpeg para executar o benchmark de compressão.")
    entrada, saida = Path(origem).resolve(), Path(destino).resolve()
    if not entrada.is_file() or entrada == saida or saida.exists():
        raise ValueError("A entrada deve existir e a saída deve ser nova.")
    encoder = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9"}[variante.codec]
    filtro = f"scale={variante.largura}:{variante.altura}:flags=area"
    if variante.perder_cada:
        filtro += f",select='not(eq(mod(n,{variante.perder_cada}),0))'"
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(entrada),
            "-map", "0:v:0", "-an", "-map_metadata", "-1", "-vf", filtro,
            "-fps_mode", "vfr", "-c:v", encoder, "-threads", "1", "-pix_fmt", "yuv420p",
            "-b:v", f"{variante.bitrate_kbps}k"]
    if variante.codec == "h265":
        args += ["-x265-params", "pools=none:frame-threads=1:log-level=error"]
    if variante.codec == "vp9":
        args += ["-deadline", "realtime", "-cpu-used", "5"]
    args += [str(saida)]
    processo = subprocess.run(args, capture_output=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if processo.returncode:
        raise RuntimeError("Falha no FFmpeg: " + processo.stderr.decode("utf-8", errors="replace")[-2000:])
    if not saida.is_file() or saida.stat().st_size == 0:
        raise RuntimeError("FFmpeg não produziu vídeo.")
    return saida


def comparar_compressao(origem, pasta_saida, variantes, avaliar, executavel=None):
    """Avalia original e todos os vídeos reais; não substitui arquivos existentes."""
    origem = Path(origem).resolve()
    if not origem.is_file() or not variantes:
        raise ValueError("Vídeo e variantes são necessários.")
    raiz = Path(pasta_saida).resolve()
    raiz.mkdir(parents=True, exist_ok=True)
    pasta = Path(tempfile.mkdtemp(prefix="compressao-", dir=raiz))
    digest = sha256(origem)
    resultados = [{"tipo": "original", "bytes": origem.stat().st_size,
                   "avaliacao": avaliar(origem)}]
    for indice, variante in enumerate(variantes):
        destino = pasta / f"{indice:03d}-{variante.codec}.mkv"
        transcodificar(origem, destino, variante, executavel)
        resultados.append({"tipo": "comprimido", "parametros": asdict(variante),
                           "arquivo": destino.name, "bytes": destino.stat().st_size,
                           "avaliacao": avaliar(destino)})
    return {"versao": 1, "original_sha256": digest, "pasta": str(pasta), "resultados": resultados}
