# 5. Abstenção com incerteza calibrada, e por que bayesiana

## Contexto

O sistema sempre devolve um número. Quando a janela é ruim, ele devolve um
número errado com exatamente a mesma aparência de um número certo, e quem lê não
tem como distinguir. Três testes já atacavam isso por regra fixa, cobrando que
parede lisa, imagem saturada e vídeo curto não produzissem valor nenhum. São
casos extremos; o caso que importa é o intermediário, em que há sinal, o
espectro tem pico, e a estimativa está a quarenta batimentos da verdade.

A hipótese H4 do projeto de iniciação científica afirma que recusar janela ruim
compra mais redução de erro do que qualquer correção de sinal, ao custo de
cobertura. Até aqui ela não tinha uma linha de código.

## Decisão

Um modelo probabilístico estima `P(|erro| ≤ tolerância)` a partir de
características da janela, e o sistema recusa responder abaixo de um limiar. O
modelo é uma **regressão logística bayesiana ajustada por aproximação de
Laplace**, escrita em numpy, sem dependência nova.

A avaliação do conjunto é a **curva de erro contra cobertura**, e nunca um
número de erro sozinho.

## Por que bayesiana, e não um classificador comum

Um classificador devolve um número entre 0 e 1 e não distingue dois casos que
são muito diferentes:

- "vi muitas janelas parecidas com esta, e 70% delas acertaram";
- "nunca vi nada parecido com esta, e meu chute é 70%".

Num sistema que vai **recusar medir** com base nesse número, confundir os dois é
o erro mais caro possível: a recusa fica arbitrária justamente na região em que
o modelo não tem experiência, que é onde ela mais importa.

A posteriori sobre os pesos separa os dois casos. A probabilidade preditiva,
marginalizada pela aproximação probit, é puxada em direção a 0,5 onde a variância
é grande. Esse encolhimento é o que faz a abstenção ser honesta, e é cobrado por
teste: dois pontos com o mesmo logito médio, um dentro e outro fora da nuvem de
treino, precisam receber probabilidades diferentes.

Há um segundo motivo, prático. A priori própria impede a divergência clássica da
logística com dado linearmente separável, e esse caso **acontece aqui**: cenário
sintético fácil produz janelas em que toda estimativa acerta. Sem priori, os
pesos iriam para o infinito e a confiança seria absoluta exatamente onde o dado
não sustenta nada.

## Por que Laplace, e não amostragem nem variacional

A posteriori não tem forma fechada. Com priori gaussiana e verossimilhança
logística, porém, ela é côncava: existe um máximo só, e a gaussiana em torno dele
é uma boa aproximação em dimensão baixa, que é o caso com uma dezena de
características. Cadeia de Markov custaria tempo e introduziria diagnóstico de
convergência para responder a mesma coisa; inferência variacional pediria uma
família e um otimizador.

A limitação, declarada: Laplace é aproximação **local**, e descreveria mal uma
posteriori assimétrica ou multimodal. A garantia aqui vem da concavidade, não da
aproximação em si.

## As três partições

Treino ajusta os pesos. **Calibração** ajusta a temperatura e escolhe o limiar.
Teste reporta.

Com duas partições, o limiar seria escolhido no mesmo dado em que é reportado, e
o número publicado ficaria otimista por construção. É o erro mais comum em
trabalho com rejeição e o mais fácil de cometer sem perceber, porque nada falha.

A partição é **por condição**, nunca por janela. Janelas do mesmo cenário são
parecidas entre si, e partir por janela deixaria quase-cópias dos dois lados: o
teste mediria memorização. Agrupar por condição é a versão sintética do que, em
dado real, precisa ser agrupamento por sujeito, e o teste
`test_nenhum_grupo_aparece_em_duas_particoes` cobra isso.

## A calibração, e por que temperatura

Discriminação e calibração são qualidades diferentes e podem andar em direções
opostas. Para ordenar, basta a primeira; para **escolher um limiar que
signifique risco**, é preciso a segunda.

A primeira medição deu ECE de 0,18 com excesso de confiança na faixa alta, que é
precisamente onde a decisão de recusa vive. A correção é escala por temperatura,
ajustada na partição de calibração. Foi escolhida em vez de regressão isotônica
por três motivos: é monótona, então não mexe na curva de erro contra cobertura e
quem já escolheu um ponto de operação não precisa reescolher; tem um parâmetro
só, e cabe numa partição pequena, onde a isotônica decoraria; e o valor aparece
no relatório, podendo ser conferido.

