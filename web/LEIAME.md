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

## Testes

```bash
cd web
npm test
```

276 casos, sem navegador e sem dependências. Verificam a FFT, o filtro, a
estimativa de frequência varrendo de 46 a 196 bpm, os três algoritmos sobre
séries RGB modeladas fisicamente, a segmentação de pele em sete tons e o
pipeline completo com um canvas falso que devolve pixels de pele modulados por
um pulso de frequência conhecida.

O porte reproduz o mesmo resultado da versão em Python no cenário decisivo: sob
interferência de iluminação dentro da banda cardíaca, CHROM e POS acertam e o
método do canal verde trava na interferência.

## Publicar

```bash
cd web
vercel deploy --prod
```

Não há etapa de compilação. São arquivos estáticos e módulos ES nativos.
