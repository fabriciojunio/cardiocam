# ADR 0002: Validar contra simulação física em vez de gravações reais

Data: 2026-08-10
Status: aceito

## Contexto

Um sistema de medição precisa de evidência de que mede certo. As opções eram
gravar pessoas e comparar com um oxímetro, usar uma base pública anotada, ou
construir um simulador com frequência conhecida.

## Decisão

Construir um simulador que reproduz a física do fenômeno e no qual a frequência
verdadeira é um parâmetro de entrada, e basear a suíte automatizada nele.

## Justificativa

Gravação real sem referência simultânea não permite verificar nada: não se sabe
o valor correto. Com oxímetro, seria possível, mas a coleta não é reproduzível
em integração contínua, envolve dados pessoais sensíveis de terceiros e não
cobriria sistematicamente a faixa de 42 a 240 bpm nem as condições adversas.

Base pública resolveria a reprodutibilidade, ao custo de um download grande e de
licenças de uso de imagem de pessoas.

O simulador permite varrer a faixa inteira, isolar uma perturbação por vez e
afirmar com precisão numérica qual é o erro. Reproduz o que importa: pulso com
harmônicos, peso diferente por canal, ruído por pixel, deriva e oscilação de
iluminação, movimento e temporização irregular. E o rosto renderizado é
detectável pela cascata de Haar, o que faz os testes de ponta a ponta
exercitarem o pipeline inteiro em vez de só a parte de sinais.

## Consequências

A suíte roda em qualquer máquina, sem download e sem dado pessoal, e mede erro
com exatidão.

O risco é real e precisa ser dito: o simulador valida contra o modelo, não
contra a realidade. Se o modelo estiver errado, os testes passam e o sistema
falha na prática. Isso aconteceu durante o desenvolvimento, ao contrário — a
primeira versão aplicava o pulso igualmente nos três canais, o que é fisicamente
errado, e CHROM e POS corretamente devolveram zero. O defeito foi encontrado
justamente porque dois algoritmos com fundamentação sólida discordaram do
simulador.

Validação contra oxímetro de dedo continua sendo o passo seguinte natural, e
está registrada como trabalho futuro no relatório.
