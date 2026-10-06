# Projeto de pesquisa

> **Campos a preencher com o orientador.** Nome e titulação do orientador,
> unidade e departamento, laboratório ou grupo de pesquisa, e o título final.
> Quem submete no SISPROPe-IC e quem assina como pesquisador responsável na
> Plataforma Brasil é o orientador, por isso esses campos ficam em branco de
> propósito.

| Campo | Conteúdo |
| --- | --- |
| **Título** | Robustez a movimento e a tom de pele na estimativa de frequência cardíaca por câmera: um estudo comparativo de métodos cromáticos |
| **Modalidade** | Iniciação científica voluntária, fluxo contínuo |
| **Aluno** | Fabrício Júnio Almeida Dias |
| **Curso** | Ciência da Computação, UNISAGRADO, Bauru |
| **Orientador** | *a preencher* |
| **Unidade** | *a preencher* |
| **Duração** | 12 meses |
| **Área** | Ciência da Computação. Visão computacional e processamento de sinais |

---

## 1. Introdução

A frequência cardíaca é o sinal vital mais medido na prática clínica, e sua
aferição convencional exige contato: eletrodo, braçadeira ou oxímetro de dedo.
Há duas décadas existe uma alternativa sem contato, baseada num efeito óptico
simples: a cada batimento, o volume de sangue nos capilares da pele aumenta, e
a hemoglobina absorve mais luz. A pele, portanto, **muda de cor** no ritmo do
coração. A variação é pequena, entre 0,1% e 1% da intensidade refletida
(Verkruysse et al., 2008), mas é suficiente para ser recuperada de um vídeo
comum pela média espacial sobre milhares de pixels.

A técnica se chama **fotopletismografia remota**, abreviada como rPPG. Suas
aplicações vão de triagem em telemedicina a monitoramento de motorista e de
recém-nascido, casos em que o contato é inviável ou indesejado.

O problema é que o desempenho relatado em laboratório não se sustenta fora
dele, e por dois motivos bem documentados e ainda abertos.

**Movimento.** Os métodos cromáticos clássicos foram formulados supondo a
cabeça aproximadamente parada. Mexer a cabeça muda o ângulo entre a pele e a
fonte de luz, o que altera a reflexão; e desloca a região medida, o que troca o
conjunto de pixels promediados. As duas coisas produzem variações de uma a duas
ordens de grandeza maiores que o pulso, e parte delas cai **dentro** da faixa
de frequência cardíaca, onde filtrar não resolve. Nos conjuntos públicos, o
erro absoluto médio salta de cerca de 0,9 bpm em cenário estático para 2,8 a
4,8 bpm com movimento (Zhao et al., 2024), e chega a 9,6 a 11,8 bpm em cenário
de direção veicular (MS-rPPG, 2026).

**Tom de pele.** A melanina absorve luz na mesma região do espectro em que a
hemoglobina produz o sinal útil. Pele mais pigmentada devolve menos sinal, e o
método degrada. O agravante é metodológico: os dois conjuntos de dados mais
usados na área, UBFC-rPPG e PURE, foram coletados quase inteiramente com
participantes de fototipos 2 e 3 na escala de Fitzpatrick. Ou seja, **a
literatura mediu sobretudo pele clara** e reporta uma média que não se aplica
igualmente a todos. O conjunto MMPD (Tang et al., 2023) foi construído
justamente para cobrir fototipos 3 a 6 e tornar essa comparação possível.

Este projeto ataca as duas questões com o mesmo instrumento: um sistema de rPPG
já implementado e validado, com quatro algoritmos clássicos, que será submetido
a um protocolo de avaliação controlado em movimento e em tom de pele.

### 1.1 Objetivo geral

Quantificar como o movimento do participante, o movimento da câmera e o tom de
pele degradam a estimativa de frequência cardíaca por câmera, e avaliar se
correções de baixo custo computacional recuperam parte dessa perda.

### 1.2 Objetivos específicos

1. Construir um gerador de cenário sintético que reproduza os quatro mecanismos
   físicos pelos quais o movimento corrompe o sinal, com frequência verdadeira
   conhecida, permitindo medir erro com exatidão.
2. Medir a degradação dos quatro métodos (GREEN, CHROM, POS e ICA) em função da
   amplitude e da banda de frequência do movimento.
