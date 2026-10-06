# Interface web do Cardiocam

Mesma medição da versão em Python, rodando inteiramente dentro do navegador.
Funciona em computador e em celular, sem instalar nada.

## Por que tudo roda no cliente

Não existe servidor neste projeto, e isso é decisão de projeto e não limitação.
Frequência cardíaca é dado pessoal sensível pela LGPD. A forma mais simples de
tratar dado sensível com responsabilidade é nunca centralizá-lo: se o vídeo não
sai do aparelho, não há vazamento possível, não há retenção a gerenciar e não há
pedido de exclusão a atender.

O cabeçalho `Content-Security-Policy` em `vercel.json` fecha isso no nível do
navegador com `connect-src 'none'`: mesmo que algum código tentasse enviar dados
para fora, o navegador recusaria a conexão. As medições salvas ficam no
`localStorage` do próprio aparelho.

## Diferenças em relação à versão em Python

| | Python | Navegador |
| --- | --- | --- |
| Detecção de rosto | cascata de Haar (Viola-Jones) | contorno na tela, posicionado pela pessoa |
| Filtro passa-faixa | Butterworth de ordem 4 nos dois sentidos | mascaramento no domínio da frequência |
| Algoritmos | GREEN, CHROM, POS, ICA | GREEN, CHROM, POS |
| Armazenamento | CSV opcional | localStorage e exportação CSV |

A cascata de Haar não existe no navegador e um modelo de rede neural custaria
alguns megabytes de download. Pedir que a pessoa encaixe o rosto no contorno
resolve isso e ainda traz um ganho colateral: com o rosto ancorado num lugar
fixo, a região medida para de tremer entre quadros, e esse tremor é o que mais
estraga a medição na versão automática.

O ICA ficou de fora porque exigiria portar o FastICA, e ele é justamente o
algoritmo que teve o pior desempenho no comparativo.

## A cadência de quadros, e as três falhas que ela cobre

`js/cadencia.js` é a camada que decide **quando** um quadro é lido. Ela ficou
separada do resto porque foi onde apareceram as falhas mais caras do porte, e
porque dentro de `app.js` não havia como testá-la: dependia de elemento de
vídeo, de `requestVideoFrameCallback` e do relógio do navegador. Agora os três
entram por parâmetro.

**Quadro repetido.** O laço original usava `requestAnimationFrame`, que dispara
na taxa do monitor e não na da câmera. Com tela de 60 Hz e câmera a 20, o mesmo
quadro entrava três vezes na série, com três carimbos de tempo diferentes.
Cópia carrega o mesmo ruído do sensor, então a promediação deixa de reduzir
ruído na proporção que o código supõe; e como a razão entre as duas taxas varia
ao longo do tempo, a duplicação injeta uma modulação lenta perto da banda
cardíaca. Era o que fazia a leitura ser descartada "independente da luz".

**Base de tempo misturada.** A correção acima trouxe um defeito próprio:
`performance.now()` conta desde o carregamento da página e chega às dezenas de
segundos, enquanto `mediaTime` começa do zero. Com os dois na mesma série, a
duração acumulada ficava negativa e a barra de progresso nunca completava. Vale
uma base só, e ela é a da mídia.

**Cadeia morta em silêncio.** `requestVideoFrameCallback` só dispara quando
chega quadro novo, então, se a câmera para, o único evento capaz de religar o
agendamento é justamente o que deixou de acontecer. A câmera "desligava
sozinha". O vigia roda em `requestAnimationFrame`, que não depende da câmera,
percebe o silêncio e reata; depois de três resgates seguidos ele desiste do
callback de vídeo e passa a puxar quadro na taxa do monitor, rejeitando
repetido pelo tempo de mídia.

Vale registrar o modo como a terceira falha sobreviveu a uma correção: o vigia
tinha sido escrito, comentado e publicado, e era armado **só dentro do ramo de
reserva**, que nenhum navegador atual usa. Defesa escrita e não instalada passa
em revisão de código e falha na mão de quem mede. O teste `o vigia é armado
também no caminho do callback` existe para isso, e foi conferido por mutação:
reintroduzindo a condição antiga, a suíte falha.

Fora da cadência, `app.js` escuta `mute`, `unmute` e `ended` na trilha de
vídeo. São os eventos que dizem **por que** parou de chegar quadro, e sem eles
a página ficava dizendo "Medindo" sobre uma imagem congelada.

## Exposição contra taxa de quadros

`js/exposicao.js` resolve a disputa que fazia a câmera desligar e ligar sozinha.
A história completa está em [docs/adr/0006](../docs/adr/0006-exposicao-contra-taxa-de-quadros.md);
o resumo é que a webcam abre com a exposição no máximo, não consegue entregar um
quadro antes de terminar de expô-lo, e por isso entrega oito quadros por segundo
**em qualquer resolução**. O aplicativo lia a taxa baixa, concluía que a culpa
era da resolução, e reabria a câmera para baixá-la. Duas vezes por sessão, sem
nunca acertar a causa.

A medição que fechou o diagnóstico, numa EMEET SmartCam S600:

| exposição | taxa entregue |
| ---: | ---: |
| 5000, o máximo e o padrão dela | 8,0 |
| 1250 | 8,0 |
| 625 | 15,9 |
| 312 | 30,0 |

E 8,0 igual em 1920x1080 e em 320x240, o que descarta banda e processamento.

Agora a taxa mínima define um **teto** de exposição, pela conta `10000 / taxa`
em unidades de 100 µs, e a procura por luz acontece debaixo dele. A resolução,
quando precisa mudar, muda na trilha viva com `applyConstraints`: o dispositivo
não cai, a luz da webcam não pisca, e só a janela de coleta recomeça.

