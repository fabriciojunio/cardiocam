# ADR 0003: Cascata de Haar e OpenCV fixado na linha 4.x

Data: 2026-08-10
Status: aceito

## Contexto

O sistema precisa localizar rostos. O OpenCV oferece a cascata de Haar clássica
e o YuNet, um detector baseado em rede neural. Durante o desenvolvimento
descobrimos que o OpenCV 5.0 removeu `CascadeClassifier` do pacote principal.

## Decisão

Usar a cascata de Haar e fixar a dependência em `opencv-python>=4.8,<5`.

## Justificativa

Os arquivos da cascata vêm dentro do próprio pacote. O YuNet exige baixar um
arquivo de pesos em tempo de execução ou versioná-lo no repositório, e uma
dependência de rede num programa que roda offline e mede dado sensível é um
custo que não vale a pena aqui.

Tecnicamente, a cascata basta para o caso de uso: alguém sentado de frente para
a câmera, que é a única postura em que a medição funciona de qualquer forma. Um
detector mais robusto a perfil resolveria um problema que o resto do sistema
não resolve.

Há também um motivo didático, já que o projeto é de disciplina: Viola-Jones é
exatamente o conteúdo coberto em aula, com imagem integral, características de
Haar, AdaBoost e cascata de rejeição.

O parâmetro de escala da pirâmide foi definido por medição. Com passo 1,1 a
taxa de detecção sobre o conjunto de validação ficou entre 64% e 80%; com 1,05,
em 100%. O custo extra é absorvido rodando o detector a cada dois quadros, com
o rastreador reaproveitando a caixa no quadro intermediário.

## Consequências

Zero download em tempo de execução e instalação simples.

Em troca, rosto de perfil ou muito inclinado não é detectado, e a cascata produz
mais falsos positivos que um detector moderno. O rastreador compensa
parcialmente ao rejeitar detecções que saltam demais em posição ou escala.

A fixação da versão precisará ser revisitada quando o OpenCV 5 se consolidar. A
saída natural será migrar para o YuNet com o arquivo de pesos versionado, e a
interface `DetectorFace` já existe para que essa troca não toque no pipeline.