3. Medir a degradação em função do tom de pele, e relatar o resultado **por
   fototipo**, nunca só pela média.
4. Reproduzir a avaliação em dados públicos (UBFC-rPPG, PURE e MMPD), para
   situar os resultados em relação à literatura.
5. Implementar e avaliar correções candidatas: rectificação por referência de
   fundo, estabilização da região de interesse, rejeição de janela por índice de
   qualidade e abstenção com cobertura declarada.
6. Coletar um conjunto local pequeno, com oxímetro como referência e aprovação
   de comitê de ética, cobrindo fototipos variados e condições de movimento
   controladas.
7. Avaliar a viabilidade da medição a partir de vídeo comprimido de
   videochamada, cenário de aplicação prática e ainda pouco medido.

### 1.3 Hipóteses

- **H1.** A degradação por movimento não é causada principalmente pelo
  deslocamento da região de interesse, que o rastreamento compensa, mas pela
  variação da **componente especular** da reflexão, que tem a cromaticidade do
  iluminante e por isso viola a hipótese de tom de pele fixo em que CHROM e POS
  se apoiam.
- **H2.** A rectificação por referência de fundo, eficaz contra variação global
  de iluminação, **perde eficácia quando a câmera se move**, porque o trecho de
  fundo usado como referência deixa de ser o mesmo trecho ao longo do tempo.
- **H3.** A perda por tom de pele é majoritariamente perda de relação
  sinal-ruído, e não viés sistemático. Se isso se confirmar, uma janela de
  análise mais longa recupera parte da perda; se o viés existir, não recupera.
- **H4.** Abstenção com limiar calibrado por índice de qualidade melhora o erro
  entre as janelas aceitas mais do que qualquer das correções de sinal, ao custo
  de cobertura.

**Estado das hipóteses na camada sintética**, antes do início da IC e declarado
como trabalho anterior:

| | Instrumento | Primeira medida |
| --- | --- | --- |
| H1 | construído | **sim**, e com resultado: há um limiar de validade |
| H2 | construído | pendente |
| H3 | construído | pendente |
| H4 | construído | **sim**, e o resultado é parcialmente negativo |

**H1 saiu mais estreita do que entrou.** Sob luz neutra, CHROM e POS cancelam a
componente especular como foram projetados para cancelar, e o erro fica em
centésimos de bpm. A degradação aparece quando a cromaticidade do iluminante se
afasta: medindo, o CHROM quebra em desvio 0,75 e o POS em 1,0, nessa ordem, que
é a que a literatura prevê. O VERDE erra em todos os pontos, por não ter proteção
cromática nenhuma.

A pergunta para a camada de dado real passa a ser **"a iluminação de uma sala se
afasta o bastante do neutro para cruzar esse limiar?"**, que é mais estreita e
mais fácil de responder.

**H4 recebeu uma ressalva que muda o que se pode prometer.** A abstenção funciona
quando o tipo de artefato está representado no treino, e **não generaliza para um
artefato inédito**. O motivo é físico: o pior artefato, que é a trava num pico
rítmico dentro da banda cardíaca, produz um espectro excelente, e toda
característica de janela diz "boa janela".

A consequência para o desenho da IC é concreta: a camada 3 precisa cobrir os
tipos de artefato que se quer detectar, e o relatório final precisa declarar
quais ficaram de fora. Tabelas e método em `05-resultados-preliminares.md`,
seções 5.2 a 5.6.

### 1.4 Contribuição esperada

Um estudo comparativo reprodutível, com código aberto e protocolo publicado,
que relate desempenho **estratificado por movimento e por fototipo** em vez de
uma média única. A contribuição não é um algoritmo novo: é medição honesta de
algoritmos conhecidos nas condições em que eles costumam ser usados e raramente
são avaliados.

### 1.5 Justificativa

Três razões.

**Científica.** A estratificação por fototipo é reconhecida como lacuna da área,
e os conjuntos que a permitem são recentes. Há espaço para contribuição
metodológica sem necessidade de modelo novo nem de infraestrutura caraffa.

**Técnica.** O ponto de partida não é do zero. Existe um sistema completo,
testado e funcionando, descrito na seção de resultados preliminares. A IC
começa com a ferramenta pronta, o que é incomum e reduz muito o risco de o
projeto não terminar.