A temperatura é ajustada minimizando **log-perda**, e não ECE. ECE depende do
número de faixas e é uma função escada do parâmetro, cheia de mínimos locais
falsos; log-perda é suave e é uma regra de pontuação própria.

## Consequências

**O resultado tem dois lados, e o negativo é o mais informativo.** Sobre 349
janelas da bateria sintética:

| Partição | Respondendo sempre | Melhor com abstenção |
| --- | ---: | ---: |
| Por frequência, artefato conhecido | 8,16 bpm | 0,01 bpm a 40,7% |
| Por condição, artefato nunca visto | 10,52 bpm | 8,01 bpm a 16,4% |

Quando o tipo de artefato está no treino, o modelo separa janela boa de ruim
quase perfeitamente. Quando o artefato é inédito, mantendo cobertura razoável,
o ganho some. A conclusão prática: **o modelo de qualidade precisa ser treinado
nos artefatos que vão ocorrer, e o modo de falha dele é o artefato inédito.**

**A primeira medição deste módulo foi melhor, e era artefato da implementação.**
Antes da reconciliação com `fontes/movimento.py`, a física de movimento era uma
senoide escrita à mão neste repositório em duplicata, e o número dava 6,01 bpm a
87,5% de cobertura. Com a física correta, de ruído de banda, o número caiu. O
primeiro resultado não estava errado por descuido de medição: estava medindo um
mundo mais fácil do que o real.

**Por que o artefato inédito escapa.** O pior deles produz um espectro excelente.
Movimento rítmico dentro da banda cardíaca cria um pico concorrente limpo, e o
método trava nele: relação sinal-ruído alta, pico proeminente, frequência estável
entre subjanelas. Toda característica de janela diz "boa janela". Movimento de
banda larga, ao contrário, derruba a relação sinal-ruído e cai no portão que já
existia; é a falha benigna.

**A característica que domina é a razão harmônica** (+4,56 com desvio de 0,88).
A física explica: o pulso sobe rápido e desce devagar, então deposita energia em
2f; uma oscilação de iluminação é senoidal e não deposita. Isso valida, com
medida, a sugestão que o relatório da disciplina tinha listado como trabalho
futuro para o critério de seleção do ICA.

Vale registrar que uma avaliação anterior, feita sobre a bateria com física de
senoide, concluiu o contrário: que a razão harmônica não sustentava o próprio
peso. A conclusão estava certa para aquele conjunto e errada sobre o mundo. É um
bom lembrete de que característica se avalia contra o fenômeno, não contra o
gerador.

**O que o modelo honestamente não sabe.** Quatro características não variam no
caminho analítico, por não haver imagem: fração de pele, fração saturada,
deslocamento da região e jitter. Os pesos delas ficam em zero com o desvio da
priori, e isso é a resposta certa, "não observei". Há teste cobrando. É também a
razão mais provável de o módulo render mais em dado real do que aqui: as
características que descrevem a **imagem** são justamente as que esta camada não
consegue exercitar.

**A calibração continua insuficiente.** O ECE fica em 0,26 depois da correção por
temperatura. A descalibração que sobra está nas faixas do meio, onde a partição
de calibração tem poucas janelas, e um limiar escolhido sobre probabilidade
descalibrada significa menos do que promete.

**A incerteza epistêmica não cobriu o caso inédito.** Era a esperança do desenho
bayesiano: que o modelo se declarasse incerto sobre o artefato que nunca viu. Não
aconteceu, e a razão é entendível: a posteriori só se alarga em direções com
pouca dispersão no treino, e um artefato semanticamente novo pode cair numa
região do espaço de características que o treino cobre bem. Incerteza sobre os
pesos não é incerteza sobre o fenômeno.

## Alternativas descartadas

**Limiar fixo de relação sinal-ruído**, que o sistema já tinha. Continua, como
primeira peneira, mas não resolve o caso intermediário: existe janela com SNR
alto e estimativa errada, e é justamente a interferência senoidal.

**Floresta aleatória ou gradiente.** Discriminariam melhor e não dariam
incerteza epistêmica, que é o que torna a recusa defensável fora da distribuição
de treino. Com uma dezena de características e algumas centenas de janelas, o
ganho em discriminação não compensaria perder isso.

**Regressão para o erro em bpm, em vez de classificação.** Parece mais
informativo e é pior aqui: o erro tem distribuição com duas modas muito
separadas, perto de zero e perto de quarenta, e a média condicional cairia no
vale entre elas, que é um valor que quase nunca ocorre.
