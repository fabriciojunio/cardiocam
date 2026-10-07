# 6. Exposição contra taxa de quadros, e a câmera que desligava sozinha

> **Nota de 07/10/2026.** A implementação em navegador descrita aqui foi
> removida do projeto no mesmo dia, e o aplicativo de desktop a substituiu. Este
> registro continua valendo por dois motivos. O primeiro é que a física medida é
> da câmera e não do navegador: a exposição no máximo limita a taxa de quadros
> em qualquer programa, e o aplicativo de desktop herda o mesmo problema e a
> mesma conta de teto. O segundo é o método, que é o que o documento de fato
> ensina: três correções publicadas sem medir o fenômeno, e o diagnóstico saindo
> em três medidas depois que o instrumento foi construído. Decisão não se apaga
> quando o código muda; se apaga, o projeto perde a memória de por que decidiu.

## Contexto

O relato foi: "a câmera desliga e liga, e não aparece mais nada". Três correções
foram publicadas antes desta, e as três erraram o alvo, porque todas partiram de
uma hipótese sobre o agendamento de quadros e nenhuma mediu a câmera.

As três hipóteses erradas, na ordem em que foram tentadas:

1. **Quadro repetido.** O laço usava `requestAnimationFrame`, que dispara na
   taxa do monitor e não na da câmera, e o mesmo quadro entrava duas ou três
   vezes na série. Era um defeito real, foi corrigido, e não era este.
2. **Base de tempo misturada.** A correção acima trouxe um defeito próprio, que
   somava `performance.now()` com `mediaTime` e dava duração negativa. Também
   real, também corrigido, também não era este.
3. **Cadeia de quadros morta em silêncio.** `requestVideoFrameCallback` só
   dispara quando chega quadro novo, então se a câmera para nada mais religa o
   agendamento. Foi escrito um vigia para isso, e ele **só era armado no ramo de
   reserva**, que nenhum navegador atual usa. Defesa escrita e não instalada.

Depois da terceira, o relato continuou igual. Foi aí que a abordagem mudou: em
vez de outra hipótese, um navegador de verdade sendo dirigido por programa, com
a câmera do próprio usuário.

## As medições

Montou-se um arnês que abre um Chromium, serve a página de `127.0.0.1` e lê o
estado dela pelo protocolo de depuração. Ele roda em dois modos: com uma câmera
falsa alimentada por um vídeo gerado pelo simulador do projeto, com frequência
cardíaca conhecida, e com a câmera de verdade da máquina.

**Primeira medida, com a câmera real.** A captura entregava **sete a oito
quadros por segundo**, enquanto `getSettings()` declarava vinte. Sem resgates,
sem silêncio, sem trilha silenciada: o agendamento estava perfeito e os quadros
é que não chegavam.

**Segunda medida, varrendo resolução.** Oito quadros por segundo em 1920x1080.
Oito em 1280x720. Oito em 960x540, em 640x480 e em 320x240. Taxa que não muda
com o tamanho do quadro não é limitada por banda de barramento nem por tempo de
decodificação: as duas se comportam de outro jeito.

**Terceira medida, varrendo exposição.** Numa EMEET SmartCam S600:

| exposição (unidades de 100 µs) | taxa entregue |
| ---: | ---: |
| 5000, o máximo, e o valor em que ela abre | 8,0 |
| 2500 | 8,0 |
| 1250 | 8,0 |
| 625 | 15,9 |
| 312 | 30,0 |

A luminância do quadro ficou em 11 de 255 em todas as linhas: sala às escuras.

## O diagnóstico

A câmera abre com a exposição no máximo. Ela não pode entregar um quadro antes
de terminar de expô-lo, então a taxa cai para oito, em qualquer resolução.

O aplicativo então fazia o seguinte: lia oito quadros por segundo, comparava com
o mínimo de catorze, concluía que **a máquina não dava conta daquela
resolução**, e chamava `parar()` seguido de `comecar()` para reabrir a câmera
numa resolução menor. Reabrir derruba o dispositivo: a luz da webcam apaga e
acende, a imagem some, e a janela de coleta recomeça do zero. Como a causa nunca
foi a resolução, a taxa continuava em oito, e ele reabria de novo. Duas vezes
por sessão, até chegar na menor resolução e desistir com uma mensagem mandando
fechar programas pesados.

Do lado de quem estava medindo: a câmera desligando e ligando sozinha, e a
contagem nunca terminando.

**O defeito mais caro não era nenhuma das três hipóteses. Era o próprio
mecanismo de proteção, agindo com segurança sobre uma causa errada.**

## A decisão

**Primeira: a exposição tem um teto, e ele vem da taxa mínima.** A relação é
física e não precisa de calibração. A especificação de Image Capture define
`exposureTime` em passos de 100 microssegundos, então a exposição máxima
compatível com uma taxa é `10000 / taxa`. Para quinze quadros por segundo, 667
unidades, isto é 66,7 ms. Conferido: 625 unidades deram 15,9 quadros por
segundo, e 312 deram 30,0.

A procura por luz continua existindo, e passou a acontecer **debaixo desse
teto**. Antes eram duas decisões em arquivos diferentes que não sabiam uma da
outra, e uma desfazia a outra.

**Segunda: a resolução muda na trilha viva, com `applyConstraints`, e nunca
reabrindo a câmera.** O dispositivo não cai, a luz não pisca, e a medição
continua. Só a janela de coleta recomeça, porque a média espacial antes e depois
da mudança não são a mesma medida e misturá-las seria juntar dois instrumentos
num número só.

