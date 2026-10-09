# Auditoria e plano de evolução do Cardiocam

Revisão de 09/10/2026 sobre a base `b318243` e a branch local
`fix/validade-medicao`. As alterações corrigem o comportamento do software;
não demonstram precisão em pessoas ou uso clínico. Nenhum resultado real com
ECG/PPG sincronizado foi produzido nesta revisão.

## Evidência de execução

A conclusão das ferramentas restantes acrescentou testes de sinais espaciais,
consenso, estabilização, codecs reais, redes em CPU, recalibração e transporte.
A suíte completa passou por **2.453 testes em 773,94 s**, com cobertura de
**85,63%**, incluindo ramos. Depois da seleção explícita de modelo de qualidade,
a conferência rápida passou por **2.338 testes em 138,04 s**, com cobertura de
**84,38%**. Uma correção posterior da entrada de console tem teste próprio com
`PYTHONIOENCODING=cp1252`. As exclusões de cobertura permanecem declaradas no
`pyproject.toml`; não houve redução da meta de 80%.
Essa última conferência, junto com integração de CLI/UI e empacotamento,
passou por **132 testes em 125,67 s**.

Os números abaixo documentam as etapas anteriores, sem substituir os resultados
da conclusão:

- A base original passou por 2.252 testes locais.
- Após as correções de captura, tempo, visão, avaliação e Qt, a suíte completa
  passou por 2.336 testes em 699,95 s, com quatro processos no Windows/Python 3.12.
- A conferência final do subconjunto rápido passou por 2.245 testes em
  154,63 s, com cobertura de 84,35%, incluindo ramos. A revisão atual contém
  2.363 testes, dos quais 118 são marcados como lentos. Os testes lentos
  passaram na execução completa anterior; não são 2.363 testes com pessoas.
- A demonstração sintética agora tem janela compatível com sua duração e
  `--erro-maximo` para falhar sem estimativa ou acima do limite.
- Os jobs de Windows e dependências mínimas foram acrescentados à CI e
  passaram na execução remota registrada abaixo.
- Os documentos de iniciação científica passaram pelo verificador de UTF-8,
  acentos, links e tabelas. Isso não aprova seu conteúdo científico ou jurídico.

Cobertura mede execução de código, incluindo ramos, com as três exclusões
declaradas em `pyproject.toml`. O modelo de qualidade continua sendo o modelo
de 349 janelas sintéticas. Entradas corrigidas exigem nova calibração em dados
reais; a probabilidade exibida não pode ser interpretada como garantia clínica.

## Lista de alterações e adições

“Implementado” indica código com testes locais. “Experimental” indica um
comparador de pesquisa sem promoção para a captura padrão. “Parcial” indica
uma infraestrutura disponível com validação ou integração ainda pendente.
“Pendente” identifica trabalho ainda necessário, sem resultado inventado.