**De formação.** O projeto cruza visão computacional, processamento de sinais,
estatística aplicada e aprendizado de máquina, que é exatamente a formação que
pretendo aprofundar no mestrado.

---

## 2. Referencial teórico

### 2.1 O princípio físico

A luz que chega à câmera a partir da pele tem duas componentes, separadas pelo
modelo de reflexão dicromática (Shafer, 1985):

- a **difusa**, que penetra o tecido, interage com o sangue e volta com a cor da
  pele modulada pelo volume sanguíneo. É ela que carrega o pulso;
- a **especular**, que reflete na superfície sem penetrar, e volta com a cor da
  **luz**, não da pele. Não carrega pulso nenhum, e é pura interferência.

Somam-se a isso a variação de iluminação do ambiente e o ruído do sensor. O
problema do rPPG é recuperar a modulação difusa de dentro dessa soma.

### 2.2 Os métodos e o que cada um supõe

| Método | Ideia | Hipótese que pode falhar | Referência |
| --- | --- | --- | --- |
| GREEN | usa só o canal verde, onde a hemoglobina mais absorve | que toda variação do verde é pulso | Verkruysse et al., 2008 |
| CHROM | combina duas projeções cromáticas para cancelar a reflexão especular | que o tom de pele é o padronizado assumido | de Haan e Jeanne, 2013 |
| POS | projeta num plano ortogonal à direção do tom de pele | a mesma, de forma explícita na construção do plano | Wang et al., 2017 |
| ICA | separação cega de fontes nos três canais | que a componente de espectro mais limpo é o pulso | Poh et al., 2010 |

A coluna do meio é o eixo do projeto. GREEN falha quando a iluminação oscila
dentro da banda cardíaca, porque não tem como distinguir "chegou mais sangue" de
"chegou mais luz". CHROM e POS resolvem isso porque o sangue muda a *cor* e a
iluminação muda os três canais na mesma proporção. Mas os dois compram essa
robustez assumindo uma cromaticidade de pele fixa, e é essa hipótese que
movimento e pigmentação atacam. ICA não assume tom de pele, e em troca herda a
ambiguidade da separação cega: uma interferência senoidal forte tem espectro
mais limpo que um pulso real, e o método escolhe a interferência.

### 2.3 Métodos aprendidos

Desde 2018 a área migrou para redes neurais treinadas ponta a ponta, e elas
lideram as tabelas. São relevantes aqui como **referência superior**, não como
objeto: DeepPhys, PhysNet, EfficientPhys e, mais recentemente, arquiteturas com
atenção periódica e modelos de espaço de estados. Métodos não supervisionados
recentes alcançam 0,66 a 0,77 bpm de erro absoluto médio em UBFC-rPPG e PURE
(PRISM, 2026).

A decisão metodológica deste projeto é começar pelos clássicos, por três
motivos: rodam em CPU e em tempo real, são interpretáveis o suficiente para que
a causa de uma falha seja identificável, e servem de linha de base obrigatória.
Um método aprendido entra na etapa 5 como comparação, não como ponto de partida.

**Há aprendizado no sistema, e ele está noutro lugar.** O modelo que decide
quando recusar medir é uma regressão logística bayesiana sobre características da
janela, descrita em 5.3. A escolha de não usar rede aqui é deliberada e tem três
razões. A primeira é de dado: são algumas centenas de janelas, regime em que um
modelo com uma dezena de parâmetros e priori própria é mais defensável do que um
com milhões. A segunda é que os pesos precisam ser **lidos**, porque parte do
valor do resultado está em qual característica o modelo usou, e foi assim que ele
reencontrou sozinho a falha conhecida do ICA. A terceira é que a decisão é
recusar, e recusa feita por modelo que não sabe quando não sabe seria a mesma
patologia que o trabalho inteiro critica.

### 2.4 Números de referência da literatura

Valores de erro absoluto médio em batimentos por minuto, para situar o que é um
resultado bom:

