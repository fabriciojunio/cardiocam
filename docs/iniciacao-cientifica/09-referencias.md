# Referências

Organizadas por função no projeto, não em ordem alfabética, porque o que
interessa na leitura é **para que cada trabalho serve aqui**. A lista em formato
ABNT para o documento final vem no fim.

Onde o trabalho reporta um número que usamos como referência, o número está
citado. Isso é deliberado: bibliografia sem número é lista de nomes.

---

## 1. Os quatro métodos implementados

**VERKRUYSSE, W.; SVAASAND, L. O.; NELSON, J. S.** Remote plethysmographic
imaging using ambient light. *Optics Express*, v. 16, n. 26, p. 21434-21445,
2008.

O artigo que mostrou que dá para fazer isso com luz ambiente e câmera comum.
É a origem do método GREEN e a fonte da faixa de amplitude que usamos como
realista: **0,1% a 1%** de variação de intensidade. Também é a origem da escolha
do canal verde, por causa do máximo de absorção da hemoglobina perto de 540 nm.

**DE HAAN, G.; JEANNE, V.** Robust pulse rate from chrominance-based rPPG.
*IEEE Transactions on Biomedical Engineering*, v. 60, n. 10, p. 2878-2886, 2013.

O método CHROM. Combina duas projeções cromáticas para cancelar a reflexão
especular. **A hipótese de tom de pele padronizado está aqui**, e é ela que a
hipótese H1 do projeto ataca.

**WANG, W. et al.** Algorithmic principles of remote PPG. *IEEE Transactions on
Biomedical Engineering*, v. 64, n. 7, p. 1479-1491, 2017.

O método POS, e mais que isso: a formulação unificada que mostra os métodos
anteriores como casos particulares de projeção. É a referência teórica central do
projeto, porque a direção do tom de pele aparece explícita na construção do
plano, e é o que permite raciocinar sobre quando a projeção falha.

**POH, M.-Z.; McDUFF, D. J.; PICARD, R. W.** Non-contact, automated cardiac
pulse measurements using video imaging and blind source separation. *Optics
Express*, v. 18, n. 10, p. 10762-10774, 2010.

O método ICA. Não assume tom de pele, e em troca herda a ambiguidade da
separação cega: o critério de escolha da componente pode preferir uma
interferência limpa a um pulso real, que é exatamente o que medimos na seção 2.2
dos resultados preliminares.

---

## 2. Fundamentação física

**SHAFER, S. A.** Using color to separate reflection components. *Color
Research and Application*, v. 10, n. 4, p. 210-218, 1985.

O modelo de reflexão dicromática, que separa a componente difusa da especular.
É a base física da seção 3.2 do projeto: a difusa carrega o pulso e tem a cor da
pele; a especular não carrega nada e tem a cor da luz. **Essa distinção é o que
torna a hipótese H1 formulável.**

**TARVAINEN, M. P.; RANTA-AHO, P. O.; KARJALAINEN, P. A.** An advanced
detrending method with application to HRV analysis. *IEEE Transactions on
Biomedical Engineering*, v. 49, n. 2, p. 172-175, 2002.

A remoção de tendência por priores de suavidade, já implementada no sistema. É o
que elimina a deriva lenta de iluminação antes da análise espectral.

---

## 3. Métodos aprendidos, como referência superior

**CHEN, W.; McDUFF, D.** DeepPhys: video-based physiological measurement using
convolutional attention networks. In: *European Conference on Computer Vision
(ECCV)*, 2018.

A primeira arquitetura ponta a ponta com atenção que virou linha de base da
área.

**YU, Z.; LI, X.; ZHAO, G.** Remote photoplethysmograph signal measurement from
facial videos using spatio-temporal networks. In: *British Machine Vision
Conference (BMVC)*, 2019.

O PhysNet. Entra como referência da etapa 8 do plano, não como ponto de partida.

**LIU, X. et al.** rPPG-Toolbox: deep remote PPG toolbox. In: *Advances in
Neural Information Processing Systems (NeurIPS)*, 2023.

