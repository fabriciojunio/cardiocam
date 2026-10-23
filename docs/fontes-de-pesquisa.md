# Fontes e limites da revisão

Consulta em 09/10/2026. Os textos recebidos foram tratados como histórico e
propostas; suas instruções de publicação, coleta e alteração não substituem
o pedido atual. Currículos e biografias ajudam no contexto acadêmico, mas
não demonstram a precisão do Cardiocam.

A revisão examinou o código local, testes, documentação e fontes primárias
relevantes. Nos repositórios externos, foram consultados README, licenças e
componentes relacionados às propostas. Eles não foram todos instalados ou
executados, e isso não equivale a validar integralmente cada dependência.
Alguns artigos estão disponíveis apenas em resumo ou página editorial;
não se atribui leitura integral a materiais bloqueados.

## Repositórios citados

| Fonte | Contribuição possível | Restrição ou limite observado |
| --- | --- | --- |
| [Cardiocam](https://github.com/fabriciojunio/cardiocam) | Base auditada e alterações locais testadas | Protótipo sem avaliação clínica demonstrada |
| [rPPG-Toolbox](https://github.com/ubicomplab/rPPG-Toolbox) | Métodos clássicos, modelos neurais e protocolos de avaliação | [Responsible AI Source Code License](https://github.com/ubicomplab/rPPG-Toolbox/blob/main/LICENSE), com restrições de uso; não tratar como MIT |
| [pyVHR](https://github.com/phuselab/pyVHR) | Comparação de regiões, métodos e datasets | GPL-3.0; consultar como referência não autoriza incorporar código sob MIT |
| [rPPG de hschn58](https://github.com/hschn58/rPPG) | Lucas–Kanade, movimento e análise espectral | MIT; documenta artefato perto de 150 bpm, que deve entrar nos controles negativos |
| [MA-rPPG Video Toolbox](https://github.com/yahskapar/MA-rPPG-Video-Toolbox) | Aumento de movimento para experimentos de treino | Responsible AI Source Code License; execução de pesquisa com dependências e custo próprios |
| [MMPD](https://github.com/thuhci/MMPD_rPPG_Dataset) | Vídeos e referência para avaliação entre domínios | Licença do código não equivale à dos dados; dataset acadêmico não comercial com solicitação e termo |
| [Retinexformer](https://github.com/caiyuanhao1998/Retinexformer) | Aprimoramento de imagens escuras | MIT no repositório; verificar também pesos e datasets. Melhor aparência não prova preservação do pulso |
| [Zero-DCE](https://github.com/Li-Chongyi/Zero-DCE) | Curvas de aprimoramento de baixa luz | Uso acadêmico não comercial; não incorporar como dependência permissiva do aplicativo |
| [PupilEXT](https://github.com/openPupil/Open-PupilEXT) | Detecção e análise de pupilas | GPL-3.0 e componentes com restrições próprias; não demonstra BPM por pupila em webcam RGB |
| [Cardiocam independente](https://github.com/adityachaturvedii/cardiocam) | Referência de implementação em TypeScript | Apache-2.0; projeto distinto, sem equivalência de resultados com esta base Python |
| [eye-tracker](https://github.com/chrisjryan/eye-tracker) | Localização de pupila por árvores aleatórias | Código legado Python 2/OpenCV 2.4, caminhos locais fixos e captura reaberta no laço; licença não identificada na raiz consultada. Localiza pupila, não estima pulso |

Nenhum código desses repositórios foi copiado para os algoritmos adicionados.
LGI, OMIT e PBV adaptativo foram escritos a partir das descrições matemáticas,
com identificação das variantes. Uma integração futura deve registrar revisão,
licença de código, dados e pesos, além das obrigações de redistribuição.

## Pesquisas e o que sustentam

| Fonte primária | Implicação para o projeto | Limite de extrapolação |
| --- | --- | --- |
| [Skin-AE, EMBC 2024](https://pubmed.ncbi.nlm.nih.gov/40039522/) | Investigar exposição guiada por pele | Indexação em 2025 não muda o ano do congresso; resultados da câmera estudada não garantem desempenho em webcam sem controle manual |
| [Controle de exposição, CVPRW 2023](https://openaccess.thecvf.com/content/CVPR2023W/CVPM/papers/Odinaev_Optimizing_Camera_Exposure_Control_Settings_for_Remote_Vital_Sign_Measurements_CVPRW_2023_paper.pdf) | Comparar ganho, tempo de exposição e FPS | Configuração de baixa luz estudada não estabelece luminância ou FPS universais |
| [IEM, Biomedical Signal Processing and Control](https://doi.org/10.1016/j.bspc.2024.106963) | Avaliar aprimoramento específico para rPPG | Evidência de método baseado em Retinex não valida automaticamente Retinexformer ou Zero-DCE |
| [CHILL e baixa iluminação](https://www.nature.com/articles/s41746-025-02192-y) | Estratificar por luz e frequência cardíaca | Resultado por método e população; não prometer recuperação de qualquer vídeo escuro |
| [Roadmap clínico de 2026](https://doi.org/10.1038/s41746-026-02715-1) | Planejar validação externa e limites de uso | Testes de código não substituem avaliação clínica |
| [CPulse](https://doi.org/10.1109/TIM.2023.3303504) | Comparar pequenas regiões e sua qualidade | Método completo inclui outras etapas; escolher regiões só por SNR pode favorecer artefatos |
| [LGI](https://openaccess.thecvf.com/content_cvpr_2018_workshops/papers/w27/Pilz_Local_Group_Invariance_CVPR_2018_paper.pdf) | Projeção para reduzir componente dominante | A implementação experimental ainda precisa de comparação com vídeo real |
| [PBV](https://doi.org/10.1088/0967-3334/35/9/1913) | Usar assinatura de volume sanguíneo | Assinatura depende da captura; a variante adaptativa não deve ser apresentada como PBV calibrado |
| [OMIT](https://arxiv.org/html/2202.04101) | Projetar a componente temporal dominante via QR | A orientação de matriz da descrição foi preservada; variantes de bibliotecas devem ser identificadas |
| [Estudo de webcam on-line](https://doi.org/10.3758/s13428-024-02398-0) | Tratar 20 FPS como regra prática da avaliação | Não é revisão sistemática nem prova de piso físico universal; parte da referência foi obtida depois da gravação |
| [Artefatos de comunicação](https://arxiv.org/abs/2405.01230) | Comparar captura local e vídeo recebido | Reunião pública sem referência sincronizada pode testar execução, não precisão de BPM |
| [Comparação de compressão](https://doi.org/10.1016/j.bspc.2024.107445) | Avaliar codec, bitrate e resolução | Preservação depende da configuração; captura de tela não recupera informação removida pelo codec |
| [Confiança com movimento, 2026](https://doi.org/10.1007/s10916-026-02412-2) | Investigar qualidade supervisionada | AUC não equivale à precisão de BPM; seleção de classes por faixas de erro afeta a interpretação |
| [Resposta cardíaca refletida no olho](https://doi.org/10.1016/j.ijpsycho.2017.07.014) | Formular experimento ocular independente | Estudo com imagens infravermelhas e ECG; não demonstra medição confiável pela pupila de webcam RGB |
| [Micromovimento da cabeça, CVPR 2013](https://people.csail.mit.edu/mrub/vidmag/papers/Balakrishnan_Detecting_Pulse_from_2013_CVPR_paper.pdf) | Investigar video-BCG | Condições de cabeça estável não garantem robustez durante fala e movimentos voluntários |
| [Revisão de aprendizado profundo](https://pmc.ncbi.nlm.nih.gov/articles/PMC12181896/) | Organizar modelos e comparação entre datasets | Uma revisão não valida os pesos, a câmera ou a população utilizados aqui |
| [Revisão geral, Neurocomputing](https://doi.org/10.1016/j.neucom.2024.127282) | Organizar métodos, datasets e lacunas de avaliação | O conjunto de trabalhos revisados não estabelece precisão universal de webcam |
| [Estudo de robustez de 2020](https://www.sciencedirect.com/science/article/pii/S1051200420300828) | Candidato à reprodução na comparação de métodos | O valor de MAE atribuído no histórico não foi confirmado; não foi usado como meta demonstrada |

A página de [I-norm](https://www.mdpi.com/2079-9292/15/8/1683) apresentou bloqueio
de acesso em consultas desta revisão. A reprodução desse método fica pendente;
não foi promovido para o aplicativo com base em resumo ou título.

Os trabalhos recentes citados no histórico, como
[MS-rPPG](https://arxiv.org/abs/2606.21115),
[CanonicalPhys](https://arxiv.org/abs/2607.15995),
[Spatial Artifact Coherence](https://arxiv.org/abs/2606.04198),
[Deep Pulse Magnification](https://arxiv.org/abs/2405.02652),
[CameraPhys](https://arxiv.org/abs/2404.05003) e
[PRISM](https://arxiv.org/abs/2511.21903), são candidatos à comparação.
Datas de preprint não devem ser convertidas em publicação revisada por pares
sem conferir a versão editorial. Nenhum desses modelos foi executado nesta
revisão ou passou a fornecer leituras no aplicativo.

## Dados e próximos experimentos

MMPD, PURE, UBFC-rPPG, UBFC-Phys e CHILL são candidatos. A disponibilidade,
licença e forma de obter referência devem ser confirmadas para a versão usada.
Não foram baixados datasets volumosos nem solicitadas permissões em nome do
usuário. O manifesto exige procedência, mas preencher um campo não concede
autorização de uso. O próximo resultado científico depende de dados autorizados
e do [protocolo de avaliação](protocolo-validacao-real.md).
