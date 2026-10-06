# Cardiocam

Mede frequência cardíaca a partir de vídeo, sem encostar na pessoa. A câmera
capta variações de cor da pele causadas pelo fluxo de sangue, e o sistema
transforma isso num número.

A técnica se chama fotopletismografia remota (rPPG). O princípio é o mesmo do
oxímetro de dedo, com uma diferença: em vez de um LED e um fotodiodo encostados
no corpo, usamos a luz do ambiente e uma webcam comum.

Projeto da disciplina de Processamento de Imagens e Sinais. Foi escolhido
justamente por exigir as duas metades: detectar e recortar o rosto é
processamento de imagem; extrair uma oscilação de 1 Hz enterrada em ruído é
processamento de sinais.

## Como funciona

A cada quadro, o sistema faz o caminho abaixo. As três primeiras etapas são
imagem, as demais são sinais, e a média RGB é a fronteira entre os dois mundos.

```
quadro de vídeo
  └─ detecção do rosto (cascata de Haar / Viola-Jones)
      └─ estabilização da caixa (média exponencial + rejeição de saltos)
          └─ regiões de interesse (testa e bochechas)
              └─ máscara de pele (limiar de crominância em YCrCb)
                  └─ média espacial dos pixels  ← 3 números por quadro
                      └─ janela deslizante de 10 s
                          └─ reamostragem em grade temporal uniforme
                              └─ algoritmo rPPG (GREEN / CHROM / POS / ICA)
                                  └─ remoção de tendência (Tarvainen)
                                      └─ passa-faixa Butterworth 0,7–4 Hz
                                          └─ FFT + refino parabólico do pico
                                              └─ batimentos por minuto
```

Alguns pontos que decidem se funciona ou não:

**Por que a média espacial é indispensável.** A variação de intensidade causada
pelo pulso fica na casa de 0,1% a 1%, abaixo do ruído de leitura de um pixel
isolado. Como esse ruído é aproximadamente independente entre pixels, promediar
N deles reduz o desvio por um fator de √N. É isso que faz o sinal emergir.

**Por que estabilizar a caixa do rosto.** A cascata redetecta o rosto do zero a
cada quadro e a caixa oscila alguns pixels mesmo com a pessoa imóvel. Como
medimos a média dentro dessa caixa, o tremor faz a região incluir ora mais pele,
ora mais cabelo. Isso injeta uma variação muito maior que a do pulso, e na
mesma banda de frequência.

**Por que quatro algoritmos.** Eles não são intercambiáveis, e a diferença entre
eles é o conteúdo mais interessante do projeto (veja a tabela abaixo).

**Por que o fundo do quadro é medido junto.** A parede atrás da pessoa não tem
pulso: tudo que oscila nela é luz do ambiente ou o ganho da câmera se ajustando
sozinho. Isso torna o fundo uma medida direta da perturbação, e o que for
explicável por ele é removido do sinal do rosto.

Esse passo fecha um buraco que os métodos cromáticos deixam. CHROM e POS partem
da hipótese de que a distorção é proporcional nos três canais, o que vale para
mudança de brilho mas não para o balanço de branco automático, que ajusta cada
canal separadamente. Em cenário com balanço de branco oscilando dentro da banda
cardíaca, a taxa de acerto foi de 1 em 16 sem a correção para 16 em 16 com ela.

O ideal seria simplesmente desligar exposição e balanço de branco automáticos, e
o sistema tenta fazer isso ao abrir a câmera. Muitas webcams não expõem esses
controles: a usada no desenvolvimento recusa toda tentativa nos dois backends do
Windows. A correção por fundo funciona independentemente disso.

## Versão web

**https://cardiocam.vercel.app**

Roda no navegador, em computador e celular, sem instalar nada. Quatro fontes:
rosto pela câmera, **janela de chamada** (Teams, Meet, Zoom, WhatsApp), dedo na
câmera traseira com a lanterna, e arquivo de vídeo. Guarda as medições por
pessoa e exporta em CSV.

