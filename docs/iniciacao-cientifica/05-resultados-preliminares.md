# Resultados preliminares

Este documento existe porque muda a natureza da proposta. Um projeto de IC
normalmente começa com uma ideia e um cronograma. Aqui o instrumento já está
construído, testado e medido, e o cronograma começa do experimento, não da
implementação.

Todos os números abaixo saem de script versionado e são reproduzíveis com um
comando. Nenhum é estimativa.

## 1. O que já está implementado

Sistema completo em Python, arquitetura em camadas, sem dependência de serviço
externo e sem requisição de rede no caminho de medição.

| Camada | Conteúdo |
| --- | --- |
| Domínio | entidades, tipo `Resultado` e erros; não conhece OpenCV nem entrada e saída |
| Visão | detecção de rosto em cascata de Haar, rastreamento com rejeição de salto, âncora nos olhos, segmentação de pele, regiões de interesse, medida do fundo |
| Sinais | remoção de tendência por priores de suavidade, passa-faixa Butterworth, reamostragem uniforme, análise espectral com refino de pico, detecção de picos, rectificação por referência |
| rPPG | os quatro algoritmos, com a mesma interface |
| Pipeline | orquestração da janela deslizante até o número |
| Fontes | webcam, arquivo de vídeo, **captura de tela** e gerador sintético |
| Interface | linha de comando e janela gráfica com indicadores |
| Qualidade | características da janela, modelo bayesiano de confiabilidade e abstenção com cobertura declarada |

**Os quatro algoritmos foram implementados do zero**, a partir dos artigos
originais, e não importados de biblioteca. Isso é relevante para o projeto
porque o experimento de movimento precisa ligar e desligar partes internas de
cada método, o que uma biblioteca fechada não permite.

## 2. Validação por simulação

A decisão metodológica que sustenta tudo: **medir alguém de verdade não prova
que o sistema está certo**, porque não se sabe o valor correto sem uma
referência ao lado. O gerador sintético escolhe a frequência, então o erro é
mensurável com exatidão.

O simulador reproduz a física, não um desenho animado: pulso não senoidal
montado com harmônicos, ganho por canal proporcional à absorção da hemoglobina,
ruído por pixel independente, deriva e tremor de iluminação, e irregularidade de
temporização da captura.

### 2.1 Resultado sobre 56 cenários, de 48 a 180 bpm

| Algoritmo | Erro médio (bpm) | RMSE (bpm) | Acerto a ±3 bpm |
| --- | ---: | ---: | ---: |
| GREEN | 12,09 | 22,46 | 71% |
| CHROM | 0,02 | 0,05 | 100% |
| POS | 0,02 | 0,03 | 100% |
| ICA | 12,01 | 22,45 | 71% |

**Leia esta tabela com desconfiança, e isso é parte do resultado.** Erro de 0,02
bpm não é desempenho de sistema de rPPG: é a assinatura de um cenário fácil
demais. A literatura reporta 3,67 bpm para o POS em dados reais. A diferença de
duas ordens de grandeza é exatamente o que a IC vai investigar, e saber disso
antes de começar é mais valioso que o número bonito.

### 2.2 Onde os métodos se separam

Erro médio por cenário:

| Cenário | GREEN | CHROM | POS | ICA |
| --- | ---: | ---: | ---: | ---: |
| ideal | 0,02 | 0,00 | 0,00 | 0,01 |
| pulso fraco | 0,35 | 0,03 | 0,02 | 0,02 |
| ruído alto | 0,22 | 0,10 | 0,06 | 0,04 |
| deriva de iluminação | 0,03 | 0,01 | 0,01 | 0,01 |
| **interferência na banda** | **42,01** | 0,01 | 0,01 | **42,00** |
| interferência forte | 42,00 | 0,01 | 0,01 | 42,00 |
| captura irregular | 0,03 | 0,02 | 0,02 | 0,01 |

A linha que informa é a da interferência dentro da banda cardíaca. Todos empatam
quando a perturbação é uma rampa lenta de iluminação, porque a remoção de
tendência e o passa-faixa a eliminam antes de qualquer algoritmo agir. **O que
separa os métodos é oscilação de luz que cai dentro de 0,7 a 4 Hz**, onde
filtrar não adianta.