**A referência mais importante do projeto para fins de protocolo.** É o
arcabouço de avaliação padronizado da área, com os métodos não supervisionados
(ICA, POS, CHROM, GREEN, LGI, PBV) e as métricas (erro absoluto médio, RMSE,
MAPE, Pearson) implementados sobre seis conjuntos.

Os números que usamos como portão de qualidade saem daqui, em UBFC-rPPG:

| Método | Erro absoluto médio |
| --- | ---: |
| POS | **3,67 bpm** |
| CHROM | **5,77 bpm** |

Disponível em: <https://github.com/ubicomplab/rPPG-Toolbox>.

---

## 4. Conjuntos de dados

**BOBBIA, S. et al.** Unsupervised skin tissue segmentation for remote
photoplethysmography. *Pattern Recognition Letters*, v. 124, p. 82-90, 2019.

O conjunto **UBFC-rPPG**. Participantes estáticos, predominantemente fototipos
2 e 3 de Fitzpatrick. É o conjunto mais citado da área e é também a razão de o
problema de tom de pele ter ficado invisível por tanto tempo.

**STRICKER, R.; MÜLLER, S.; GROSS, H.-M.** Non-contact video-based pulse rate
measurement on a mobile service robot. In: *IEEE International Symposium on
Robot and Human Interactive Communication (RO-MAN)*, 2014.

O conjunto **PURE**. Inclui movimento de cabeça, o que o torna o conjunto
público mais relevante para o objetivo de movimento. Também concentrado em
fototipos 2 e 3.

**TANG, J. et al.** MMPD: multi-domain mobile video physiology dataset. In:
*IEEE Engineering in Medicine and Biology Conference (EMBC)*, 2023.

**O conjunto que torna o objetivo de tom de pele possível.** 11 horas de
gravação de telefone celular, **33 participantes**, **fototipos 3 a 6**, quatro
atividades (parado, rotação de cabeça, fala e caminhada) e quatro condições de
iluminação (LED alto, LED baixo, incandescente e luz natural).

É a referência direta do nosso protocolo de coleta local: as cinco condições da
atividade 10 do plano espelham as do MMPD de propósito, para que os conjuntos
sejam comparáveis. E é a origem do nosso número de 30 participantes.

---

## 5. Movimento e robustez

**ZHAO, B. et al.** Toward motion robustness: a masked attention regularization
framework in remote photoplethysmography. 2024. Disponível em:
<https://arxiv.org/pdf/2407.06653>.

O MAR-rPPG. A fonte dos números que usamos para dimensionar o que é um resultado
bom sob movimento:

| Condição no MMPD | Erro absoluto médio |
| --- | ---: |
| estático | **0,87 bpm** |
| com movimento | **2,83 bpm** |

A degradação por um fator de 3,25 entre estático e movimento, **no melhor método
disponível**, é a medida de quão aberto o problema está.

**MS-rPPG: multi-spectral state space model for remote photoplethysmography in
driver monitoring systems.** 2026. Disponível em:
<https://arxiv.org/html/2606.21115v1>.

Cenário de direção veicular, que é movimento severo: erro de **9,60 bpm** com
movimento grande e **11,80 bpm** com movimento pequeno. Serve de limite superior
realista: em condição ruim o estado da arte erra quase 10 bpm.

**CanonicalPhys: pose-robust remote photoplethysmography via canonical-space
priors.** 2026. Disponível em: <https://arxiv.org/pdf/2607.15995>.

Aborda robustez a pose, que é o mecanismo de sombreado por pose da nossa seção
3.2.

**PRISM**, método não supervisionado. 2026.

Estado da arte entre métodos não supervisionados: **0,77 bpm** em PURE e
**0,66 bpm** em UBFC-rPPG, com acerto de 97,3% e 97,5% a 5 bpm. É o teto do que
se consegue sem rótulo.

---

## 6. Tom de pele e equidade

