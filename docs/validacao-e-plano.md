# Auditoria e plano de evolução do Cardiocam

Revisão de 09/10/2026 sobre a base `b318243` e a branch local
`fix/validade-medicao`. As alterações corrigem o comportamento do software;
não demonstram precisão em pessoas ou uso clínico. Nenhum resultado real com
ECG/PPG sincronizado foi produzido nesta revisão.

## Evidência de execução

- A base original passou por 2.252 testes locais.
- Após as correções de captura, tempo, visão, avaliação e Qt, a suíte completa
  passou por 2.336 testes em 699,95 s, com quatro processos no Windows/Python 3.12.
- A conferência final do subconjunto rápido passou por 2.245 testes em
  154,63 s, com cobertura de 84,35%, incluindo ramos. A revisão atual contém
  2.363 testes, dos quais 118 são marcados como lentos. Os testes lentos
  passaram na execução completa anterior; não são 2.363 testes com pessoas.
- A demonstração sintética agora tem janela compatível com sua duração e
  `--erro-maximo` para falhar sem estimativa ou acima do limite.
- Os novos jobs de Windows e dependências mínimas foram acrescentados à CI.
  Eles ainda precisam executar no GitHub; alteração de workflow não é resultado.
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
| 10 | Renovar regiões e máscaras quando muda o alvo | Parcial | Reset implementado; adaptação de pose e máscara por qualidade pendente |
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
| 23 | Conferir Windows e versões mínimas de dependências na CI | Parcial | Jobs adicionados; execução remota pendente |
| 24 | Compatibilizar NumPy 1.26 e mss 9 | Implementado | Integração numérica via SciPy e fábrica de captura compatível |
| 25 | Exigir estimativa e limite de erro na demonstração da CI | Implementado | Guarda `--erro-maximo` e exportação da simulação |
| 26 | Conferir instalação por wheel em ambiente limpo | Implementado | Instalação, importação, dados do modelo, Qt e comandos verificados; detalhes abaixo |
| 27 | Conferir geração e abertura do executável Windows | Parcial | Empacotamento preserva arquivos; verificação final registrada abaixo; outras máquinas pendentes |
| 28 | Corrigir documentação divergente e números antigos | Implementado | Fundo, suavização, FPS, quantização e natureza dos testes corrigidos |
| 29 | Comparar LGI | Experimental | Testes de frequências conhecidas, ausência de sinal e benchmark sintético |
| 30 | Comparar OMIT | Experimental | QR temporal da descrição matemática, sem matriz quadrada por duração |
| 31 | Comparar PBV | Experimental | Variante adaptativa identificada; assinatura calibrada por câmera pendente |
| 32 | Comparar SSR | Pendente | Precisa de estatísticas espaciais e implementação compatível com a referência |
| 33 | Comparar FFT, Welch, autocorrelação e rastreamento temporal | Parcial | FFT e detecção por picos existem; ablação reproduzível dos demais pendente |
| 34 | Selecionar pequenas regiões por qualidade e concordância | Pendente | Requer preservação das séries por região e avaliação com referência |
| 35 | Estabilizar por landmarks e fluxo óptico | Pendente | Definir dependência, custo e controles contra artefatos periódicos |
| 36 | Selecionar e fundir métodos adaptativamente | Pendente | SNR maior não prova BPM correto; exige calibração e ablação em participantes separados |
| 37 | Testar Skin-AE e controle de exposição | Pendente | Câmera precisa aceitar e efetivar os controles; ensaio com referência |
| 38 | Comparar normalização fotométrica, Retinexformer e Zero-DCE | Pendente | Dados, pesos e licenças; confirmar preservação temporal do pulso |
| 39 | Comparar redução de ruído e iluminação temporal | Pendente | Medir distorção de pulso e falsa aceitação em vídeos sem sinal |
| 40 | Avaliar codecs, bitrate, resolução e perda de quadros | Parcial | Guards de continuidade prontos; benchmark de compressão com referência pendente |
| 41 | Avaliar PhysNet, DeepPhys, EfficientPhys e modelos recentes | Pendente | Dados autorizados, pesos, partições, dependências e custo computacional |
| 42 | Testar aumento de dados por movimento e iluminação | Pendente | Separar participantes antes do aumento; medir generalização entre datasets |
| 43 | Comparar leituras com ECG/PPG sincronizado | Parcial | Avaliador, manifesto e testes prontos; sessões reais ausentes |
| 44 | Recalibrar confiança com participantes não vistos | Pendente | Dados reais de treino, calibração e teste sem vazamento |
| 45 | Prototipar medição no paciente antes da compressão | Parcial | Webcam local existe; transporte, sessões e integração de teleconsulta pendentes |
| 46 | Investigar região periocular, pupila RGB e video-BCG | Pendente | Experimentos separados com referência; não integrar hipótese ocular como BPM validado |
| 47 | Revisar consentimento, privacidade e limites de uso | Parcial | Propostas e protocolo disponíveis; revisão institucional e avaliação real pendentes |

## Resultados experimentais disponíveis

Em 56 cenários de séries sintéticas, LGI e OMIT tiveram MAE arredondado de
0,02 bpm e nenhuma falha. PBV adaptativo teve MAE de 0,09 bpm entre os casos
com estimativa e sete falhas. Esses números não incluem detecção facial,
codec, webcam ou participantes. Falhas devem ser relatadas junto com MAE.
Não justificam substituir os métodos atuais no aplicativo.

## Distribuição conferida

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