Ali o GREEN erra 42 bpm, que é exatamente a distância entre o pulso e a
interferência: ele trava na perturbação, porque olhando só o brilho do canal
verde não existe como distinguir "chegou mais sangue" de "chegou mais luz".
CHROM e POS distinguem porque o sangue muda a **cor** enquanto a iluminação muda
os três canais na mesma proporção.

O ICA erra o mesmo valor por motivo diferente e conhecido: ele separa as fontes
corretamente, mas precisa escolher qual componente é o pulso, e escolhe a de
espectro mais limpo. Uma interferência senoidal forte é mais limpa que um pulso
real. É a ambiguidade intrínseca da separação cega.

**Esse achado é o que gerou a hipótese H1 do projeto.** Se a robustez de CHROM e
POS vem de supor que a distorção é igual nos três canais, então uma distorção
que **não** é igual nos três canais deve derrubá-los. O reflexo especular é
exatamente isso, e é o que o movimento produz.

### 2.3 Varredura de amplitude: o que acontece com pulso realista

Medido em 04/10/2026. O simulador usa 2% de variação relativa, e pele real fica
entre 0,1% e 1%. A varredura mostra o que a diferença custa, com o POS e com
ruído de sensor de webcam comum:

| Amplitude do pulso | Janelas medidas | Janelas descartadas | SNR (dB) | Erro (bpm) |
| ---: | ---: | ---: | ---: | ---: |
| 2,0% | 11 | 0 | 8,8 | 0,04 |
| 1,0% | 11 | 0 | 7,9 | 0,06 |
| 0,5% | 11 | 0 | 5,5 | 0,03 |
| 0,3% | 8 | 3 | 4,4 | 0,15 |
| 0,2% | 6 | 5 | 2,2 | 0,21 |
| 0,1% | 0 | 11 | sem medida | sem medida |

E os quatro algoritmos em amplitude realista de 0,3%:

| Algoritmo | Janelas medidas | Janelas descartadas | SNR (dB) | Erro (bpm) |
| --- | ---: | ---: | ---: | ---: |
| GREEN | **0** | 11 | sem medida | sem medida |
| CHROM | 7 | 4 | 3,0 | 0,85 |
| POS | 8 | 3 | 4,4 | 0,15 |
| ICA | 9 | 2 | 2,8 | 0,48 |

Dois achados aqui, e os dois entram no projeto:

1. **A cobertura cai antes do erro subir.** Em 0,1% o sistema para de responder
   em vez de responder errado, o que é o comportamento desejado, mas significa
   que cobertura tem de ser relatada junto com erro em qualquer comparação. É a
   razão de a métrica estar no método.
2. **O GREEN não mede nada em amplitude realista.** Ele não erra: ele recusa.
   Comparar métodos só pelo erro das janelas aceitas esconderia isso por
   completo.

## 3. Testes automatizados

**2.212 casos em Python**, e nenhum usa simulacro no lugar do
código real. A estratégia é a mesma em todos os níveis: gerar um sinal cuja
frequência verdadeira foi escolhida por nós, rodar o sistema de verdade e
conferir o que sai.

| Nível | Casos | O que exercita |
| --- | ---: | --- |
| Unidade | 1.499 | resposta em frequência do filtro medida em dezenas de frequências; recuperação de senoides varrendo 45 a 220 bpm em passos de 2,5 bpm; remoção de tendência; rectificação; detecção de picos; geometria; **segmentação de pele em oito tons diferentes** |
| Integração | 601 | os quatro algoritmos sobre séries modeladas fisicamente, variando tom de pele, taxa de quadros, amplitude, ruído e interferência; pipeline, fontes, interface, linha de comando e ajustes de câmera |
| Ponta a ponta | 98 | vídeo renderizado quadro a quadro, cascata de Haar procurando o rosto de fato, até o número final |

