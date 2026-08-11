# ADR 0004: Usar o fundo do quadro como referência de iluminação

Data: 2026-08-10
Status: aceito

## Contexto

Uma medição real feita com webcam comum devolveu 73 bpm contra 89 de um relógio
de pulso, com relação sinal-ruído de apenas 1,2 dB. O sistema sinalizou
confiança baixa, ou seja, acertou em desconfiar, mas o número exibido estava
errado.

A investigação apontou para os controles automáticos da câmera. A exposição
automática compensa exatamente a variação que queremos medir: quando a pele
escurece por causa do pulso, o ganho sobe e apaga parte do sinal. O balanço de
branco automático é pior, porque ajusta cada canal de cor separadamente.

Isso importa porque CHROM e POS partem da hipótese de que a perturbação é
proporcional nos três canais. Um ganho por canal viola essa hipótese e escapa da
projeção cromática. Era o buraco que faltava fechar.

A primeira tentativa foi desligar os controles pela API do OpenCV. Na câmera
usada nos testes, todas as propriedades de exposição e balanço de branco leem
-1.0 e toda escrita devolve falso, nos dois backends do Windows. A câmera
simplesmente não expõe esses controles.

## Decisão

Amostrar faixas laterais do quadro, fora do rosto e sem pixels de pele, e
remover do sinal do rosto a parte explicável por essa referência, canal a canal,
por mínimos quadrados com alguns atrasos.

## Justificativa

A parede atrás da pessoa não tem pulso. Tudo que oscila nela é iluminação do
ambiente ou o ganho da câmera se ajustando. Como rosto e fundo recebem a mesma
luz, o fundo é uma medida direta da perturbação. É a técnica de rectificação de
iluminação por referência descrita na literatura de rPPG.

A correção é aplicada em cada canal RGB antes do algoritmo, e não depois. A
ordem não é detalhe: o balanço de branco age por canal, então é aí que a
correção pertence. Depois da combinação cromática os canais já se misturaram e
não há como desfazer. Medimos as duas ordens e ambas funcionam, mas a primeira é
a que corresponde ao mecanismo físico.

Os atrasos existem porque o controle automático da câmera reage alguns quadros
depois da mudança de luz.

Medição do efeito, em cenário com balanço de branco oscilando dentro da banda
cardíaca e ganho diferente por canal:

| | Acertos dentro de 3 bpm |
| --- | ---: |
| Sem rectificação | 1 de 16 |
| Com rectificação | 16 de 16 |

O porte para o navegador reproduz o resultado: 0 de 5 sem, 5 de 5 com.

## Consequências

O sistema passa a cobrir uma classe de perturbação que os métodos cromáticos não
cobrem, e deixa de depender de a câmera permitir travar seus automatismos.

Duas contrapartidas. A primeira é que passa a existir um custo por quadro para
amostrar o fundo, pequeno porque a amostragem é esparsa. A segunda é mais séria:
a referência precisa mesmo ser fundo. Se alguém passar atrás da pessoa medida, a
faixa lateral deixa de ser uma referência limpa. A exclusão de pixels de pele
reduz o risco, mas não elimina.

Uma trava que existia no começo foi retirada de propósito. Ela devolvia o sinal
original quando a remoção apagava quase tudo, para proteger contra o fundo
casualmente correlacionado com o pulso. O efeito colateral era pior que o
problema: se o fundo explica todo o sinal do rosto, então não havia pulso ali, e
devolver o original faria o sistema reportar a interferência como batimento.
Agora o resultado fica próximo de zero e a verificação de sinal degenerado
recusa a janela, que é a resposta correta. Um medidor deve errar para o lado de
dizer "não sei".
