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

**O que foi medido.** Sobre 335 janelas da bateria sintética, com partição por
condição: o erro cai de 10,51 bpm respondendo sempre para 6,01 bpm com 87,5% de
cobertura.

**O modelo redescobriu um defeito conhecido do projeto.** Os pesos de entropia
espectral e de proeminência dizem a mesma coisa: dado o SNR, espectro **limpo
demais** indica resposta errada. É o que o README já afirmava em prosa sobre o
ICA, "uma interferência senoidal forte é mais limpa que um pulso real", agora
saindo do dado sem ninguém ter dito ao modelo.

**O que o modelo não resolve, e não vai resolver com mais característica.**
Quando a interferência é cromaticamente alinhada com o pulso, nenhuma
característica de janela a distingue, e o erro no teste tem piso. Isso está
medido na varredura de desvio do iluminante e é um limite físico, não uma
deficiência de ajuste.

**O que o modelo honestamente não sabe.** Quatro características não variam no
caminho analítico, por não haver imagem: fração de pele, fração saturada,
deslocamento da região e jitter. Os pesos delas ficam em zero com o desvio da
priori, e isso é a resposta certa, "não observei", em vez de um número que depois
seria lido como informação. Há teste cobrando.

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