Cobertura de 87%. O que fica fora é quase todo o código que só executa com
hardware presente: abrir a webcam e o laço da janela gráfica. O núcleo de sinais
e de visão fica entre 88% e 100%.

**Três testes existem para provar que o sistema sabe dizer "não sei"**, que é o
requisito mais importante de um medidor: parede lisa filmada, imagem saturada em
255 e vídeo mais curto que a janela não podem produzir nenhum valor.

## 4. Dois defeitos achados e corrigidos em 04/10/2026

Entram aqui porque são evidência do método de trabalho, e porque o segundo
explica por que a medição com câmera de verdade vinha ruim.

### 4.1 O controle automático de exposição continuava ligado

A função que desliga exposição e balanço de branco automáticos da câmera tentava
três valores em sequência, `(0,25, 0,0, 1,0)`, parando no primeiro que a câmera
aceitasse.

Dois problemas, e os dois são sérios:

**O valor 1,0 liga a exposição automática** na convenção do Media Foundation,
que é o primeiro backend tentado no Windows. A função que existia para desligar o
automático podia ligá-lo.

**O sucesso era decidido pelo retorno de `set`**, que informa apenas que o
backend aceitou a chamada, não que o valor pegou. Câmera que aceita e ignora é
comum, e o comportamento varia entre backends. O sistema anunciava "automáticos
travados" sem ter travado nada, e a interface repetia isso para o usuário.

Isso importa muito para a medição: os dois controles trabalham exatamente contra
o que se quer medir. Quando a pele escurece por causa do pulso, a exposição
automática clareia a imagem e apaga parte do sinal; e o balanço de branco
automático aplica ganho **diferente por canal**, criando variação de cor que
CHROM e POS não cancelam, justamente porque eles supõem distorção igual nos três
canais.

**Correção:** candidatos reduzidos a `(0,25, 0,0)`, confirmação por leitura de
volta do valor, e relato honesto quando não foi possível travar. Mais a fixação
de um tempo de exposição ao passar para manual, porque manual sem tempo definido
herda o último valor escolhido pelo automático, que pode ser o de um quadro
escuro.

**Nove testes novos** cobrem a função, com câmeras falsas que reproduzem o
comportamento documentado de cada backend, incluindo um teste de regressão que
cobra que o valor 1,0 nunca seja escrito.

### 4.2 O simulador de movimento não produzia artefato de movimento

O simulador deslocava a cabeça por uma senoide, e isso não degradava nada.
Medido: com deslocamento de 8 pixels e nada mais, o erro do POS não muda na
terceira casa decimal.

A razão é instrutiva. O rastreador segue o deslocamento, as regiões de interesse
acompanham, e a média de cor sai idêntica à do rosto parado. **Deslocar o desenho
reproduz só o mecanismo mais fácil de compensar**, e nenhum dos três que de fato
derrubam a medição.

Isso explica por que não havia cenário de movimento no conjunto de avaliação: não
havia como construir um que falhasse. O simulador estava otimista, não errado.

**Correção:** módulo novo com os quatro mecanismos físicos, descrito na seção 3.2
do projeto, todos com padrão neutro para que os números já publicados continuem
valendo bit a bit.

## 5. A abstenção com incerteza calibrada, e o que ela já mede

Esta seção corresponde à hipótese H4, e ela deixou de ser só hipótese: o
instrumento está construído e rodou.

### 5.1 Por que a bateria antiga não servia para isso

Primeira medição, e ela reprovou o próprio plano. Sobre os 56 cenários da seção
2.1, **cinco das sete condições acertam 100% das janelas dentro de 3 bpm**, e as
duas restantes erram exatamente 50%, que é o GREEN e o ICA falhando na
interferência enquanto CHROM e POS acertam.

Um modelo de confiabilidade treinado ali aprenderia a identificar **qual
algoritmo rodou**, e não se a janela presta. O erro não varia de forma contínua,
então não há o que ordenar.

A conclusão foi construir a bateria de robustez, que é o instrumento das três
primeiras hipóteses. Ela entra no gerador como componente especular, movimento de
câmera com fundo gerado, e tons de pele.

