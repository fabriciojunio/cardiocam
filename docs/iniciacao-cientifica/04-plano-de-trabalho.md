# Plano de trabalho e cronograma

Duração: 12 meses. Dedicação declarada: 12 horas semanais, que é o piso que a
FAPESP exige de bolsista de IC e serve de referência razoável também na
modalidade voluntária.

## O princípio que organiza o cronograma

**Nada do que depende de aprovação ética está no caminho crítico dos primeiros
meses.** As camadas 1 e 2 do método, que juntas respondem às quatro hipóteses,
usam dados sintéticos e dados públicos. Elas começam no mês 1 e terminam no mês
8. A coleta com pessoas entra no mês 7, já com parecer em mãos.

Isso tem uma consequência prática que vale dizer na conversa com o professor: se
o comitê de ética atrasar, ou se a coleta local não acontecer, **o projeto ainda
tem resultado publicável**. Projeto de IC que morre esperando parecer é comum, e
esse desenho evita o problema.

## Cronograma

| Atividade | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 1. Revisão bibliográfica sistemática | ● | ● | ● | | | | | | | ● | | |
| 2. Gerador de cenário de movimento | ● | ● | | | | | | | | | | |
| 3. Experimento de movimento, camada sintética | | ● | ● | ● | | | | | | | | |
| 4. Experimento de tom de pele, camada sintética | | | ● | ● | | | | | | | | |
| 5. Submissão ao comitê de ética | ● | ● | | | | | | | | | | |
| 6. Obtenção e preparo dos dados públicos | | | ● | ● | | | | | | | | |
| 7. Reprodução do protocolo em UBFC, PURE e MMPD | | | | ● | ● | ● | | | | | | |
| 8. Implementação e avaliação das correções | | | | | ● | ● | ● | ● | | | | |
| 9. Relatório parcial | | | | | ● | | | | | | | |
| 10. Coleta local, após parecer aprovado | | | | | | | ● | ● | ● | | | |
| 11. Análise estatística consolidada | | | | | | | | | ● | ● | | |
| 12. Estudo de viabilidade em vídeo comprimido | | | | | | | | | ● | ● | | |
| 13. Redação do artigo | | | | | | | | | | ● | ● | |
| 14. Preparo e apresentação no CIC | | | | | | | | | | | ● | ● |
| 15. Relatório final | | | | | | | | | | | | ● |

## Detalhamento por atividade

### 1. Revisão bibliográfica sistemática (meses 1 a 3, revisita no mês 10)

Levantamento nas bases IEEE Xplore, ACM, PubMed e arXiv, com os termos `remote
photoplethysmography`, `rPPG`, `motion robustness`, `skin tone`, `fairness`.
Extração padronizada: conjunto de dados usado, condição avaliada, métrica,
número reportado. O produto é uma tabela comparável, não um texto corrido.

A revisita no mês 10 existe porque a área publica rápido e o artigo precisa
citar o estado da arte na data da submissão, não na data em que começamos.

### 2. Gerador de cenário de movimento (meses 1 e 2)

Extensão do simulador já existente com os quatro mecanismos físicos descritos no
projeto: sombreado difuso por pose, reflexo especular por pose, desregistro da
região de interesse e movimento de câmera. Mais desfoque por movimento e
resposta do controle automático de exposição.

**Critério de aceitação.** Com todos os parâmetros novos no padrão neutro, as
séries geradas têm de sair idênticas às de antes, bit a bit. Um simulador que
muda de resposta ao ganhar um recurso invalida toda medição anterior sem avisar.

*Estado: concluída na camada sintética.* Os quatro mecanismos entraram:
componente especular com cromaticidade de iluminante configurável, movimento de
câmera com série de fundo gerada, desregistro da região e tons de pele. Desfoque
por movimento e resposta do controle de exposição continuam pendentes, e ficam
para a reavaliação sob movimento forte.

O critério de aceitação foi transformado em teste automatizado
(`test_os_parametros_novos_no_padrao_nao_mudam_nada`): com tudo no padrão, a
série sai idêntica à anterior, e a tabela dos 56 cenários continua comparável
com a publicada.

### 3. Experimento de movimento, camada sintética (meses 2 a 4)

Varredura fatorial: amplitude de movimento, banda de frequência do movimento,
mecanismo ligado ou desligado, quatro algoritmos, várias sementes. O piso do
acaso é a média de várias sementes, nunca um sorteio.

**O experimento decisivo de H1** é ligar o sombreado difuso e o reflexo
especular separadamente. Se a degradação vier sobretudo do especular, H1 se
confirma e a conclusão é que o problema não é o rastreamento, é a hipótese de
cromaticidade.

**O experimento de H2** é comparar movimento de cabeça contra movimento de
câmera com a rectificação por fundo ligada. Se a rectificação ajudar no
primeiro e **piorar** no segundo, H2 se confirma.

*Estado: primeira varredura de H1 feita, e ela estreitou a hipótese.* Sob luz
branca CHROM e POS cancelam o especular como foram projetados para cancelar; a
degradação aparece a partir de um afastamento cromático do iluminante, e o
limiar foi medido. A pergunta para a camada de dado real passa a ser se a
iluminação de uma sala cruza esse limiar. Tabela em
`05-resultados-preliminares.md`, seção 5.2. A varredura fatorial completa, com
várias sementes, continua pendente.

### 4. Experimento de tom de pele, camada sintética (meses 3 e 4)

Varredura do tom de pele base cobrindo a escala de Fitzpatrick, com o restante
dos parâmetros fixos. Resultado relatado **por fototipo**, com a média agregada
apresentada depois e nunca sozinha.

**O experimento de H3** separa perda de relação sinal-ruído de viés
sistemático: se for só relação sinal-ruído, alongar a janela recupera parte;
se houver viés, não recupera e o erro fica.