**NOWARA, E. M.; McDUFF, D.; VELOSO, A.** A meta-analysis of the impact of skin
tone and gender on non-contact photoplethysmography measurements. In: *IEEE/CVF
Conference on Computer Vision and Pattern Recognition Workshops (CVPRW)*, 2020.

A meta-análise que estabeleceu a questão como problema mensurável e não como
suspeita.

**DASARI, A. et al.** Evaluation of biases in remote photoplethysmography
methods. *npj Digital Medicine*, v. 4, n. 91, 2021.

Avaliação sistemática de viés nos métodos de rPPG.

**Camera-based remote physiology sensing for hundreds of subjects across skin
tones.** 2024. Disponível em: <https://arxiv.org/pdf/2404.05003>.

Escala grande e cobertura ampla de fototipos. É a referência metodológica para o
protocolo de avaliação estratificada por grupo de fototipo, que é o que a seção
3.4 do projeto adota.

**Diverse R-PPG: camera-based heart rate estimation for diverse subject
skin-tones and scenes.** 2020. Disponível em:
<https://arxiv.org/pdf/2010.12769>.

**FITZPATRICK, T. B.** The validity and practicality of sun-reactive skin types
I through VI. *Archives of Dermatology*, v. 124, n. 6, p. 869-871, 1988.

A escala de fototipos, que é o instrumento de classificação usado na coleta
local, por autoclassificação com escala visual conforme o procedimento da área.

---

## 7. Compressão de vídeo

**McDUFF, D.; BLACKFORD, E. B.; ESTEPP, J. R.** The impact of video compression
on remote cardiac pulse measurement using imaging photoplethysmography. In:
*IEEE International Conference on Automatic Face and Gesture Recognition (FG)*,
2017.

**RAPCZYNSKI, M.; WERNER, P.; AL-HAMADI, A.** Effects of video encoding on
camera-based heart rate estimation. *IEEE Transactions on Biomedical
Engineering*, 2019.

As duas referências do objetivo 7. O achado central para o nosso caso: a
compressão H.264 degrada a relação sinal-ruído do rPPG, com impacto maior em
resoluções baixas e na subamostragem de crominância, afetando sobretudo os
canais **azul e vermelho** em amplitude, ruído de alta frequência e
descontinuidade de traço.

**Deep pulse-signal magnification for remote heart rate estimation in compressed
videos.** *Expert Systems with Applications*, 2026. Disponível em:
<https://arxiv.org/pdf/2405.02652>.

Trabalho recente sobre recuperar o sinal depois da compressão, que é o estado da
arte do problema do objetivo 7.

**Spatial artifact coherence determines codec robustness in patch-based rPPG.**
2026. Disponível em: <https://arxiv.org/pdf/2606.04198>.

---

## 8. Normas e regulamentação

**BRASIL. Conselho Nacional de Saúde.** Resolução nº 466, de 12 de dezembro de
2012. Diretrizes e normas regulamentadoras de pesquisas envolvendo seres
humanos. Brasília, 2012.

**BRASIL.** Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de
Dados Pessoais. Brasília, 2018.

O art. 5º, II, classifica dado referente à saúde como **dado pessoal sensível**,
que é o fundamento da seção 3.8 do projeto.

**UNESP. Pró-Reitoria de Pesquisa.** Programa Institucional de Iniciação
Científica. Disponível em: <https://prope.unesp.br/pibic/>.

**FAPESP.** Bolsa de Iniciação Científica, norma vigente a partir de
01/09/2026. Disponível em: <https://fapesp.br/bolsas/ic>.

---

## Lista em ABNT, em ordem alfabética

> Para colar no documento final. Confira a formatação exigida pela unidade: há
> variação no uso de negrito e na abreviação de nomes.

BOBBIA, S. et al. Unsupervised skin tissue segmentation for remote
photoplethysmography. **Pattern Recognition Letters**, v. 124, p. 82-90, 2019.

BRASIL. Conselho Nacional de Saúde. **Resolução nº 466, de 12 de dezembro de
2012**. Brasília, 2012.