### 5.2 O achado sobre H1: a proteção cromática existe, e ela acaba

A componente especular soma na cor do **iluminante**, e não na da pele. É isso
que move a direção cromática em que CHROM e POS se apoiam.

Varrendo o afastamento do iluminante com movimento rítmico de 12 px, quatro
frequências por linha, erro absoluto médio em bpm:

| Desvio do iluminante | VERDE | CHROM | POS | ICA |
| --- | ---: | ---: | ---: | ---: |
| 0,0 neutro | 18,01 | 0,02 | 0,02 | 25,51 |
| 0,5 | 18,01 | 0,01 | 0,02 | 25,51 |
| 0,75 | 18,01 | **20,00** | 0,04 | 18,00 |
| 1,0 | 18,01 | 31,50 | **31,51** | 31,49 |

**Três leituras, e as três sustentam a formulação de H1.**

O VERDE erra em todos os pontos, o que é esperado: usando um canal só, não há
como distinguir "chegou mais sangue" de "chegou mais luz".

CHROM e POS **cancelam o especular como foram projetados para cancelar**
enquanto a cromaticidade fica perto da suposta, e o erro deles fica em
centésimos de bpm. A proteção não é infinita: o CHROM quebra em desvio 0,75 e o
POS em 1,0.

A ordem entre os dois é a que a literatura prevê, com o POS proposto como
melhoria sobre o CHROM. Aqui ela aparece **medida**, e com o ponto em que cada um
cede.

Isso estreita a hipótese de um jeito útil. A pergunta para a camada de dado real
deixa de ser "o especular degrada?" e passa a ser **"a iluminação de uma sala se
afasta o bastante do neutro para cruzar esse limiar?"**. É mais estreita, mais
fácil de responder e mais útil, e só apareceu porque a camada sintética permite
varrer uma coisa de cada vez.

### 5.3 Dois regimes de movimento, e só um é perigoso

Medidos separadamente, e a distinção não estava no projeto original:

**Movimento de banda larga** espalha energia pelo espectro, derruba a relação
sinal-ruído e o sistema **recusa** pelo portão que já existia. É a falha
benigna: o resultado é silêncio, não mentira.

**Movimento rítmico**, de banda estreita dentro da faixa cardíaca, é outra
história. Alguém balançando a cabeça, caminhando ou numa esteira cria um pico
concorrente limpo, o método trava nele, e a resposta sai com trinta batimentos de
erro e com toda a aparência de correta.

A consequência para o protocolo de coleta é direta: **registrar o tipo de
movimento, e não só a amplitude**. Duas sessões com o mesmo deslocamento em
pixels podem cair em regimes opostos.

### 5.4 O que a abstenção entrega, e o que ela não entrega

Modelo: regressão logística bayesiana por aproximação de Laplace, características
que não dependem da resposta certa, três partições.

Sobre 349 janelas, com três recusadas pelo próprio pipeline:

| Partição | Respondendo sempre | Melhor com abstenção |
| --- | ---: | ---: |
| Por frequência, artefato conhecido | 8,16 bpm | **0,01 bpm** a 40,7% |
| Por condição, artefato nunca visto | 10,52 bpm | 8,01 bpm a 16,4% |

**O lado positivo.** Com o tipo de artefato representado no treino, o modelo
separa janela boa de ruim quase perfeitamente. No ponto de operação adotado, o
erro cai de 8,16 para 5,39 bpm recusando metade das janelas.

**O lado negativo, e é o resultado que mais vale.** O modelo **não generaliza
para um artefato que nunca viu**. Mantendo cobertura razoável, o ganho some.

A razão é a de 5.3: o artefato que sobra é a trava num pico rítmico limpo, e ele
produz um espectro **excelente**. Relação sinal-ruído alta, pico proeminente,
frequência estável entre subjanelas. Toda característica de janela diz "boa
janela".

Isso tem consequência direta para o desenho da IC: a camada 3, de coleta local,
precisa cobrir os tipos de artefato que se quer que o modelo detecte, e o
relatório final precisa declarar quais tipos ficaram de fora. Prometer abstenção
que funcione fora disso seria afirmar mais do que a medida sustenta.