Reproduza com `npm run test:navegador:lenta`, que prende a câmera na exposição
máxima antes de abrir a página e cobra que ela saia de lá sem reabrir nada.

## Quando algo não funcionar

O botão **Copiar diagnóstico** na página põe na área de transferência a linha do
tempo da captura: cada abertura de câmera, cada ajuste de exposição, cada
silêncio, cada mudança de resolução, com o instante de cada um, e uma pulsação
de dois em dois segundos com a contagem de quadros, a taxa medida e o estado da
trilha. Nada sai do aparelho sozinho; quem copia é quem está usando.

Isso existe porque três correções seguidas foram publicadas em cima do relato
"a câmera desliga e liga", e desse relato cabiam quatro explicações com
providências diferentes. Nenhuma delas se distinguia das outras olhando a tela.

Quando a captura precisa ser resgatada, a janela de coleta recomeça. Meio
segundo sem quadro são dez amostras faltando a 20 por segundo, e a análise
espectral trata a série como amostrada uniformemente: com um buraco no meio, o
progresso chega a 100% sem que as amostras existam e a frequência sai de uma
base de tempo que não corresponde ao que foi coletado.

## Testes

```bash
cd web
npm test
```

502 casos, sem navegador e sem dependências. Verificam a FFT, o filtro, a
estimativa de frequência varrendo de 46 a 196 bpm, os três algoritmos sobre
séries RGB modeladas fisicamente, a segmentação de pele em sete tons, o
pipeline completo com um canvas falso que devolve pixels de pele modulados por
um pulso de frequência conhecida, a cascata de Haar contra o OpenCV, a
cadência de quadros com relógio e filas de agendamento sob controle, e o ajuste
de exposição contra uma câmera de mentira que arredonda os pedidos para cima
como a de verdade faz.

### Com navegador

```bash
npm run test:navegador         # câmera falsa, com pulso de 75 bpm gravado
npm run test:navegador:real    # a câmera do computador
npm run test:navegador:lenta   # a câmera presa na exposição máxima
```

Abrem um Chromium pelo protocolo de depuração, servem a página de `127.0.0.1`,
apertam o botão e leem o que acontece. O primeiro usa um y4m gerado por
`ferramentas/gerar_y4m.py` com o mesmo simulador da suíte em Python, então a
frequência que a página tem de encontrar é conhecida: ela mede 79 para um vídeo
de 75, com 21,7 dB de relação sinal-ruído sobre catorze janelas.

Estes três não entram no `npm test`, porque dependem de navegador instalado e de
câmera. São eles que acharam o defeito que três correções sem navegador não
acharam.

Para investigar uma câmera nova:

```bash
npm run medir:taxas       # taxa entregue em cada resolução
npm run medir:exposicao   # taxa entregue em cada tempo de exposição
npm run medir:troca       # trocar de resolução derruba o dispositivo?
```

O terceiro cobre a outra metade da correção. Medido na EMEET: de 1920x1080 para
1280x720 em 561 ms, trilha continuando `live`, nenhum evento `mute` ou `ended`,
mesmo `deviceId`, e 33 quadros em dois segundos antes e depois. É isso que
`applyConstraints` compra em relação a fechar e reabrir, que apaga e acende a
luz da webcam e zera a janela de coleta.

O porte reproduz o mesmo resultado da versão em Python no cenário decisivo: sob
interferência de iluminação dentro da banda cardíaca, CHROM e POS acertam e o
método do canal verde trava na interferência.

## Publicar

```bash
cd web
vercel deploy --prod
```

Não há etapa de compilação. São arquivos estáticos e módulos ES nativos.

## Sobre a política de segurança

`connect-src` era `'none'`, que era a garantia mais forte do projeto: nada
podia sair daqui, nem por engano. Passou para `'self'` quando o detector de
rosto em cascata entrou, porque ele busca o modelo de 148 KB do próprio site.

A diferença é menor do que parece, e vale registrar: `'self'` permite
requisição para esta origem e para nenhuma outra. Terceiro continua bloqueado, e
é por isso que o modelo é hospedado aqui em vez de vir de uma rede de
distribuição. O vídeo continua sem ter para onde ir.

A alternativa seria embutir o modelo no JavaScript, dispensando a requisição.
Foi descartada porque faria o arquivo do aplicativo crescer 148 KB para todo
mundo, inclusive quem só vai usar o modo dedo, e porque modelo versionado à
parte é mais fácil de trocar.

## Em aberto: o Meet entrega imagem mais clara que nós

Observado em 05/10/2026, com a mesma câmera e a mesma sala: a imagem no Google
Meet fica visivelmente mais clara que a nossa, e a nossa relata 47 de 255 de
luminância na pele.

Isso é evidência de que **a câmera consegue entregar mais luz do que estamos
obtendo**, e que o gargalo é a nossa aquisição e não o ambiente. A hipótese
principal é o travamento da exposição: travamos para a exposição automática não
brigar com a medição, e o Meet não trava, ficando com uma imagem melhor.

A tensão é real e está documentada na literatura dos dois lados. A deriva da
exposição automática é apontada como o maior problema de qualidade de sinal em
condição interna típica; e maior tempo de exposição é apontado como o que mais
melhora a correlação com o fotopletismógrafo de contato em pouca luz. Travar
escuro perde das duas formas.

O que falta medir, e que decide a questão: comparar a relação sinal-ruído final
**com exposição travada** e **com exposição automática**, na mesma sala, com o
mesmo participante. Se o automático ganhar, a rectificação por fundo já cobre a
deriva e o travamento deixa de se justificar.

Enquanto isso não é medido, o travamento continua, porque é o que a literatura
recomenda e o que a medição anterior deste projeto sustentou: a correção por
fundo levou os acertos de 1 em 16 para 16 em 16 sob balanço de branco oscilando.