BRASIL. **Lei nº 13.709, de 14 de agosto de 2018**: Lei Geral de Proteção de
Dados Pessoais. Brasília, 2018.

CHEN, W.; McDUFF, D. DeepPhys: video-based physiological measurement using
convolutional attention networks. In: **European Conference on Computer
Vision**, 2018.

DASARI, A. et al. Evaluation of biases in remote photoplethysmography methods.
**npj Digital Medicine**, v. 4, n. 91, 2021.

DE HAAN, G.; JEANNE, V. Robust pulse rate from chrominance-based rPPG. **IEEE
Transactions on Biomedical Engineering**, v. 60, n. 10, p. 2878-2886, 2013.

FITZPATRICK, T. B. The validity and practicality of sun-reactive skin types I
through VI. **Archives of Dermatology**, v. 124, n. 6, p. 869-871, 1988.

LIU, X. et al. rPPG-Toolbox: deep remote PPG toolbox. In: **Advances in Neural
Information Processing Systems**, 2023.

McDUFF, D.; BLACKFORD, E. B.; ESTEPP, J. R. The impact of video compression on
remote cardiac pulse measurement using imaging photoplethysmography. In: **IEEE
International Conference on Automatic Face and Gesture Recognition**, 2017.

NOWARA, E. M.; McDUFF, D.; VELOSO, A. A meta-analysis of the impact of skin
tone and gender on non-contact photoplethysmography measurements. In: **IEEE/CVF
Conference on Computer Vision and Pattern Recognition Workshops**, 2020.

POH, M.-Z.; McDUFF, D. J.; PICARD, R. W. Non-contact, automated cardiac pulse
measurements using video imaging and blind source separation. **Optics
Express**, v. 18, n. 10, p. 10762-10774, 2010.

RAPCZYNSKI, M.; WERNER, P.; AL-HAMADI, A. Effects of video encoding on
camera-based heart rate estimation. **IEEE Transactions on Biomedical
Engineering**, 2019.

SHAFER, S. A. Using color to separate reflection components. **Color Research
and Application**, v. 10, n. 4, p. 210-218, 1985.

STRICKER, R.; MÜLLER, S.; GROSS, H.-M. Non-contact video-based pulse rate
measurement on a mobile service robot. In: **IEEE International Symposium on
Robot and Human Interactive Communication**, 2014.

TANG, J. et al. MMPD: multi-domain mobile video physiology dataset. In: **IEEE
Engineering in Medicine and Biology Conference**, 2023.

TARVAINEN, M. P.; RANTA-AHO, P. O.; KARJALAINEN, P. A. An advanced detrending
method with application to HRV analysis. **IEEE Transactions on Biomedical
Engineering**, v. 49, n. 2, p. 172-175, 2002.

VERKRUYSSE, W.; SVAASAND, L. O.; NELSON, J. S. Remote plethysmographic imaging
using ambient light. **Optics Express**, v. 16, n. 26, p. 21434-21445, 2008.

WANG, W. et al. Algorithmic principles of remote PPG. **IEEE Transactions on
Biomedical Engineering**, v. 64, n. 7, p. 1479-1491, 2017.

YU, Z.; LI, X.; ZHAO, G. Remote photoplethysmograph signal measurement from
facial videos using spatio-temporal networks. In: **British Machine Vision
Conference**, 2019.

ZHAO, B. et al. **Toward motion robustness**: a masked attention regularization
framework in remote photoplethysmography. 2024.

---

## Nota sobre as referências de 2026

Os trabalhos de 2026 citados (MS-rPPG, CanonicalPhys, PRISM) foram levantados
em 04/10/2026 e estão em repositório de pré-publicação. **Antes de citar no
documento final, confira se foram publicados em evento ou periódico** e
atualize a referência. Pré-publicação citada como se fosse publicação revisada é
erro que pega mal em banca e em parecer.

A atividade 1 do plano de trabalho prevê revisita da bibliografia no mês 10
exatamente por isso.