### 5. Submissão ao comitê de ética (meses 1 e 2)

Cadastro na Plataforma Brasil, preenchimento dos formulários, anexo do projeto e
do TCLE, folha de rosto assinada. Submissão com a antecedência de 30 dias que a
norma exige. Ver [Ética e Plataforma Brasil](06-etica-plataforma-brasil.md).

### 6. Obtenção e preparo dos dados públicos (meses 3 e 4)

UBFC-rPPG, PURE e MMPD exigem solicitação acadêmica, normalmente com termo de
uso assinado pelo orientador. O prazo de resposta é incerto, e é por isso que o
pedido entra no mês 3 e não no mês 6.

MMPD é o conjunto que torna o objetivo de tom de pele possível: 33
participantes, fototipos 3 a 6, quatro atividades e quatro condições de
iluminação.

### 7. Reprodução do protocolo em dados públicos (meses 4 a 6)

Aplicação do mesmo pipeline aos três conjuntos, com as métricas da área. O
objetivo primeiro é **reproduzir** os números publicados dos métodos clássicos,
como controle de que nosso protocolo está correto. Só depois vêm os números
novos.

**Marco de validação.** Se o nosso POS em UBFC-rPPG não cair próximo dos 3,67
bpm que a literatura reporta, o problema é nosso protocolo, e nada do que vem
depois vale. Esse é o portão de qualidade do projeto.

### 8. Implementação e avaliação das correções (meses 5 a 8)

Quatro candidatas, avaliadas uma a uma e depois combinadas:

1. rectificação por referência de fundo (já implementada);
2. estabilização da região de interesse com rejeição de salto (já implementada,
   a ser reavaliada sob movimento forte);
3. rejeição de janela por índice de qualidade;
4. abstenção com cobertura declarada, isto é, o sistema recusa responder quando
   a qualidade não dá, e a taxa de recusa é relatada junto com o erro.

**O experimento de H4** compara o ganho da abstenção contra o ganho das
correções de sinal, com a cobertura declarada em cada ponto. A curva de erro
contra cobertura é o produto desta etapa.

*Estado: instrumento pronto e primeira curva medida na camada sintética.* O
modelo é uma regressão logística bayesiana sobre características da janela, com
três partições e agrupamento por condição, e `cardiocam qualidade` produz a
curva inteira. Primeira medida: o erro cai de 10,51 para 6,01 bpm recusando
12,5% das janelas. Falta o que só dado real responde, que é se a ordenação
aprendida em cenário sintético transfere para sujeito de verdade. Seção 5.3 de
`05-resultados-preliminares.md` e ADR 5 do repositório.

### 9. Relatório parcial (mês 5)

Conforme o calendário da unidade.

### 10. Coleta local (meses 7 a 9, após parecer aprovado)

Protocolo por participante, cerca de 15 minutos:

| Trecho | Duração | Condição |
| --- | --- | --- |
| 1 | 60 s | parado, iluminação de ambiente |
| 2 | 60 s | rotação lenta da cabeça |
| 3 | 60 s | falando |
| 4 | 60 s | parado, iluminação baixa |
| 5 | 60 s | câmera na mão, tremendo |

Referência simultânea por oxímetro de pulso de dedo. Fototipo de Fitzpatrick
registrado por autoclassificação com a escala visual, que é o procedimento usado
na literatura da área.

As cinco condições espelham as do MMPD de propósito, para que o nosso conjunto
seja comparável com ele.

### 11. Análise estatística consolidada (meses 9 e 10)

Friedman sobre os quatro métodos, e se houver diferença global, Wilcoxon
pareado com correção de Benjamini-Hochberg. Tamanho de efeito junto com o
valor-p. Estratificação por fototipo e por condição.

### 12. Estudo de viabilidade em vídeo comprimido (meses 9 e 10)

Pipeline padronizado com FFmpeg, H.264, subamostragem 4:2:0, varrendo o fator de
qualidade e a resolução. A pergunta é se a medição sobrevive ao que uma
videochamada faz com a imagem, e a literatura sugere que a resposta é "mal".
Relatar isso com número é mais útil que prometer que funciona.

### 13. Redação do artigo (meses 10 e 11)

### 14. Preparo e apresentação no CIC (meses 11 e 12)

Condição do certificado. Resumo, pôster ou apresentação oral conforme o formato
do congresso no ano.

### 15. Relatório final (mês 12)

## Produtos entregáveis

| Produto | Mês |
| --- | --- |
| Gerador de cenário de movimento, com código aberto | 2 |
| Protocolo de avaliação publicado e reprodutível | 4 |
| Resultado estratificado por movimento | 4 |
| Resultado estratificado por fototipo | 4 |
| Relatório parcial | 5 |
| Curva de erro contra cobertura | 8 |
| Conjunto de dados local, se o CEP aprovar | 9 |
| Artigo submetido | 11 |
| Apresentação no CIC | 12 |
| Relatório final | 12 |

## Riscos do plano, e o que fazer

| Risco | Probabilidade | Mitigação |
| --- | --- | --- |
| Parecer do CEP atrasa | alta | camadas 1 e 2 não dependem dele e já dão resultado publicável |
| Conjunto público negado ou demorado | média | pedido no mês 3; camada sintética não depende de nenhum |
| Recrutamento insuficiente nos fototipos 5 e 6 | alta | é a própria lacuna que o projeto estuda; relatar o que foi coletado e declarar o limite, em vez de agregar e esconder |
| Nosso número não reproduz a literatura | média | é portão de qualidade no mês 6, antes de qualquer conclusão |
| Resultado das correções é negativo | média | resultado negativo é resultado, e está declarado como tal desde o projeto |