Tudo é processado dentro do navegador. Não existe servidor neste projeto, e o
cabeçalho `Content-Security-Policy` fecha isso com `connect-src 'none'`: ainda
que algum código tentasse enviar dados para fora, o navegador recusaria a
conexão. Detalhes e diferenças em relação a esta versão em
[web/LEIAME.md](web/LEIAME.md).

**O rosto é detectado por cascata de Haar, portada para o navegador.** As três
regiões medidas acompanham a caixa do rosto, e a pessoa pode se mover. Não há
contorno para encaixar nem linha para alinhar.

O caminho até aqui passou por duas tentativas, e as duas ensinaram algo.

A primeira localizava o rosto pela **mancha de pele**, reaproveitando o
classificador de crominância que o projeto já tinha testado. Passou em todo
cenário sintético e falhou na primeira foto real, pela razão mais simples
possível: **a parede bege do quarto cai na faixa de crominância da pele e é
maior que o rosto**. A caixa resultante ocupava 99% da largura do quadro.
Nenhum ajuste de limiar conserta, porque o problema não é o limiar: é a premissa
de que a maior mancha cor de pele é um rosto.

A segunda seria o BlazeFace via MediaPipe, medido e descartado por três motivos:
runtime em WebAssembly de 9,3 MB e pacote acima de 18 MB, inviável numa página
que abre no celular; a política de segurança do site precisaria ser afrouxada em
duas diretivas para baixar de terceiro; e modelo em WebAssembly não roda na
suíte em Node.

A cascata resolve os três: **107 KB de modelo convertido**, JavaScript puro,
hospedada no próprio site, e é o mesmo algoritmo da versão em Python, o que põe
as duas implementações em paridade. Na mesma foto em que a cor falhou, ela acha
o rosto a quatro pixels de onde o OpenCV acha.

Dois erros no porte, e os dois valem registro porque o sintoma não apontava a
causa. Supor que os classificadores fracos eram tocos de decisão, quando são
árvores: o detector passava dois estágios e morria no terceiro, em toda posição
e toda escala. E a normalização da janela, que no OpenCV usa a janela recuada em
um pixel e a raiz de (área × soma dos quadrados − soma²), não o desvio padrão:
misturar as convenções dá erro de escala de centenas de vezes.

**Duas coisas que a medição do movimento ensinou**, e que contrariam a
intuição:

- **Movimento lento não estraga a medição.** Deslocamento a 0,15 Hz fica muito
  abaixo da banda cardíaca, e o passa-faixa o remove antes de qualquer
  estimativa. Com a região congelada e o rosto oscilando 10% do quadro, o erro
  continuou em 0,0 bpm. O que o rastreamento compra é tolerância a deslocamento
  **grande**, em que a região congelada sai do rosto e falta pele para medir.
- **Rosto sintético de cor uniforme esconde o problema por completo.** Com o
  rosto pintado de uma cor só, a máscara de pele seleciona apenas pixels de
  pele dentro da região, e todos carregam o mesmo pulso, então a medição sai
  perfeita mesmo com a região no lugar errado. O cenário só passa a significar
  algo com gradiente de sombreado ao longo da face, que é o que existe de
  verdade.

As duas conclusões saíram de um teste de controle que reprovou duas versões do
cenário. Nas duas vezes o certo era mudar o cenário, não o limiar.

**O número exibido vem do espectro médio**, e não de suavizar estimativas de
janelas isoladas. Promediar o espectro de janelas sucessivas é a técnica de
Welch: a variância do espectro estimado cai com o número de segmentos, e disso
vem tanto um número mais firme quanto um pico que emerge em condição pior. O
peso de esquecimento, 0,15, saiu de medição contra três alternativas, e é o
único que ganha da média exponencial **nos dois eixos ao mesmo tempo**: 0,030
contra 0,036 de desvio, e 17 s contra 19 s para acompanhar uma mudança real de
frequência. Somar sem esquecer leva 60 s para acompanhar, e foi descartado. A
mediana móvel também foi medida, e dá desvio pior que a exponencial.

