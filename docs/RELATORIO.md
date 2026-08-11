# Medição de frequência cardíaca sem contato por fotopletismografia remota

Relatório técnico do projeto Cardiocam, disciplina de Processamento de Imagens e
Sinais.

## 1. Problema

Medir frequência cardíaca normalmente exige contato: eletrodos, uma pulseira, um
oxímetro no dedo. A pergunta deste trabalho é se dá para chegar ao mesmo número
usando só uma câmera comum e a luz que já existe no ambiente.

Dá, e o motivo é óptico. A cada sístole o coração empurra um volume de sangue
para os capilares da pele. Mais hemoglobina no caminho da luz significa mais
absorção e menos luz refletida de volta ao sensor. A pele, portanto, escurece e
clareia no ritmo do coração.

O problema é a escala do efeito. A variação de intensidade fica entre 0,1% e 1%,
frequentemente abaixo do ruído de leitura de um único pixel, e vem misturada com
variações de iluminação e movimento que são uma ou duas ordens de grandeza
maiores. O trabalho consiste em recuperar esse sinal.

## 2. Fundamentação

### 2.1 Por que o canal verde

A hemoglobina tem um máximo de absorção em torno de 540 nm, bem no meio da
resposta do filtro verde de um sensor Bayer. A luz vermelha penetra mais fundo
no tecido e volta com pouco contraste pulsátil; a azul é dominada por reflexão
superficial e por ruído. Verkruysse, Svaasand e Nelson (2008) mostraram que o
verde carrega a maior parte da informação, e é por isso que ele é a linha de
base contra a qual os outros métodos precisam se justificar.

### 2.2 O modelo de reflexão da pele

A luz que chega ao sensor tem duas parcelas. A **reflexão especular** volta da
superfície sem atravessar o tecido: carrega a cor da fonte de luz e nenhuma
informação de sangue. A **reflexão difusa** atravessa a pele, interage com a
hemoglobina e traz a modulação que interessa.

Movimento e variação de iluminação afetam principalmente a componente especular,
e o fazem de forma aproximadamente proporcional nos três canais. Essa é a
observação central: a perturbação é uma mudança de *intensidade*, enquanto o
pulso é uma mudança de *cor*, porque modula cada canal com um peso diferente.

Toda a família de métodos cromáticos explora essa assimetria.

### 2.3 CHROM

De Haan e Jeanne (2013) constroem duas projeções cromáticas a partir dos canais
normalizados pela própria média temporal:

```
X = 3R − 2G
Y = 1,5R + G − 1,5B
```

Ambas são filtradas na banda cardíaca e combinadas como `S = X − αY`, com
`α = σ(X)/σ(Y)`. O peso α é escolhido para que a distorção comum às duas
projeções se cancele na subtração.

Os coeficientes saem da suposição de um tom de pele padrão sob luz branca, o que
é a limitação do método: iluminação muito colorida desloca essa suposição.

### 2.4 POS

Wang et al. (2017) removem a necessidade de calibração. Em vez de coeficientes
ajustados a um tom de pele médio, definem um plano ortogonal à direção do tom de
pele no espaço RGB:

```
S1 =      G − B
S2 = −2R + G + B
```

Qualquer variação puramente de intensidade desloca a cor ao longo da direção do
tom de pele, e projetar no plano ortogonal a elimina por construção. O sinal
final é `S1 + (σ(S1)/σ(S2))·S2`.

Dois detalhes de implementação importam. A normalização é feita em sub-janelas
de cerca de 1,6 s deslizando sobre o sinal, de modo que a hipótese de tom de
pele constante só precisa valer por um instante; e as sub-janelas são somadas
com sobreposição, o que faz as bordas de uma compensarem as da outra.

### 2.5 ICA

Poh, McDuff e Picard (2010) tratam o problema como separação cega de fontes: os
três canais são três misturas de fontes independentes, uma das quais é o pulso.
A vantagem é dispensar modelo físico. A desvantagem, que os resultados deste
trabalho evidenciam, é a ambiguidade: o método não sabe qual componente é o
pulso, e qualquer critério de escolha pode ser enganado.

## 3. Metodologia

### 3.1 Da imagem ao sinal

A detecção de rosto usa a cascata de Haar de Viola e Jones (2001):
características retangulares calculadas em tempo constante via imagem integral,
selecionadas por AdaBoost e organizadas em cascata, de modo que a maioria das
janelas candidatas é descartada nos primeiros estágios. É de 2001, roda em CPU
sem esforço, e é suficiente para alguém sentado de frente para a câmera.

