# Experimentos optativos

Os comandos abaixo implementam as frentes de pesquisa restantes. Não mudam o
algoritmo padrão nem substituem o modelo de qualidade distribuído. A saída
declara `experimental: true`. Código executável e testes de frequência
conhecida não equivalem a precisão demonstrada em participantes.

## Instalação e execução

Na pasta do projeto, instale o pacote para usar os comandos:

```powershell
python -m pip install -e ".[dev]"
python -m cardiocam pesquisa --help
```

Redes locais exigem as dependências optativas. Para CPU:

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install onnx
```

FFmpeg deve estar no PATH para os experimentos de compressão. Vídeos e pesos
externos não são baixados automaticamente. Resultados JSON usam UTF-8, `null`
para valores ausentes e nomes de saída novos; o comando recusa sobrescrever
um resultado existente.

## Vídeo, regiões, SSR e consenso

```powershell
python -m cardiocam pesquisa video video.avi --saida analise.json --janela 10 --grade 3 --metodos verde pos chrom lgi omit pbv_adaptativo ssr --referencia referencia.csv
python -m cardiocam pesquisa video video.avi --saida estabilizada.json --estabilizar --ancorar-olhos
```

`--area X Y LARGURA ALTURA` usa uma região explicitamente escolhida. Sem essa
opção, o rastreador acompanha a caixa detectada. Isso não identifica uma
pessoa biometricamente nem garante detectar a troca de pessoa na mesma posição.

Cada célula da grade conserva sua média RGB e seu segundo momento espacial
3×3, calculado sem centrar os pixels. SSR recebe esses momentos, não as médias
de cor. Regiões sem pele suficiente são ausentes. Momentos sem posto espacial
suficiente não produzem SSR. A implementação segue as equações de
[Wang, Stuijk e de Haan](https://doi.org/10.1109/TBME.2015.2508602), com
alinhamento de sinais dos autovetores entre quadros.

Os métodos passam pelo mesmo detrend e passa-faixa antes da comparação.
Periodograma, Welch e autocorrelação são registrados/comparados. Uma região
com estimadores discordantes não vota. O consenso exige ao menos duas regiões
e dois métodos, pouca saturação e baixo acoplamento ao fundo. Dois consensos
incompatíveis levam à abstenção. O acompanhamento temporal recusa saltos e
reinicia após lacunas. Concordância de métodos não prova origem fisiológica:
um artefato comum pode afetar vários métodos e regiões.

`--estabilizar` usa Lucas–Kanade, checagem de ida e volta e similaridade por
RANSAC. `--ancorar-olhos` usa os dois centros detectados, recusa inclinação
excessiva e alinha a imagem à referência. Não estima pose 3D. Falhas e mudanças
de contexto apagam o histórico espacial. O custo e as recusas ficam no relatório.

O JSON contém janelas aceitas/recusadas, candidatos, falhas de cada método,
características de estimativas brutas, FPS de processamento e métricas contra
referência, quando fornecida. Estimativas de baixo SNR também são exportadas
para não selecionar previamente os exemplos usados para treinar qualidade.

## Iluminação, ruído e aumento de dados

```powershell
python -m cardiocam pesquisa video video.avi --saida fundo.json --corrigir-fundo --suavizacao 0.16
python -m cardiocam pesquisa video video.avi --saida retinex.json --fotometria retinex
python -m cardiocam pesquisa ablacao video.avi --saida ablacao.json --movimento 4 --iluminacao 0.3 --ruido 2 --semente 7 --referencia referencia.csv
```

Normalização cromática, Retinex multiescala clássico, regressão pelo fundo e
Savitzky–Golay são ablações optativas. Retinex clássico não é Retinexformer.
A suavização limita a janela a 0,2 s; isso ainda pode atenuar componentes do
pulso e precisa ser comparado. Sem fundo, o método não remove um componente
global estimado do rosto, pois ele pode conter o próprio pulso.

Perturbações de movimento, iluminação, ruído e congelamento conservam os
timestamps e a referência. A semente e os parâmetros são registrados.
Separe participantes antes de gerar variantes: uma variante de um vídeo de
treino não pode virar vídeo de teste.

## Compressão e perda de quadros

```powershell
python -m cardiocam pesquisa compressao video.avi --saida resultados --codecs h264 h265 vp9 --bitrates 400 1000 --resolucoes 320x240 640x480 --perdas 0 5 --referencia referencia.csv
```

O comando codifica vídeos reais com libx264, libx265 e libvpx-vp9, preserva
os timestamps nas variantes com perdas, analisa o original e cada variante
e registra bitrate solicitado, resolução, tamanho em bytes e SHA-256 do
original. `--perdas 5` remove cada quinto quadro; não simula toda a pilha de
uma plataforma de reuniões. Bitrate solicitado não é bitrate garantido pelo
encoder. Uma área explícita é escalada da resolução original para a variante.
O diretório de cada execução é novo; os vídeos gerados permanecem disponíveis.

## Exposição de pele

```powershell
python -m cardiocam pesquisa exposicao --camera 0 --minimo -10 --maximo -1 --incremento 1 --saida exposicao.json
```

Os limites do exemplo precisam corresponder ao driver da câmera. O comando
exige confirmação de exposição manual e confirma por leitura cada ajuste.
O controlador busca uma faixa de luminância de pele antes da medição e trava
após três confirmações. Não aplica oscilação de exposição durante a janela
cardíaca. Mudança posterior invalida a estabilidade. É um controlador local
inspirado em [Skin-AE](https://doi.org/10.1109/EMBC53108.2024.10781984), sem
afirmar reprodução do ensaio com câmera industrial. Testes de driver controlado
não demonstram que uma webcam física aceita esses limites.

## Redes e realçadores

Há implementações locais independentes de DeepPhys, PhysNet-3DCNN-ED,
EfficientPhys convolucional e curvas Zero-DCE, com testes de inferência,
gradiente, treinamento e integridade de pesos em CPU. Não são checkpoints
intercambiáveis com os repositórios de referência. A variante convolucional
local de EfficientPhys é um baseline, sem pretensão de reproduzir todas as
variantes ou métricas do artigo. Referências:
[DeepPhys](https://www.ecva.net/papers/eccv_2018/papers_ECCV/papers/Weixuan_Chen_DeepPhys_Video-Based_Physiological_ECCV_2018_paper.pdf),
[PhysNet](https://arxiv.org/abs/1905.02419),
[EfficientPhys](https://arxiv.org/abs/2110.04447),
[Zero-DCE](https://openaccess.thecvf.com/content_CVPR_2020/html/Guo_Zero-Reference_Deep_Curve_Estimation_for_Low-Light_Image_Enhancement_CVPR_2020_paper.html).

```powershell
python -m cardiocam pesquisa treinar-rede dados-neurais.json --arquitetura physnet --saida treino-local --epocas 10
python -m cardiocam pesquisa rede video.avi --pesos treino-local/pesos.json --saida rede.json --referencia referencia.csv
python -m cardiocam pesquisa realcar video.avi --pesos realcador.json --saida comparacao-realce.json
```

O treinamento exige a onda PPG de contato sincronizada, não apenas BPM.
Cada NPZ, lido sem pickle, contém `video` RGB uint8 T×H×W×3, `ppg` com T
amostras e `fps`. O manifesto contém `versao: 1` e `clipes`, com `arquivo`,
`participante`, `particao` (`treino`, `calibracao`, `teste`), `dataset` e
`licenca`. Um participante não pode atravessar partições. A calibração escolhe
o checkpoint; o teste só avalia a escolha final. Perda da onda não substitui
avaliação de BPM, falsa aceitação e generalização em outro conjunto.

O manifesto de pesos declara `versao`, `formato`, `arquitetura`, `arquivo`,
`sha256`, `licenca`, `procedencia` e `preprocessamento`. Formatos:

| Uso | Formato | Preprocessamento |
| --- | --- | --- |
| Redes locais e Zero-DCE | `torch_state_dict` | `rgb_0_1_local_v1` |
| Realçadores ONNX, incluindo Retinexformer exportado | `onnx` | `rgb_nchw_0_1` |
| Outras redes PPG exportadas | `onnx` | `rgb_ncthw_0_1` |

Redes PPG ONNX podem declarar `tamanho` espacial entre 16 e 256. A saída deve
conter T ou T−1 valores finitos. O suporte depende de o OpenCV conseguir
executar os operadores do grafo exportado. Não há pesos Retinexformer ou
pesos treinados em pessoas incluídos. Declarar a licença no manifesto não
concede uma licença: obtenha autorização compatível para os pesos e os dados.

## Recalibração da qualidade

```powershell
python -m cardiocam pesquisa recalibrar dados-qualidade.json --saida modelo-real.json --cobertura 0.5 --erro-alvo 2
```

O manifesto tem `versao: 1` e `sessoes`. Cada sessão declara `participante`,
`dataset`, `licenca`, `dispositivo`, `condicao`, `caracteristicas` (JSON da
avaliação com referência) e `particao`. Todos os vetores precisam ter as onze
características finitas, contexto completo e erro contra referência.
`teste_dataset_inedito: true` também recusa datasets de teste usados no ajuste.
O padronizador, os pesos e a temperatura/limiar não usam o teste. O comando
grava um modelo novo; não substitui o modelo sintético distribuído.

Para aplicar o modelo verificado na medição, use
`cardiocam arquivo video.avi --modelo-qualidade modelo-real.json` ou
`cardiocam ao-vivo --modelo-qualidade modelo-real.json`. A câmera da teleconsulta
também aceita essa opção. Um arquivo escolhido ausente/inválido é erro;
não aciona silenciosamente o modelo distribuído ou uma regra fixa.

## Pupila, pele periocular e movimento de cabeça

```powershell
python -m cardiocam pesquisa modalidades video.avi --saida modalidades.json --janela 10
```

O comando registra diâmetros e centros de pupilas RGB quando há uma elipse
escura aproveitável, médias da pele abaixo dos olhos e estimadores separados
de video-BCG, obtidos por fluxo óptico e PCA de trajetórias verticais.
Piscadas, reflexos, ausência de olhos ou perda de pontos produzem ausência
de leitura. As séries não são fundidas automaticamente com rPPG. Um resultado
com deslocamento sintético conhecido verifica o algoritmo de movimento;
não comprova que esse movimento veio de um batimento cardíaco.

## Teleconsulta com medição local

O protótipo mede na câmera local antes de qualquer compressão da reunião e
envia somente `sessao`, `sequencia`, `instante_s`, `bpm`, `qualidade` e `aceita`.
Não envia quadros. O token, com pelo menos 32 caracteres, é fornecido por
variável de ambiente, não pela URL ou pelos logs. Use identificador pseudônimo.

```powershell
python -m cardiocam teleconsulta receber --sessao participante-01 --consentimento
python -m cardiocam teleconsulta camera --sessao participante-01 --url http://127.0.0.1:8765/leituras --consentimento
python -m cardiocam teleconsulta transmitir leituras.csv --sessao participante-01 --url http://127.0.0.1:8765/leituras --consentimento
```

Configure `CARDIOCAM_TOKEN` nos dois processos com uma credencial de sessão
gerada de forma segura. `--consentimento` registra a confirmação do operador,
sem substituir um processo institucional de consentimento. A sessão tem prazo
máximo de uma hora, rejeita leituras repetidas/fora de ordem e apaga dados ao
encerrar. A fila de envio conserva no máximo uma leitura aguardando a rede.
Leitura recusada transmite `bpm: null`.

O receptor incluído escuta apenas loopback. Destinos remotos exigem HTTPS,
com validação TLS e sem redirecionamentos. Um serviço remoto, integração com
plataformas de reunião e validação institucional permanecem etapas de
implantação, não resultados desses testes locais.