**A correção por fundo é escolhida por medição, não assumida.** As duas versões
do sinal são calculadas a cada janela, com e sem a correção, e a de melhor
relação sinal-ruído vence. Isso existe porque a correção não ajuda sempre: num
enquadramento com roupa clara ocupando metade do quadro, aplicá-la piorou a
dispersão de 0,10 para 10,12 bpm, porque a referência de iluminação continha
ombro e roupa, que se movem com a pessoa.

**A taxa de captura é limitada a 20 quadros por segundo, de propósito.** A
câmera não pode expor um quadro por mais tempo que o intervalo entre quadros: a
60 o limite é 16 ms, a 20 é 50 ms. Odinaev et al. (CVPRW 2023) acharam o ótimo
de exposição em 1/16 de segundo e mostram que exposição maior melhora a
correlação com o fotopletismógrafo de contato em pouca luz, funcionando com até
25 lux. A revisão sistemática da área dá 19,9 quadros por segundo como piso.
Para a banda cardíaca, que vai a 3,3 Hz, 20 ainda são três vezes Nyquist.

## Instalação

```bash
git clone https://github.com/<usuario>/cardiocam.git
cd cardiocam
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux e macOS
pip install -e ".[dev]"
```

Precisa de Python 3.10 a 3.13. O OpenCV está fixado na linha 4.x de propósito:
a 5.0 removeu os classificadores em cascata, que vêm embutidos no pacote e
evitam qualquer download em tempo de execução.

## Uso

Medir pela webcam:

```bash
cardiocam ao-vivo
```

A janela mostra o rosto com as regiões medidas marcadas, a onda de pulso
recuperada, o espectro com o pico destacado e o valor em bpm. Durante os
primeiros 10 segundos aparece uma barra de progresso: é a janela de análise
enchendo. Teclas: `q` sai, `r` reinicia, `1` a `4` trocam de algoritmo ao vivo.

Analisar um vídeo gravado:

```bash
cardiocam arquivo gravacao.mp4 --mostrar
```

Medir uma região da tela, por exemplo a janela de uma chamada de vídeo:

```bash
cardiocam tela --x 100 --y 200 --largura 640 --altura 480
```

Rodar sem câmera nenhuma, com pulso simulado de frequência conhecida (útil para
demonstrar o sistema e para conferir o erro):

```bash
cardiocam simular --bpm 84 --duracao 20
```

Comparar os algoritmos e gerar a tabela de métricas:

```bash
cardiocam avaliar --saida docs/metricas.md
```

Treinar o modelo de abstenção e medir erro contra cobertura:

```bash
cardiocam qualidade --saida docs/abstencao.md
```

## Os quatro algoritmos

Todos recebem a mesma série RGB e o mesmo pós-processamento. A única diferença
medida é como combinam os canais de cor.

| Método | Ideia | Referência |
| --- | --- | --- |
| GREEN | Usa só o canal verde, onde a hemoglobina mais absorve | Verkruysse et al., 2008 |
| CHROM | Duas projeções cromáticas combinadas para cancelar a reflexão especular | de Haan e Jeanne, 2013 |
| POS | Projeção num plano ortogonal à direção do tom de pele | Wang et al., 2017 |
| ICA | Separação cega de fontes nos três canais | Poh et al., 2010 |

Resultado sobre 56 cenários sintéticos com frequência conhecida, de 48 a
180 bpm (`cardiocam avaliar`):

| Algoritmo | Erro médio (bpm) | RMSE (bpm) | Acerto ±3 bpm |
| --- | ---: | ---: | ---: |
| VERDE | 12,01 | 22,45 | 71% |
| CHROM | 0,02 | 0,05 | 100% |
| POS | 0,02 | 0,03 | 100% |
| ICA | 12,01 | 22,45 | 71% |