| Condição | Método | Erro (bpm) | Fonte |
| --- | --- | ---: | --- |
| UBFC-rPPG, estático | CHROM | 5,77 | rPPG-Toolbox, 2023 |
| UBFC-rPPG, estático | POS | 3,67 | rPPG-Toolbox, 2023 |
| UBFC-rPPG, estático | não supervisionado recente | 0,66 | PRISM, 2026 |
| MMPD, estático | aprendido com atenção mascarada | 0,87 | MAR-rPPG, 2024 |
| MMPD, com movimento | aprendido com atenção mascarada | 2,83 | MAR-rPPG, 2024 |
| Direção veicular, movimento grande | modelo de espaço de estados | 9,60 | MS-rPPG, 2026 |

**Esta tabela é o controle de honestidade do projeto.** Qualquer resultado nosso
abaixo de 1 bpm em dado real deve ser tratado como suspeita de erro de
protocolo, não como sucesso.

### 2.5 Compressão de vídeo

Codec de videochamada aplica subamostragem de crominância e descarta variações
temporais sutis em regiões homogêneas, porque elas não afetam a percepção. Essa
é a descrição exata do sinal de rPPG. A literatura mede que a compressão H.264
degrada a relação sinal-ruído do rPPG, com impacto maior nos canais azul e
vermelho e em resoluções baixas. É a razão pela qual o objetivo 7 é formulado
como estudo de **viabilidade**, e não como funcionalidade assumida.

---

## 3. Método

### 3.1 Delineamento

Estudo experimental comparativo em três camadas, da mais controlada à menos:

**Camada 1, sintética.** Frequência verdadeira escolhida por nós, portanto erro
mensurável com exatidão e sem referência externa. Permite varrer um parâmetro de
cada vez, o que dado real não permite. É onde as hipóteses H1 e H2 são testadas,
porque só aqui é possível ligar e desligar a componente especular isoladamente.

**Camada 2, dados públicos.** UBFC-rPPG, PURE e MMPD, com o protocolo de
avaliação e as métricas que a área usa, para que o resultado seja comparável.
MMPD é o que permite estratificar por fototipo e por atividade.

**Camada 3, coleta local.** Conjunto pequeno, com oxímetro de pulso como
referência, protocolo de movimento controlado e recrutamento buscando variedade
de fototipo. Depende de aprovação de comitê de ética.

A ordem é deliberada e é a mesma que uso nos meus outros trabalhos: **o método é
provado onde a resposta é conhecida antes de encostar no dado onde não é.**

### 3.2 Modelo do artefato de movimento

O gerador sintético reproduz quatro mecanismos, separáveis e controláveis um a
um:

1. **sombreado difuso por pose**, multiplicativo e igual nos três canais. É o
   controle do experimento: CHROM e POS devem cancelá-lo por construção;
2. **reflexo especular por pose**, aditivo e com a cromaticidade do iluminante.
   É o termo que H1 aponta como causa real da degradação;
3. **desregistro da região de interesse**, que surge do atraso intrínseco do
   suavizador exponencial do rastreador;
4. **movimento da câmera**, que arrasta o fundo junto e por isso corrompe a
   referência de iluminação, conforme H2.

Mais desfoque por movimento e resposta do controle automático de exposição, de
segunda ordem mas presentes em câmera de notebook.

O movimento é gerado como ruído de banda larga, e não senoidal, com a faixa
invadindo de propósito a banda cardíaca de 0,7 a 4 Hz. É essa sobreposição que
impede o filtro passa-faixa de resolver o problema.

### 3.3 Métricas

- **erro absoluto médio** e **raiz do erro quadrático médio**, em bpm;
- **correlação de Pearson** entre estimado e referência;
- **acerto a ±3 bpm** e a ±5 bpm, que é o critério prático;
- **relação sinal-ruído** da banda, em dB, como índice de qualidade;
- **cobertura**, isto é, a fração de janelas em que o sistema aceita responder.

A cobertura entra porque um medidor que recusa 70% das janelas e acerta nas
demais não é comparável a um que responde sempre. Relatar erro sem cobertura
seria comparar coisas diferentes.

### 3.4 Análise estatística

Comparação dos quatro métodos sobre os mesmos cenários pelo teste de Friedman,
e, se houver diferença global, comparações pareadas por Wilcoxon com correção de
Benjamini-Hochberg para controlar a taxa de falsas descobertas. Tamanho de
efeito relatado junto com o valor-p, porque com muitos cenários tudo fica
significativo e o valor-p para de informar.