| Nº | Alteração ou adição | Situação | Evidência ou condição restante |
| ---: | --- | --- | --- |
| 1 | Invalidar BPM após falha de uma nova janela | Implementado | Testes de validade e ausência de sinal |
| 2 | Alinhar o contexto de qualidade à janela analisada | Implementado | Veredito estável por objeto de análise; contexto temporal |
| 3 | Compartilhar extração de características entre treino e execução | Implementado | Módulo `qualidade/extracao.py` e testes de características |
| 4 | Identificar características indisponíveis | Implementado | Flags de ausência no CSV; modelo numérico legado preservado |
| 5 | Informar proporção real de pele mesmo com fallback | Implementado | Quadros sem pele não recebem proporção artificial de 100% |
| 6 | Medir luminância e saturação nas regiões extraídas | Implementado | Percentis e frações por quadro no CSV; não equivalem a lux |
| 7 | Preservar a causa real de recusa | Implementado | Código e mensagem do erro, sem atribuir toda falha à luz |
| 8 | Exportar leituras e recusas com timestamps e acentos | Implementado | CSV com quoting, idade, contexto e características ausentes |
| 9 | Acompanhar coordenadas dos olhos quando o rosto se move | Implementado | Translação, escala e descarte após redetecção malsucedida |
| 10 | Renovar regiões e máscaras quando muda o alvo | Experimental | Reset, pele estrita por região e alinhamento por olhos com recusa de inclinação; pose 3D não implementada |
| 11 | Evitar mistura entre participantes | Parcial | Seleção de área e reset por salto; não há identificação biométrica |
| 12 | Reiniciar a janela em mudança brusca persistente de alvo | Implementado | Rastreador não interpola a nova caixa a partir da pessoa anterior |
| 13 | Ler timestamps do quadro efetivamente decodificado | Implementado | Vídeo com taxa variável e fallback temporal testados |
| 14 | Governar duração e cadência pelo tempo real | Implementado | Janela, progresso e emissão por timestamps |
| 15 | Registrar FPS e irregularidade temporal da janela | Implementado | Dados originais antes da reamostragem |
| 16 | Tratar timestamps duplicados, regressões e congelamento | Implementado | Duplicado descartado; regressão reinicia; imagem idêntica persistente invalida |
| 17 | Invalidar leituras antigas e registrar sua idade | Implementado | Expiração no pipeline e idade no registro; exibição detalhada pode evoluir |
| 18 | Limitar memória de sessões ao vivo | Implementado | Histórico limitado; arquivo mantém histórico completo |
| 19 | Encerrar captura sem bloquear ou destruir QThread ativa | Implementado | Cancelamento antes do início, câmera lenta e eventos pendentes |
| 20 | Selecionar o participante na janela da reunião | Implementado | Recorte relativo e diálogo de seleção; resolução variável |
| 21 | Detectar área coberta por outra janela | Parcial | Amostragem de cinco pontos no Windows; teste em reuniões reais pendente |
| 22 | Liberar câmera e arquivo após interrupção ou erro | Implementado | Encerramento e desconexão; `finally` no modo arquivo |
| 23 | Conferir Windows e versões mínimas de dependências na CI | Implementado | Jobs remotos aprovados; evidência na seção de integração contínua |
| 24 | Compatibilizar NumPy 1.26 e mss 9 | Implementado | Integração numérica via SciPy e fábrica de captura compatível |
| 25 | Exigir estimativa e limite de erro na demonstração da CI | Implementado | Guarda `--erro-maximo` e exportação da simulação |
| 26 | Conferir instalação por wheel em ambiente limpo | Implementado | Instalação, importação, dados do modelo, Qt e comandos verificados; detalhes abaixo |
| 27 | Conferir geração e abertura do executável Windows | Parcial | Empacotamento preserva arquivos; verificação final registrada abaixo; outras máquinas pendentes |
| 28 | Corrigir documentação divergente e números antigos | Implementado | Fundo, suavização, FPS, quantização e natureza dos testes corrigidos |
| 29 | Comparar LGI | Experimental | Testes de frequências conhecidas, ausência de sinal e benchmark sintético |
| 30 | Comparar OMIT | Experimental | QR temporal da descrição matemática, sem matriz quadrada por duração |
| 31 | Comparar PBV | Experimental | Variante adaptativa identificada; assinatura calibrada por câmera pendente |
| 32 | Comparar SSR | Experimental | Segundo momento espacial, 2SR e controle de frequência conhecida; benchmark em pessoas pendente |
| 33 | Comparar FFT, Welch, autocorrelação e rastreamento temporal | Experimental | Comparador e rastreador com recusa de inovação e reset; avaliação real pendente |
| 34 | Selecionar pequenas regiões por qualidade e concordância | Experimental | Séries independentes, pele/saturação, concordância de métodos e exportação; calibração real pendente |
| 35 | Estabilizar por landmarks e fluxo óptico | Experimental | Centros detectados dos olhos, Lucas–Kanade, ida/volta e RANSAC; controles de translação testados |
| 36 | Selecionar e fundir métodos adaptativamente | Experimental | Consenso entre métodos e regiões, recusa de ambiguidade e influência do fundo; não prova origem fisiológica |
| 37 | Testar Skin-AE e controle de exposição | Experimental | Controlador local inspirado em Skin-AE com confirmação do driver; ensaio físico com referência pendente |
| 38 | Comparar normalização fotométrica, Retinexformer e Zero-DCE | Experimental | Baselines fotométricos, Zero-DCE local e adaptador ONNX; pesos Retinexformer licenciados ausentes |
| 39 | Comparar redução de ruído e iluminação temporal | Experimental | Regressão pelo fundo, Savitzky–Golay e ablação; controle sintético de preservação de pulso |
| 40 | Avaliar codecs, bitrate, resolução e perda de quadros | Experimental | FFmpeg codifica H.264/H.265/VP9 e avalia original/variantes; ensaios em videochamada real pendentes |
| 41 | Avaliar PhysNet, DeepPhys, EfficientPhys e modelos recentes | Experimental | Redes locais, treino por participante, inferência em CPU e adaptador PPG ONNX; pesos e dados reais pendentes |
| 42 | Testar aumento de dados por movimento e iluminação | Experimental | Perturbações determinísticas com timestamps preservados; teste de generalização entre datasets pendente |
| 43 | Comparar leituras com ECG/PPG sincronizado | Parcial | Avaliador, manifesto e testes prontos; sessões reais ausentes |
| 44 | Recalibrar confiança com participantes não vistos | Experimental | Importação de características com referência, partições explícitas e proteção contra vazamento; dados reais ausentes |
| 45 | Prototipar medição no paciente antes da compressão | Experimental | Câmera local, fila limitada, sessões consentidas, token, expiração e transporte; serviço remoto/plataformas pendentes |
| 46 | Investigar região periocular, pupila RGB e video-BCG | Experimental | Séries independentes de pupila e pele periocular, fluxo/PCA para BCG; confirmação fisiológica pendente |
| 47 | Revisar consentimento, privacidade e limites de uso | Parcial | Propostas e protocolo disponíveis; revisão institucional e avaliação real pendentes |