Erro médio por cenário:

| Cenário | VERDE | CHROM | POS | ICA |
| --- | ---: | ---: | ---: | ---: |
| ideal | 0,02 | 0,00 | 0,00 | 0,01 |
| pulso fraco | 0,35 | 0,03 | 0,02 | 0,02 |
| ruído alto | 0,22 | 0,10 | 0,06 | 0,04 |
| deriva de iluminação | 0,03 | 0,01 | 0,01 | 0,01 |
| interferência na banda | 42,01 | 0,01 | 0,01 | 42,00 |
| interferência forte | 42,00 | 0,01 | 0,01 | 42,00 |
| captura irregular | 0,03 | 0,02 | 0,02 | 0,01 |

A linha que importa é a da interferência na banda. Todos empatam quando a
perturbação é uma rampa lenta de iluminação, porque o detrend e o passa-faixa
já a eliminam antes de qualquer algoritmo agir. O que separa os métodos é uma
oscilação de luz que cai *dentro* da faixa de 0,7 a 4 Hz, onde filtrar não
adianta.

Nesse caso o GREEN erra 42 bpm, exatamente a distância entre o pulso e a
interferência. Ele trava na perturbação, porque olhando só o brilho do canal
verde não há como distinguir "chegou mais sangue" de "chegou mais luz". CHROM e
POS distinguem porque o sangue muda a *cor* (absorve muito mais no verde que no
vermelho) enquanto a iluminação muda os três canais na mesma proporção.

O ICA falha pelo mesmo valor, por um motivo diferente e conhecido na literatura:
ele separa as fontes corretamente, mas precisa escolher qual componente é o
pulso, e escolhe a de espectro mais limpo. Uma interferência senoidal forte é
mais limpa que um pulso real. É a ambiguidade intrínseca da separação cega.

Por isso o padrão do sistema é POS.

## Saber quando não medir

Essa é a segunda metade do sistema, e ela tem autoridade para calar a resposta.

A primeira metade estima a frequência. O problema é que ela **sempre** devolve um
número: quando a janela é ruim, o número errado tem exatamente a mesma aparência
do certo, e quem lê não tem como distinguir.

```bash
cardiocam qualidade --saida docs/abstencao.md
```

O comando roda a bateria inteira pelo pipeline real, extrai as características de
cada janela, ajusta o modelo e imprime a curva.

### O que o modelo é

Uma **regressão logística bayesiana**, ajustada por aproximação de Laplace, em
numpy, sem dependência nova. Ela estima a chance de a janela estar dentro da
tolerância e o sistema recusa abaixo de um limiar.

Bayesiana por um motivo que decide o projeto. Um classificador comum devolve um
número e não separa dois casos muito diferentes: "vi muitas janelas assim e 70%
acertaram" e "nunca vi nada parecido, meu chute é 70%". Num sistema que vai
**recusar medir** com base nesse número, confundir os dois deixa a recusa
arbitrária justamente onde o modelo não tem experiência.

### O resultado, e ele tem dois lados

A medição que importa não é "quanto o erro cai". É **quanto ele cai conforme o
que se pede ao modelo**, e aqui a resposta depende do que o teste considera
inédito:

| Partição | Respondendo sempre | Melhor com abstenção |
| --- | ---: | ---: |
| Por **frequência** (artefato conhecido, bpm novo) | 8,16 bpm | **0,01 bpm** a 40,7% |
| Por **condição** (artefato nunca visto) | 10,52 bpm | 8,01 bpm a 16,4% |

Lado positivo: quando o tipo de artefato está representado no treino, o modelo
separa janela boa de ruim quase perfeitamente. No ponto de operação adotado, o
erro cai de 8,16 para 5,39 bpm recusando metade das janelas.

Lado negativo, e é o que vale saber: **o modelo não generaliza para um artefato
que nunca viu**. Mantendo cobertura razoável, o ganho some.