**Terceira: a resolução deixou de ser a primeira suspeita.** Antes dela vem o
relatório da exposição, que diz se o que limita é luz, taxa ou nenhum dos dois.

**Quarta: o programa anota o que fez.** Um registro em anel, com o instante de
cada decisão, copiável por um botão. O relato possível antes era "a câmera
desliga e liga", e dele cabiam quatro explicações com providências diferentes.
Nenhuma delas se distinguia das outras olhando a tela.

## Por que conferir onde a câmera ficou, e não confiar no pedido

Pedir o teto não basta. `getCapabilities` desta webcam declara passo de 1,22
unidades, sugerindo ajuste fino, e o que ela aceita de fato é uma escada grossa:
5000, 2500, 1250, 625. Pedir 666 devolveu 625 numa execução e 1250 em outra, e
1250 ainda dá oito quadros por segundo.

Então o ajuste pede o teto, **lê onde a câmera ficou**, e corta pela metade
enquanto estiver acima dele, até três vezes. Cortar pela metade garante descer
um degrau da escada por rodada, qualquer que seja a escada.

E a conferência vale para **toda** escrita de exposição, não só para a que
pretende descer. A primeira versão deste módulo a punha apenas no ramo que
desce, e o furo apareceu no teste com a câmera real duas horas depois: com a
câmera em 625, abaixo do teto de 666, e a sala escura, o ramo que sobe atrás de
luz pedia exatamente o teto; a câmera arredondava para 1250, o degrau de cima; e
a captura caía de 15,9 para 8,0 quadros por segundo caçando uma luz que nem
chegava a ganhar. É o mesmo erro que este ADR documenta, cometido de novo dentro
do código escrito para impedi-lo, e pego pelo instrumento que a investigação
tinha acabado de construir.

Essa conferência não mede taxa nenhuma: compara dois números que a câmera
entrega na hora. Isso importa mais do que parece, porque medir taxa é a parte
frágil, e foi medido que ela falha: em parte das execuções
`requestVideoFrameCallback` não disparou nenhuma vez durante a abertura, porque
o elemento de vídeo ainda está escondido nesse ponto e compor quadro de elemento
invisível é opcional para o navegador. A decisão principal foi tirada desse
caminho frágil de propósito.

## Consequências

Na mesma câmera, no mesmo quarto escuro, com a exposição propositalmente presa
no máximo antes de abrir a página:

| | antes | depois |
| --- | ---: | ---: |
| exposição final | 5000 | 625 |
| taxa entregue | 8,0 | 15,9 |
| reaberturas da câmera | 2 | 0 |
| resgates da cadeia de quadros | 0 | 0 |

E com a câmera sintética, que entrega um rosto com 75 batimentos por minuto
gravados: a página mede 79, com relação sinal-ruído de 21,7 dB sobre catorze
janelas, e a barra de progresso completa.

**O que continua limitado, e é honesto declarar.** Com luminância 11 de 255 não
há medição possível, e nenhum ajuste de câmera resolve isso: o pulso vale entre
0,1% e 1% da intensidade, e abaixo de 60 ele fica menor que o passo de
quantização do sensor. O que mudou é que a página agora **diz isso**, com o
número medido, em vez de reabrir a câmera atrás de uma causa que não existe.

**O custo.** A abertura ficou cerca de dois segundos mais lenta, gastos medindo
e ajustando. É pago com uma mensagem na tela dizendo o que está acontecendo.

**A taxa que o diagnóstico mostra passou a ser a entregue.** Ela vinha de
`medidor.fpsEfetivo`, que devolve 30 enquanto não houver dez amostras. É um
valor de partida razoável para o processamento e uma mentira num diagnóstico:
ele dizia 30 numa captura rodando a 16, e quem lesse isso procuraria o defeito
no lugar errado. Agora sai da contagem de quadros entre dois pulsos, e vale
mesmo sem ninguém na frente da câmera.

**O que esta história ensina sobre o projeto, e vale para a iniciação
científica.** Três correções seguidas foram publicadas sem uma medição do
fenômeno, cada uma consertando algo real e nenhuma consertando o que o usuário
via. A quarta começou por montar o instrumento, e o diagnóstico saiu em três
medidas. A diferença entre as três primeiras e a quarta não foi conhecimento de
domínio: foi ter decidido medir antes de decidir.

## Alternativas descartadas

**Baixar a taxa alvo e aceitar oito quadros por segundo.** Nyquist permitiria,
já que a banda cardíaca vai a 3,3 Hz. Mas a análise usa subjanelas e mede a
dispersão entre elas, e com oito quadros por segundo cada subjanela fica com
poucas dezenas de amostras; a dispersão deixa de distinguir medida boa de ruído,
que é o indicador de confiança que o sistema mostra.

**Deixar a exposição no automático.** É o que mais estraga a medição: quando a
pele escurece por causa do pulso, o controle automático clareia a imagem e apaga
parte do sinal. O travamento precisa existir; o erro era travar sem olhar onde.

**Avisar e não ajustar.** Seria honesto e inútil: o usuário não tem como mexer
no tempo de exposição da webcam pelo sistema operacional sem um utilitário do
fabricante.

**Usar `brightness` em vez de `exposureTime`.** Ganho digital não compra sinal,
multiplica o que já existe junto com o ruído. A relação sinal-ruído não melhora,
e a imagem fica mais clara dando a impressão de que melhorou.