Estratificação obrigatória por fototipo e por condição de movimento. A média
agregada é relatada, mas nunca sozinha.

### 3.5 Local da pesquisa

As camadas 1 e 2 são inteiramente computacionais e rodam em equipamento próprio
do aluno, sem envolver participantes.

A camada 3 ocorre em **sala de laboratório da unidade do orientador**, com porta
fechada, sem circulação de terceiros durante a coleta, e com iluminação
artificial controlável, que é requisito do protocolo porque uma das cinco
condições é iluminação baixa. A sala específica é indicada pelo orientador na
submissão.

Nenhuma coleta ocorre em ambiente externo, em domicílio ou de forma remota.

### 3.6 População estudada, na camada 3

**Número de participantes: 30.** Adultos maiores de 18 anos, de ambos os sexos,
sem exigência de condição clínica, recrutados por convite aberto na comunidade
acadêmica.

**Estratificação: 5 participantes por grupo de fototipo de Fitzpatrick**, do I
ao VI.

**Justificativa do número.** Não vem de cálculo de poder sobre efeito
hipotético, e é melhor dizer por quê. O desfecho primário é a comparação de
quatro métodos sobre os **mesmos** participantes e as **mesmas** condições, isto
é, um delineamento pareado em blocos. O que determina o poder aqui é o número de
blocos, e cada participante contribui com cinco condições, totalizando 150
blocos de comparação pareada. Para o teste de Friedman com quatro tratamentos,
esse número de blocos detecta efeito de magnitude média com folga, e a
literatura da área trabalha com conjuntos dessa escala: o MMPD, que é a
referência direta deste projeto para estratificação por fototipo, tem **33
participantes**. Adotar 30 mantém a comparabilidade e é factível de recrutar em
três meses.

O desfecho secundário, a comparação **entre** fototipos, é o que tem poder
limitado com 5 participantes por grupo, e isso está declarado como limitação em
vez de maquiado. A camada sintética cobre essa pergunta com qualquer resolução
desejada, porque lá o tom de pele é um parâmetro que se varre; a camada local
serve para confirmar que o efeito observado no sintético aparece em pele de
verdade, não para estimar sua magnitude com precisão.

**Critérios de inclusão:** idade igual ou superior a 18 anos; concordância com o
termo de consentimento e com o termo de uso de imagem.

**Critérios de exclusão:** uso de maquiagem espessa na face, que altera a
reflexão da pele; barba cobrindo as bochechas, por reduzir a área de pele
mensurável; arritmia conhecida, porque a frequência instantânea deixa de ser bem
definida e a referência do oxímetro perde sentido; uso de marca-passo; e
qualquer desconforto manifestado com a filmagem, em qualquer momento.

**Critério de descontinuidade:** desistência do participante, a qualquer
momento e sem necessidade de justificativa, com descarte imediato do material já
coletado dele.

### 3.7 Riscos e benefícios

**Riscos.** Mínimos e não físicos. O procedimento é filmar o rosto por alguns
minutos e usar um oxímetro de dedo, ambos não invasivos. O risco real é de
**privacidade**, por se tratar de imagem de rosto e de dado de saúde, e está
tratado na seção de ética.

Há um risco secundário que vale declarar: o participante pode interpretar a
medição como informação clínica. O termo de consentimento afirma de forma
explícita que o sistema **não é dispositivo médico** e que nenhum valor medido
serve para diagnóstico.

**Benefícios.** Não há benefício direto ao participante. O benefício é coletivo:
medição de desempenho estratificada por tom de pele em uma técnica que tem
desempenho desigual documentado, o que é pré-requisito para que ela seja usada
de forma justa.

### 3.8 Tratamento, guarda e descarte dos dados

Esta seção existe porque o material coletado é **imagem de rosto** combinada com
**dado de saúde**, e as duas coisas juntas são dado pessoal sensível segundo a
Lei Geral de Proteção de Dados. O comitê vai olhar isto com atenção, e com
razão.

**O que é coletado.** Vídeo do rosto, série de frequência cardíaca do oxímetro,
fototipo autoclassificado, idade e sexo. Nada mais. Não há coleta de nome,
documento, endereço, contato, histórico clínico ou qualquer identificador
adicional.