O parâmetro de escala da pirâmide foi definido por medição, não por hábito. Com
o passo de 1,1, a taxa de detecção sobre o conjunto de validação ficou em 64% a
80%; com 1,05, em 100%. O custo adicional é irrelevante porque o detector só
roda a cada dois quadros — entre eles, o rastreador reaproveita a caixa.

As regiões de interesse são a testa e as bochechas, definidas em coordenadas
relativas à caixa do rosto. Boca e olhos são excluídos de propósito: piscar e
falar produzem movimento exatamente na banda de frequência do coração, e esse é
o tipo de artefato que nenhuma filtragem posterior consegue remover.

A segmentação de pele usa limiar de crominância em YCrCb. A escolha do espaço de
cor tem uma consequência de correção, não de estética: a crominância da pele
humana ocupa uma faixa estreita e estável independentemente do tom, e o que
varia entre pessoas de pele clara e escura é sobretudo a luminância. Limiarizar
apenas em Cr e Cb torna a segmentação muito mais justa entre tons do que
limiarizar em RGB. A suíte verifica isso em oito tons.

A média espacial sobre os pixels de pele é o passo que viabiliza tudo. Como o
ruído de leitura é aproximadamente independente entre pixels, promediar N deles
reduz o desvio do ruído por √N. Com alguns milhares de pixels, uma variação de
0,1% consegue emergir.

### 3.2 Do sinal ao número

**Remoção de tendência.** Iluminação muda, a pessoa se aproxima, o ganho
automático da câmera atua. Isso gera uma tendência lenta que concentra energia
em baixa frequência e vaza para dentro da banda. Usamos o detrend por priores de
suavidade de Tarvainen, Ranta-aho e Karjalainen (2002), que estima a tendência
como solução de um problema de mínimos quadrados regularizado pela segunda
diferença.

**Reamostragem uniforme.** Webcam não entrega quadros em intervalo constante; o
"30 fps" é nominal. Os instantes são medidos na chegada de cada quadro e o sinal
é reinterpolado numa grade regular antes da FFT.

**Filtragem.** Butterworth passa-faixa de ordem 4 entre 0,7 e 4 Hz (42 a
240 bpm), em seções de segunda ordem por estabilidade numérica, aplicado para
frente e para trás. A filtragem bidirecional cancela o atraso de grupo, o que
importa porque os picos do pulso não podem sair deslocados no tempo se
quisermos calcular variabilidade.

**Estimativa da frequência.** A resolução bruta de uma FFT é fs/N: numa janela
de 10 s isso dá 0,1 Hz, ou seja 6 bpm, grosseiro demais para exibir. Resolvemos
em duas etapas. Primeiro, preenchimento com zeros, que não cria informação nova
mas interpola o espectro numa grade fina o bastante para revelar o formato do
lóbulo. Segundo, interpolação parabólica em escala logarítmica sobre os três
pontos ao redor do pico. Como a janela de Hann tem lóbulo principal simétrico, o
vértice da parábola cai praticamente sobre a frequência verdadeira.

O erro residual desse estimador, medido sobre senoides puras de 45 a 220 bpm,
ficou abaixo de 0,21 bpm no pior caso.

**Qualidade.** A relação sinal-ruído é calculada no espectro, considerando sinal
a energia próxima da fundamental e do primeiro harmônico e ruído todo o resto da
banda. O harmônico entra porque a onda de pulso não é senoidal: a subida é
rápida e a descida lenta, o que sempre deposita energia em 2f.

### 3.3 Validação

Medir uma pessoa real não prova nada sem um oxímetro ao lado para comparar. A
validação usa um simulador que reproduz a física do fenômeno e no qual a
frequência é escolhida por nós:

- pulso construído com harmônicos, para ter o formato de um pletismograma;
- modulação com peso diferente por canal (R 0,30, G 1,00, B 0,55);
- ruído de sensor por pixel, independente entre pixels;
- deriva e oscilação de iluminação, comuns aos três canais;
- movimento da cabeça e irregularidade na temporização dos quadros.

O rosto renderizado é detectável pela cascata de Haar, o que permite que os
testes de ponta a ponta exercitem o pipeline inteiro, incluindo a detecção, e
não apenas a parte de sinais.

Um erro cometido durante o desenvolvimento vale registro porque ilustra o ponto
central do trabalho. A primeira versão do simulador aplicava o pulso como um
fator multiplicativo único sobre a cor da pele, igual nos três canais. CHROM e
POS passaram a devolver sinal nulo, e a causa não era um defeito neles: uma
variação idêntica em todos os canais é, por definição, o que esses métodos
foram construídos para cancelar. O simulador é que estava fisicamente errado.
Corrigir o peso por canal fez os dois funcionarem imediatamente.

