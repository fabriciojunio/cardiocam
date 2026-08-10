"""Erros de domínio, com mensagens em português voltadas ao usuário final."""

from __future__ import annotations


class ErroCardiocam(Exception):
    """Raiz da hierarquia de erros do sistema."""

    codigo = "erro_generico"


class JanelaInsuficiente(ErroCardiocam):
    """Não há amostras suficientes para uma estimativa confiável."""

    codigo = "janela_insuficiente"

    def __init__(self, amostras: int, minimo: int) -> None:
        super().__init__(
            f"A janela tem {amostras} amostras, mas são necessárias ao menos "
            f"{minimo} para estimar a frequência com segurança."
        )
        self.amostras = amostras
        self.minimo = minimo


class FrequenciaAmostragemInvalida(ErroCardiocam):
    """Taxa de amostragem incompatível com a banda de interesse."""

    codigo = "fps_invalido"

    def __init__(self, fps: float, minimo: float) -> None:
        super().__init__(
            f"A taxa de {fps:.2f} quadros por segundo é baixa demais; o mínimo "
            f"para observar a banda cardíaca sem rebatimento é {minimo:.2f} fps."
        )
        self.fps = fps
        self.minimo = minimo


class BandaInvalida(ErroCardiocam):
    """Banda passante mal formada ou fora do intervalo de Nyquist."""

    codigo = "banda_invalida"


class RostoNaoEncontrado(ErroCardiocam):
    """Nenhum rosto detectado no quadro."""

    codigo = "rosto_nao_encontrado"

    def __init__(self) -> None:
        super().__init__(
            "Nenhum rosto foi encontrado no quadro. Verifique a iluminação e "
            "mantenha o rosto de frente para a câmera."
        )


class RegiaoInvalida(ErroCardiocam):
    """Região de interesse vazia ou fora dos limites da imagem."""

    codigo = "regiao_invalida"


class FonteIndisponivel(ErroCardiocam):
    """Câmera ou arquivo de vídeo não pôde ser aberto."""

    codigo = "fonte_indisponivel"


class SinalSemQualidade(ErroCardiocam):
    """O sinal extraído não tem relação sinal-ruído suficiente."""

    codigo = "sinal_sem_qualidade"

    def __init__(self, snr_db: float, minimo_db: float) -> None:
        super().__init__(
            f"A relação sinal-ruído de {snr_db:.1f} dB está abaixo do mínimo de "
            f"{minimo_db:.1f} dB exigido para reportar um valor."
        )
        self.snr_db = snr_db
        self.minimo_db = minimo_db
