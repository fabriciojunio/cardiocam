# Quadros de referência do detector

Arquivos `.cinza`: um byte por pixel, sem cabeçalho, nas dimensões que
`indice.json` declara. São gerados, não fotografados.

## Por que crus e não PNG

Node não decodifica PNG sem dependência, e acrescentar uma só para teste traria
peso e uma superfície de falha a mais. Pixel cru também deixa explícito que o
que está sob teste é **o detector**, e não o decodificador de imagem.

O custo é tamanho: 75 KB por quadro contra uns 15 KB em PNG. Para cinco quadros
é troca que vale, e mantém o trabalho de teste do navegador dependendo só de
Node.

## Por que gerados e não fotos

O detector foi depurado contra uma captura real, e é dela que vem a conclusão
sobre o método: a localização por cor punha a caixa na parede bege do quarto, e
a cascata acha o rosto a quatro pixels de onde o OpenCV acha.

Mas o repositório é público, e comitar o rosto de alguém nele seria fazer
exatamente o que a seção de privacidade do projeto diz para não fazer. O rosto
sintético do próprio projeto tem estrutura suficiente para a cascata detectar,
que é o que o teste precisa, e não é o rosto de ninguém.

## O que cada quadro cobre

| quadro | o que exercita |
| --- | --- |
| `rosto-claro` | caso base, tom claro, bem iluminado |
| `rosto-medio` | tom médio |
| `rosto-escuro` | tom escuro; **nem o OpenCV detecta**, e o teste cobra que a nossa saída concorde com a dele |
| `rosto-pouca-luz` | iluminação a 28%; idem |
| `rosto-deslocado` | rosto fora do centro, para o teste não premiar um detector que só olha o meio |

Os dois casos em que ninguém detecta são tão úteis quanto os outros três: eles
cobram **equivalência**, e não acerto. Um detector que achasse rosto ali estaria
divergindo do OpenCV para mais, que é tão errado quanto divergir para menos.

## Como regerar

```bash
python web/ferramentas/exportar_quadro.py
```

Precisa do ambiente Python do projeto, porque usa o renderizador de rosto e o
OpenCV para gerar a caixa de referência. O trabalho de teste do navegador na
integração contínua não regera nada: ele lê o que está versionado.
