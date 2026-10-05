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

**O rosto é rastreado, sem baixar modelo nenhum.** As três regiões medidas
ficam ancoradas na caixa do rosto, localizada pela mancha de pele usando o
classificador de crominância que o projeto já tinha testado. A pessoa pode se
mover.

O caminho óbvio seria o BlazeFace via MediaPipe, e ele foi medido e descartado
por três motivos, nesta ordem de peso: o runtime em WebAssembly tem 9,3 MB e o
pacote passa de 18 MB, o que é inviável numa página que precisa abrir no
celular; a política de segurança do site teria de ser afrouxada em duas
diretivas para permitir download de terceiro; e modelo em WebAssembly não roda
na suíte em Node, onde moram os 386 casos do navegador.

A limitação honesta da escolha: localizar por cor não distingue rosto de
qualquer outra mancha de pele grande. Mão na frente da câmera ou braço nu
atravessando o quadro deslocam a caixa, e a rejeição de salto só cobre o caso
brusco.

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
| VERDE | 12,09 | 22,46 | 71% |
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

## Testes

```bash
pytest -n 4                    # suíte completa
pytest -m "not lento"          # pula os testes de vídeo
pytest --cov=cardiocam         # com cobertura
```

São 2.005 casos em Python e 386 no navegador, e nenhum usa simulacro no lugar do
código real. A estratégia é a mesma em todos os níveis: gerar um sinal cuja
frequência verdadeira nós escolhemos, rodar o sistema de verdade e conferir o
que sai.

```bash
cd web && npm test     # os 386 casos da versão web, em Node
```

- **Unidade** (1.355 casos): resposta em frequência do filtro medida em dezenas
  de frequências, recuperação de senoides varrendo a banda de 45 a 220 bpm em
  passos de 2,5 bpm, remoção de tendência, rectificação por referência de fundo,
  detecção de picos, geometria, segmentação de pele em oito tons diferentes.
- **Integração** (552 casos): os quatro algoritmos sobre séries RGB modeladas
  fisicamente, variando tom de pele, taxa de quadros, amplitude do pulso, ruído
  e interferência; mais pipeline, fontes, interface e linha de comando.
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
  ui/           painel sobreposto ao vídeo
  avaliacao/    benchmark comparativo
web/
  js/           porte do processamento para o navegador
  testes/       276 casos rodando em Node, sem navegador
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