## 4. Resultados

Bateria de 56 cenários, de 48 a 180 bpm, sete condições cada.

| Algoritmo | Erro médio (bpm) | RMSE (bpm) | Erro máximo (bpm) | Acerto ±3 bpm |
| --- | ---: | ---: | ---: | ---: |
| VERDE | 12,09 | 22,46 | 42,09 | 71% |
| CHROM | 0,02 | 0,05 | 0,19 | 100% |
| POS | 0,02 | 0,03 | 0,18 | 100% |
| ICA | 12,01 | 22,45 | 42,00 | 71% |

| Cenário | VERDE | CHROM | POS | ICA |
| --- | ---: | ---: | ---: | ---: |
| ideal | 0,02 | 0,00 | 0,00 | 0,01 |
| pulso fraco | 0,35 | 0,03 | 0,02 | 0,02 |
| ruído alto | 0,22 | 0,10 | 0,06 | 0,04 |
| deriva de iluminação | 0,03 | 0,01 | 0,01 | 0,01 |
| interferência na banda | 42,01 | 0,01 | 0,01 | 42,00 |
| interferência forte | 42,00 | 0,01 | 0,01 | 42,00 |
| captura irregular | 0,03 | 0,02 | 0,02 | 0,01 |

### 4.1 Discussão

**Em condição favorável, o método simples basta.** Nas quatro primeiras
condições os quatro algoritmos são equivalentes na prática. Isso merece ser dito
porque contraria a expectativa de que o método mais elaborado seja sempre
melhor: se a iluminação é estável e a pessoa está parada, o canal verde resolve.

**A deriva lenta de iluminação não separa nada.** Era o cenário que
intuitivamente pareceria difícil, e não é: uma rampa é removida pelo detrend e
pelo passa-faixa antes de qualquer algoritmo agir. Todos empatam.

**A interferência dentro da banda separa tudo.** Quando a oscilação de
iluminação cai entre 0,7 e 4 Hz, filtrar deixa de ajudar, porque a perturbação
está exatamente onde o sinal está. O GREEN erra 42 bpm, que é precisamente a
distância entre o pulso e a interferência: ele trava na perturbação. Olhando só
a intensidade de um canal, não existe informação capaz de distinguir "chegou
mais sangue" de "chegou mais luz". CHROM e POS distinguem porque o sangue muda a
proporção entre canais e a iluminação não.

**O ICA falha pelo mesmo valor, por outro motivo.** Ele separa as fontes bem,
mas precisa decidir qual das três componentes é o pulso. O critério usado aqui,
o pico espectral mais destacado, escolhe a interferência, que sendo senoidal
pura é mais "limpa" que um pulso fisiológico com harmônicos. É a ambiguidade
intrínseca da separação cega, e não se resolve com ajuste de parâmetro.

**Consequência prática:** o padrão do sistema é POS. Ele empata com o CHROM em
precisão, dispensa a calibração de tom de pele e teve o menor RMSE.

### 4.2 Verificação

A suíte tem mais de 1.700 casos, todos executando o código real. Além da
precisão, três testes verificam a propriedade que mais importa num instrumento
de medição, que é saber recusar: parede lisa filmada, imagem saturada em 255 e
vídeo mais curto que a janela de análise não podem produzir valor nenhum.

Essa exigência apareceu de um defeito encontrado pelos próprios testes. Com
entrada perfeitamente constante, o que sobra depois da filtragem é erro de
arredondamento; o espectro disso tem um pico como qualquer outro, e a relação
sinal-ruído resultava em infinito porque o denominador era zero. O sistema
reportava um valor arbitrário com confiança máxima. A correção foi rejeitar
sinais cuja amplitude é numericamente indistinguível de zero em relação à escala
da entrada.

## 4.3 O que a medição real revelou

Uma medição com webcam comum devolveu 73 bpm contra 89 de um relógio de pulso,
com relação sinal-ruído de 1,2 dB. O sistema classificou a leitura como
confiança baixa, ou seja, sinalizou corretamente que não confiava no próprio
número, mas o valor exibido estava errado.

A investigação levou aos controles automáticos da câmera, e a um buraco na
fundamentação usada até então. A exposição automática compensa exatamente a
variação que queremos medir: quando a pele escurece por causa do pulso, o ganho
sobe e apaga parte do sinal. O balanço de branco automático é pior, porque
ajusta cada canal de cor separadamente.