### 5.5 A característica que domina, e uma avaliação que se corrigiu

| Característica | Peso | Desvio | Sustentado |
| --- | ---: | ---: | :---: |
| `razao_harmonica` | +4,56 | 0,88 | sim |
| `jitter_temporal` | +0,93 | 0,74 | sim |
| `snr_db` | +0,93 | 0,38 | sim |
| `proeminencia` | −0,94 | 0,32 | sim |
| `correlacao_com_fundo` | −0,48 | 0,19 | sim |

A razão harmônica domina, e a física explica: o pulso sobe rápido e desce
devagar, então deposita energia em 2f; uma oscilação de iluminação é senoidal e
não deposita.

**Uma avaliação anterior concluiu o oposto**, com peso de +0,199 contra desvio de
0,558, e vale contar por quê. Naquele momento a física do especular era uma
senoide escrita à mão, numa duplicata acidental de um módulo que já existia no
repositório. Com a física correta, acionada por pose, a característica passa a
discriminar. A conclusão antiga estava certa sobre o conjunto que tinha em mãos e
errada sobre o fenômeno, que é a forma mais fácil de se enganar com dado
sintético.

Quatro características ficam com peso zero e o desvio da priori, porque não
variam no caminho analítico, que não tem imagem: fração de pele, fração saturada,
deslocamento da região e saturação. Isso é a resposta certa, "não observei", e é
também a razão mais provável de o módulo render mais em dado real: as
características que descrevem a **imagem** são exatamente as que esta camada não
consegue exercitar.

### 5.6 Os limites, declarados

**A calibração não está boa.** Depois da correção por temperatura, ajustada fora
da amostra, o ECE fica em 0,26. Um limiar escolhido sobre probabilidade
descalibrada significa menos do que promete.

**A incerteza bayesiana não cobriu o caso inédito.** Era a esperança do desenho:
que o modelo se declarasse incerto sobre o artefato que nunca viu. Não aconteceu.
A posteriori só se alarga em direções com pouca dispersão no treino, e um
artefato semanticamente novo pode cair numa região bem coberta do espaço de
características. Incerteza sobre os pesos não é incerteza sobre o fenômeno, e
confundir as duas seria repetir, num nível acima, o erro que o projeto inteiro
critica.

**O conjunto é sintético.** Os números acima comparam configurações entre si e
não afirmam desempenho absoluto. O portão continua valendo: reproduzir os 3,67
bpm da literatura em UBFC-rPPG antes de acreditar em qualquer número novo.

## 6. O que isso significa para a IC

O projeto não começa do zero, e também não começa de um sistema que já funciona
perfeitamente. Começa de um sistema **medido o suficiente para saber onde ele
falha**, o que é a posição de partida mais útil que existe:

- a ferramenta está pronta e testada;
- o gerador de cenário está pronto e estendido, agora com componente especular,
  movimento de câmera e tons de pele;
- as hipóteses não foram inventadas: saíram de medição;
- **H1 e H4 já têm instrumento e primeira medida**, e H1 já produziu um
  resultado: o limiar de validade da hipótese cromática;
- o portão de qualidade está definido, que é reproduzir os 3,67 bpm da
  literatura antes de acreditar em qualquer número novo.

Uma ressalva que o orientador precisa ouvir antes de qualquer outra: **nada
disso é resultado da IC**. É trabalho anterior, de disciplina, e está declarado
como preliminar justamente para não ser confundido. O que ele muda é o ponto de
partida: a IC começa pelo experimento e pela interpretação, e não pela
construção da ferramenta. As perguntas das quatro hipóteses continuam abertas em
dado real, que é onde elas de fato se respondem.

## 7. Como reproduzir

```bash
git clone <repositório>
cd cardiocam
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"

pytest -n 4                 # os 2.198 testes
cardiocam avaliar           # os 56 cenários da seção 2.1
cardiocam diagnosticar      # a varredura da seção 2.3
cardiocam qualidade         # a abstenção da seção 5
```
