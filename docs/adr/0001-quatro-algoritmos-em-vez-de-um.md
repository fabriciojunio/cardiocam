# ADR 0001: Implementar quatro algoritmos rPPG em vez de escolher um

Data: 2026-08-10
Status: aceito

## Contexto

Bastaria um algoritmo para o sistema funcionar. A literatura converge para os
métodos cromáticos, e implementar só o POS entregaria o mesmo resultado prático
com menos código.

## Decisão

Implementar GREEN, CHROM, POS e ICA atrás de uma interface comum, com o mesmo
pós-processamento para todos, e um benchmark que os compara nos mesmos cenários.

## Justificativa

O que separa esses métodos não é ajuste fino: é uma diferença conceitual sobre o
que se assume a respeito do fenômeno. O GREEN assume que a intensidade de um
canal já é o sinal. O CHROM assume um tom de pele padrão e cancela a distorção
comum. O POS não assume tom de pele nenhum e projeta num plano ortogonal. O ICA
não assume modelo físico algum e tenta separar as fontes cegamente.

Só com os quatro lado a lado é possível mostrar que a diferença aparece apenas
sob interferência dentro da banda cardíaca, e desaparece em condição favorável.
Com um algoritmo só, a afirmação "o POS é robusto" seria uma citação, não um
resultado.

A interface comum e o pós-processamento compartilhado existem para que a
comparação seja honesta: a única variável entre eles é a combinação de canais.

## Consequências

Mais código para manter e uma suíte de testes maior. Em compensação, trocar de
algoritmo em tempo de execução ficou trivial (teclas 1 a 4 na janela ao vivo), e
o benchmark virou o principal resultado do trabalho.

O ICA trouxe um custo não previsto: é iterativo, pode não convergir, e exige o
scikit-learn como dependência para uma única função.