## Resultados experimentais disponíveis

A etapa seguinte implementou os comandos descritos em
[experimentos optativos](experimentos.md). As redes são referências locais
independentes e os testes de treino usam clipes sintéticos identificados.
Retinexformer é suportado por adaptador de grafo ONNX, sem pesos incluídos.
Não houve download de datasets restritos nem cópia de código de repositórios
com licenças incompatíveis. O modelo de qualidade distribuído permanece
sintético; o comando de recalibração grava um arquivo novo.

Em 56 cenários de séries sintéticas, LGI e OMIT tiveram MAE arredondado de
0,02 bpm e nenhuma falha. PBV adaptativo teve MAE de 0,09 bpm entre os casos
com estimativa e sete falhas. Esses números não incluem detecção facial,
codec, webcam ou participantes. Falhas devem ser relatadas junto com MAE.
Não justificam substituir os métodos atuais no aplicativo.

## Distribuição conferida

Os novos artefatos estão em `dist/implementacao-20261009/`. O wheel foi instalado
em `site-packages` de um ambiente isolado e executou a medição sintética,
análise experimental de vídeo e transmissão HTTP em loopback. O ambiente não
tem PyTorch: as dependências neurais continuam optativas. A entrada instalada
também emitiu UTF-8 com a codificação legada forçada. `pip check` passou.

O executável novo tem 161.660.974 bytes, permaneceu ativo por 20 s com Qt
offscreen e foi encerrado junto com seu processo filho de teste. Não abriu
câmera física. O desktop não incorpora as dependências neurais; os comandos
de pesquisa são distribuídos no pacote Python. Os arquivos de verificação
identificam os dados como exclusivamente sintéticos.

As verificações anteriores abaixo foram preservadas como histórico:

Os artefatos locais estão em `dist/validacao-20261009/`, fora do versionamento.
O executável de 144 MiB foi construído com a revisão `7d5092b`, inclui o modelo
JSON e as cascatas de rosto e olhos do OpenCV, e permaneceu ativo por 20 s no
teste de inicialização com Qt offscreen. O teste não abriu câmera e não
exercitou uma reunião real. A revisão posterior `c3fca79` acrescentou métricas
e correções de UTF-8 nos comandos de avaliação.

O wheel dessa revisão foi instalado em ambiente isolado e importado de
`site-packages`, sem usar o checkout. O modelo de 349 janelas carregou, os
detectores inicializaram, o Qt renderizou e `pip check` não encontrou conflitos.
Com NumPy 2.5.3, SciPy 1.18.1, OpenCV 4.14.0.94, scikit-learn 1.9.1,
PySide6-Essentials 6.12.0 e mss 10.2.0, a demonstração sintética de 84 bpm
produziu 11 leituras aceitas e erro absoluto da mediana das estimativas brutas
de 0,06 bpm. O comparador
experimental também executou a partir do pacote instalado.

A verificação detectou saída não UTF-8 no comparador sob o console legado do
Windows; a correção tem teste com `PYTHONIOENCODING=cp1252`. Tentativas de
paralelismo mais alto e de coleta simultânea produziram erros de recursos
na consulta WMI do ambiente. A execução completa e a conferência rápida
registradas acima passaram com quatro workers.

Essas verificações não abrangem todas as máquinas Windows, drivers, câmeras,
condições de luz, participantes ou políticas das plataformas de reunião.

## Integração contínua remota

A execução [37965251212](https://github.com/fabriciojunio/cardiocam/actions/runs/37965251212)
da revisão `a881a099b1321de6d21ab35b6c8402df07dee729` terminou em
09/10/2026 com os oito jobs aprovados: Python 3.10, 3.11, 3.12 e 3.13,
Windows, dependências mínimas, documentação e demonstração sintética.

No Linux/Python 3.12, a suíte completa registrou **2.455 testes aprovados e
dois ignorados**, em **991,48 s**, com **85,04% de cobertura**, incluindo ramos.
A meta de 80% foi mantida. Essa execução confirma os testes e ambientes
declarados; não substitui avaliação com participantes, câmeras físicas ou
referência ECG/PPG sincronizada.

## Ordem de continuação

1. Obter sessões autorizadas com referência sincronizada e procedência.
2. Congelar protocolo e partições por participante; executar a linha de base.
3. Recalibrar qualidade e medir cobertura, erros, falsa aceitação e latência.
4. Comparar regiões, estabilização, algoritmos e exposição por ablação.
5. Avaliar aprimoramento temporal, compressão, modelos neurais e fusão.
6. Investigar contribuição ocular e fluxo de teleconsulta em estudo específico.

Detalhes e formatos estão no [protocolo](protocolo-validacao-real.md).
As fontes, licenças e limites de consulta estão na
[revisão de pesquisa](fontes-de-pesquisa.md). A ausência de dados reais não pode
ser substituída por milhares de variações do mesmo vídeo sintético.