**Identificação.** Cada participante recebe um código no formato `P01` a `P30` no
momento da coleta. O nome aparece **somente** no termo de consentimento
assinado, que é guardado em papel, separado do material de pesquisa, em armário
com chave sob responsabilidade do orientador. Não existe, em lugar nenhum,
arquivo que ligue nome a código. A desidentificação é, portanto, irreversível
depois da coleta, e isso é deliberado.

**Onde fica.** Em disco de computador da unidade ou do aluno, **com cifragem de
volume**, sem cópia em serviço de nuvem, sem envio por mensagem ou por e-mail e
sem backup fora do dispositivo cifrado. Acesso restrito ao aluno e ao
orientador.

**Processamento.** Todo o processamento é local. O sistema não faz requisição de
rede em nenhum momento, e isso é propriedade verificada do software, não
promessa: ele não tem dependência de rede no caminho de medição.

**O que é publicado.** Apenas resultados agregados e estatísticas. **Nenhum
quadro de vídeo, nenhuma imagem de participante e nenhum valor individual são
publicados**, e o conjunto de vídeos não é compartilhado nem disponibilizado
como base pública. Se houver interesse futuro em publicar o conjunto, isso exige
novo consentimento específico e novo parecer, e não está previsto aqui.

**Prazo de guarda e descarte.** O material de pesquisa é guardado por **5 anos**
contados do fim da pesquisa, prazo usual para fins de verificação de
integridade científica, e **destruído** em seguida: apagamento seguro dos
arquivos e fragmentação dos termos em papel. O participante pode pedir a
destruição do material dele a qualquer momento antes disso, sem precisar
justificar, e nesse caso a destruição é imediata.

**Incidente.** Em caso de perda ou acesso indevido ao material, o orientador
comunica o comitê de ética e os participantes afetados.

### 3.9 Orçamento

| Item | Finalidade | Valor estimado | Fonte |
| --- | --- | ---: | --- |
| Oxímetro de pulso de dedo | referência de frequência cardíaca | R$ 120,00 | aluno |
| Câmera | captura | já adquirida | aluno |
| Computador para processamento | análise | já disponível | aluno |
| Lâmpada regulável | condição de iluminação baixa | R$ 80,00 | aluno |
| Disco externo com cifragem | guarda do material | R$ 250,00 | aluno |
| **Total** | | **R$ 450,00** | |

**Não há solicitação de recurso à instituição nem a agência de fomento.** Todos
os itens são custeados pelo aluno. Os conjuntos de dados públicos são de acesso
acadêmico gratuito, mediante termo de uso. O software usado é livre: Python,
NumPy, SciPy e OpenCV.

Não há previsão de ressarcimento a participantes, porque não há despesa para
eles: a coleta ocorre na própria unidade, em horário combinado, sem deslocamento
específico. Também não há pagamento por participação, conforme a norma.

### 3.10 Resultados e divulgação

- relatório final à UNESP, conforme exigência da modalidade;
- apresentação no Congresso de Iniciação Científica da UNESP, que é condição do
  certificado;
- código e protocolo em repositório público, para reprodutibilidade;
- submissão a evento ou periódico da área, a definir com o orientador conforme o
  resultado.

Os participantes recebem, se quiserem, um resumo em linguagem simples dos
resultados agregados do estudo. Nenhum resultado individual é devolvido como
informação de saúde, justamente porque não é.

---

## 4. Viabilidade

| Recurso | Situação |
| --- | --- |
| Sistema de rPPG implementado | **pronto**, 2.005 testes automatizados |
| Gerador de cenário sintético | **pronto**, estendido com movimento neste projeto |
| Câmera | **adquirida** pelo aluno |
| Oxímetro de pulso como referência | a adquirir, custo baixo |
| Dados públicos | UBFC-rPPG, PURE e MMPD, acesso por solicitação acadêmica |
| Equipamento de processamento | próprio, roda em CPU |
| Aprovação ética | a submeter, 3 meses reservados no cronograma |

**Não há dependência de recurso financeiro para as camadas 1 e 2**, que juntas
já respondem às quatro hipóteses. A camada 3 agrega validade externa e é a parte
sujeita a prazo de comitê de ética.

---

## 5. Referências

Ver [09-referencias.md](09-referencias.md) para a lista completa com o número que
cada trabalho reporta.