A conclusão prática é direta e não é confortável: um modelo de qualidade precisa
ser treinado nos artefatos que vão ocorrer, e o modo de falha dele é o artefato
inédito. Afirmar o contrário exigiria uma evidência que esta medição não dá.

### Por que o artefato inédito escapa

Porque o pior deles produz um espectro **excelente**.

A bateria de robustez separa dois regimes de movimento, e os dois foram medidos:

- **movimento de banda larga** espalha energia, derruba a relação sinal-ruído, e
  o sistema **recusa** pelo portão que já existia. É a falha benigna;
- **movimento rítmico**, de banda estreita dentro da faixa cardíaca, cria um pico
  concorrente limpo. O método trava nele e responde com confiança um número
  errado em trinta batimentos. Relação sinal-ruído alta, pico proeminente,
  frequência estável entre subjanelas: toda característica diz "boa janela".

### A característica que mais pesa

| Característica | Peso | Desvio |
| --- | ---: | ---: |
| `razao_harmonica` | +4,56 | 0,88 |
| `jitter_temporal` | +0,93 | 0,74 |
| `snr_db` | +0,93 | 0,38 |
| `proeminencia` | −0,94 | 0,32 |
| `correlacao_com_fundo` | −0,48 | 0,19 |

A razão harmônica domina, e a física explica: o pulso sobe rápido e desce
devagar, então deposita energia em 2f; uma oscilação de iluminação é senoidal e
não deposita. É exatamente a ideia que o relatório da disciplina tinha listado
como trabalho futuro para corrigir o critério de seleção do ICA, agora medida.

Quatro características ficam com peso zero e o desvio da priori, porque não
variam no caminho analítico, que não tem imagem: fração de pele, fração
saturada, deslocamento da região e saturação. Isso é a resposta certa, "não
observei", em vez de um número que seria lido como informação.

### O limite da calibração

O ECE fica em 0,26 depois da correção por temperatura, ajustada fora da amostra.
A descalibração que sobra está nas faixas do meio, onde a partição de calibração
tem poucas janelas. Está no diagrama de confiabilidade do relatório, com a
contagem de cada faixa, e não vale esconder: um limiar escolhido sobre
probabilidade descalibrada significa menos do que promete.

O raciocínio inteiro, com as alternativas descartadas, está na
[ADR 5](docs/adr/0005-abstencao-com-incerteza-calibrada.md).

## Testes

```bash
pytest -n 4                    # suíte completa
pytest -m "not lento"          # pula os testes de vídeo
pytest --cov=cardiocam         # com cobertura
```

São 2.198 casos em Python e 373 no navegador, e nenhum usa simulacro no lugar do
código real. A estratégia é a mesma em todos os níveis: gerar um sinal cuja
frequência verdadeira nós escolhemos, rodar o sistema de verdade e conferir o
que sai.

```bash
cd web && npm test     # os 373 casos da versão web, em Node
```

- **Unidade** (1.499 casos): resposta em frequência do filtro medida em dezenas
  de frequências, recuperação de senoides varrendo a banda de 45 a 220 bpm em
  passos de 2,5 bpm, remoção de tendência, rectificação por referência de fundo,
  detecção de picos, geometria, segmentação de pele em oito tons diferentes, e o
  modelo de qualidade: recuperação de pesos conhecidos, encolhimento da
  probabilidade longe do treino e aferição de calibração.
- **Integração** (601 casos): os quatro algoritmos sobre séries RGB modeladas
  fisicamente, variando tom de pele, taxa de quadros, amplitude do pulso, ruído
  e interferência; mais pipeline, fontes, interface, linha de comando e o treino
  da abstenção de ponta a ponta sobre a bateria inteira.
- **Ponta a ponta** (98 casos): vídeo renderizado quadro a quadro, cascata de
  Haar procurando o rosto de fato, até o número final.

Três testes existem para provar que o sistema sabe dizer "não sei", que é o
requisito mais importante de um medidor: parede lisa filmada, imagem saturada
em 255 e vídeo mais curto que a janela não podem produzir nenhum valor.