Esse último ponto é o que importa teoricamente. CHROM e POS partem da hipótese
de que a distorção é proporcional nos três canais, e é dessa hipótese que vem
toda a robustez deles. Um ganho por canal viola a hipótese e passa direto pela
projeção cromática. Ou seja, existia uma classe inteira de perturbação que
nenhum dos algoritmos implementados cobria.

A saída mais direta seria desligar os automatismos. Na câmera usada, todas as
propriedades de exposição e balanço de branco leem -1.0 e toda escrita devolve
falso, nos dois backends do Windows. A câmera não expõe esses controles, e não
há o que fazer por software do lado da captura.

A solução adotada usa o fundo do quadro como referência. A parede atrás da
pessoa não tem pulso: tudo que oscila nela é iluminação ou ganho de câmera. Como
rosto e fundo recebem a mesma luz, o fundo mede a perturbação diretamente, e o
que for explicável por ele é removido do sinal do rosto por mínimos quadrados
com alguns atrasos, canal a canal, antes do algoritmo rPPG.

| Cenário com balanço de branco oscilando na banda cardíaca | Acertos em 3 bpm |
| --- | ---: |
| Sem rectificação | 1 de 16 |
| Com rectificação | 16 de 16 |

Duas tentativas anteriores foram descartadas por medição, e registrá-las importa
tanto quanto registrar a que funcionou.

A primeira foi pontuar cada candidata a pico somando a energia encontrada no
dobro da frequência, na expectativa de que o pulso, por ter harmônico, vencesse
artefatos senoidais. A medição mostrou que a ideia premia subharmônicos: uma
interferência a 48 bpm recebe o bônus do próprio pulso a 96 bpm. Na faixa em que
o sistema já acertava tudo, a taxa caiu de 100% para 75%. Descartada.

A segunda foi uma trava que devolvia o sinal original quando a rectificação
apagava quase tudo, pensada para proteger contra um fundo casualmente
correlacionado com o pulso. O efeito colateral era pior que o problema: se o
fundo explica todo o sinal do rosto, então não havia pulso ali, e devolver o
original faria o sistema reportar a interferência como batimento. A trava foi
retirada, e agora a verificação de sinal degenerado recusa a janela.

## 5. Limitações

- Não é dispositivo médico e não serve para diagnóstico.
- É impossível medir a partir de uma foto. Frequência é uma grandeza temporal e
  uma imagem isolada não tem eixo do tempo. São necessários ao menos 10 s.
- Rosto de perfil derruba a cascata de Haar. Um detector baseado em rede
  resolveria, ao custo de um arquivo de pesos externo.
- Movimento amplo continua sendo o limite. CHROM e POS resistem a variação de
  iluminação, não a alguém que sai do enquadramento.
- Vídeo comprimido degrada bastante o sinal. Codecs de videochamada usam
  subamostragem de crominância 4:2:0 e o controle de taxa descarta justamente
  variações sutis em regiões homogêneas.

## 6. Trabalhos futuros

Marcos faciais no lugar da caixa retangular dariam regiões que acompanham a
expressão. Compensação de movimento por fluxo óptico atacaria a limitação
principal. Uma validação contra oxímetro de dedo permitiria reportar erro contra
padrão-ouro em vez de contra simulação. E o critério de seleção de componente do
ICA pode ser melhorado exigindo presença de harmônico, já que um pulso real tem
energia em 2f e uma interferência senoidal não.

## Referências

Verkruysse, W., Svaasand, L. O., Nelson, J. S. (2008). Remote plethysmographic
imaging using ambient light. *Optics Express*, 16(26).

Poh, M. Z., McDuff, D. J., Picard, R. W. (2010). Non-contact, automated cardiac
pulse measurements using video imaging and blind source separation. *Optics
Express*, 18(10).

de Haan, G., Jeanne, V. (2013). Robust pulse rate from chrominance-based rPPG.
*IEEE Transactions on Biomedical Engineering*, 60(10).

Wang, W., den Brinker, A. C., Stuijk, S., de Haan, G. (2017). Algorithmic
principles of remote PPG. *IEEE Transactions on Biomedical Engineering*, 64(7).

Viola, P., Jones, M. (2001). Rapid object detection using a boosted cascade of
simple features. *CVPR*.

Tarvainen, M. P., Ranta-aho, P. O., Karjalainen, P. A. (2002). An advanced
detrending method with application to HRV analysis. *IEEE Transactions on
Biomedical Engineering*, 49(2).

Chai, D., Ngan, K. N. (1999). Face segmentation using skin-color map in
videophone applications. *IEEE Transactions on Circuits and Systems for Video
Technology*, 9(4).