A cobertura é de 87%. O que fica de fora é quase todo o código que só executa
com hardware presente: abrir a webcam (49%) e o laço da janela gráfica (32%).
São as duas fronteiras com o sistema operacional, e testá-las exigiria câmera
física e servidor gráfico na integração contínua. O núcleo de sinais e de visão
fica entre 88% e 100%.

## Privacidade

Medição de sinal fisiológico é dado pessoal sensível segundo a LGPD. O projeto
foi construído com isso em mente:

- Todo o processamento é local. Nada é enviado para lugar nenhum, e o sistema
  não faz nenhuma requisição de rede.
- Nenhum quadro de vídeo é gravado em disco em momento algum. O comando
  `--salvar` grava apenas a série numérica (instante, bpm, relação sinal-ruído).
- Medir outra pessoa exige o consentimento dela. Isso vale especialmente para o
  modo de captura de tela, que consegue medir alguém numa chamada de vídeo.

## Limitações

Vale ser direto sobre o que o sistema não faz:

- **Não é dispositivo médico.** Não serve para diagnóstico, e a variabilidade
  cardíaca calculada aqui é indicativa, não clínica.
- **Não funciona a partir de uma foto.** É uma impossibilidade física, não uma
  limitação de implementação: frequência é uma medida temporal e uma imagem
  isolada não tem eixo do tempo. São necessários ao menos uns 10 segundos.
- Precisa de rosto de frente e luz suficiente. Contra a luz o sinal desaparece.
- **Movimento é tolerado, iluminação instável não.** O rastreamento resolve
  medir o lugar certo enquanto a pessoa se move, e os testes cobram isso com o
  rosto atravessando 25% do quadro. O que ele não resolve é o outro mecanismo:
  virar a cabeça muda o ângulo entre a pele e a luz, e isso muda a cor
  refletida por um motivo que não é o pulso. Luz estável continua valendo mais
  que ficar imóvel.
- **O número do cenário sintético é otimista por uma ou duas ordens de
  grandeza.** Erro de 0,02 bpm é assinatura de cenário fácil, não de bom
  desempenho: a literatura reporta 3,67 bpm para o POS em dados reais
  (rPPG-Toolbox, 2023). Qualquer resultado nosso abaixo de 1 bpm em dado real
  deve ser tratado como suspeita de erro de protocolo.
- Vídeo comprimido degrada bastante o resultado. Codecs de videochamada usam
  subamostragem de crominância e descartam justamente variações sutis em regiões
  homogêneas, que é a descrição exata do que procuramos. É por isso que a fonte
  de chamada avalia resolução, taxa de quadros e tamanho do rosto na captura, e
  avisa antes de medir.

## Estrutura

```
src/cardiocam/
  dominio/      entidades, tipo Result e erros; não depende de OpenCV nem de I/O
  sinais/       filtros, detrend, espectro, picos, janela deslizante
  visao/        detecção de rosto, rastreamento, regiões, máscara de pele
  rppg/         os quatro algoritmos, atrás de uma interface comum
  fontes/       webcam, arquivo, tela e simulador
  pipeline/     orquestração e estado da medição
  qualidade/    o modelo que decide se a janela presta, e a abstenção
  ui/           painel sobreposto ao vídeo
  avaliacao/    benchmark comparativo
web/
  js/           porte do processamento para o navegador
  testes/       373 casos rodando em Node, sem navegador
```

As dependências apontam sempre para dentro: `dominio` não importa nada do
projeto, e `pipeline` conhece as camadas de baixo apenas por interface. Isso é o
que permite trocar a webcam por um simulador nos testes sem tocar em uma linha
da lógica.

## Documentação

- [Relatório técnico](docs/RELATORIO.md): fundamentação teórica, metodologia e
  discussão dos resultados
- [Decisões de arquitetura](docs/adr/): o porquê das escolhas que não são óbvias

## Licença

MIT.
