# Protocolo de avaliação com referência cardíaca

Versão de 09/10/2026. Este documento define como avaliar o protótipo e registrar
suas limitações. Nenhuma sessão com ECG ou PPG sincronizado foi fornecida para
esta revisão. Os exemplos distribuídos são numéricos e sintéticos.

## Dados necessários

Cada sessão precisa ter vídeo autorizado, referência cardíaca independente,
identificador pseudônimo do participante, câmera, condição, origem dos dados
e licença ou autorização aplicável. O sinal de referência deve ser derivado
de ECG ou PPG de contato por um procedimento descrito no estudo. Um oxímetro
que mostra apenas BPM na tela pode ter atraso e suavização desconhecidos;
comparar esses números sem alinhamento não equivale a referência sincronizada.

Guardar o método de sincronização, os relógios utilizados, a definição de BPM
da referência e sua janela temporal. O pipeline registra o fim da janela do
vídeo; comparar com a referência desse instante é uma aproximação. Quando a
frequência muda, a referência deve representar a mesma janela de observação.
O avaliador atual interpola BPM tabulados e não extrai picos de ECG bruto.

## Formatos e execução

As leituras exportadas por `--salvar` contêm `instante_s`, `bpm` e `aceita`,
além de qualidade, causa da recusa, idade, características ausentes e diagnóstico.
Linhas recusadas continuam no CSV; um BPM bruto nelas não é uma leitura aceita.
A luminância está na escala dos quadros de 8 bits, não em lux. Os percentis
com sufixo `_quadro` descrevem a região extraída do quadro da emissão. `fps_janela`
e `jitter_intervalos_s` usam os timestamps originais da janela, antes da
reamostragem. Eles não identificam, por si só, bitrate, codec ou exposição.

A referência precisa de duas ou mais linhas com instantes finitos, estritamente
crescentes e BPM positivos:

```csv
instante_s,bpm
0.0,72.0
1.0,72.0
2.0,73.0
```

O [manifesto de exemplo](exemplos/manifesto-sintetico.json) demonstra todos os
campos obrigatórios. Os caminhos dos CSVs são relativos ao manifesto.
`offset_s` é somado ao instante da leitura para chegar ao relógio da referência.
`lacuna_maxima_s` limita a interpolação; o padrão é 2 s. Não há extrapolação
fora da referência nem interpolação em lacunas maiores que o limite.

```bash
cardiocam arquivo sessao.mp4 --janela 25 --salvar leituras.csv
python -m cardiocam.avaliacao.referencia manifesto.json --saida resultados.json
```

Para conferir a infraestrutura sem pessoas, execute:

```bash
python -m cardiocam.avaliacao.referencia docs/exemplos/manifesto-sintetico.json --saida resultado-sintetico.json
```

O resultado esperado desse exemplo é MAE e RMSE de 2 bpm, viés de zero,
duas leituras aceitas com referência e cobertura de 2/3 dos três registros.
Esse resultado testa o cálculo, não a precisão de uma câmera.

## Métricas e denominadores

O avaliador gera métricas por sessão: MAE, RMSE, viés, limites descritivos de
concordância de 1,96 desvios, proporção de leituras aceitas dentro de ±5 bpm e
proporção das aceitas com erro acima de 5 bpm. O corte de 5 bpm é uma métrica
experimental explícita, não um critério de aprovação clínica.

`aceitas` conta leituras publicadas que também têm referência válida.
`cobertura_registros` divide esse número por todos os registros exportados,
incluindo recusas e registros fora da referência. Registros de erro podem ser
agrupados para não repetir uma mensagem a cada quadro. Portanto, essa cobertura
não é fração do tempo total de vídeo. Para medir cobertura temporal, é necessário
registrar também a duração de cada estado e definir a cadência de avaliação.

Os limites calculados não corrigem a dependência entre janelas sobrepostas.
Não são intervalos de confiança nem evidência de equivalência clínica. O
relatório preserva participantes e sessões sem contar cada janela como uma
pessoa independente. Uma análise estatística final deve agregar por participante
ou usar métodos apropriados para medidas repetidas.

## Desenho da comparação

Antes dos experimentos, fixar participantes de treino, calibração e teste.
Nenhuma sessão da mesma pessoa pode aparecer em partições diferentes. Manter
também um dataset independente para avaliar transferência. Registrar versões,
configuração, sementes, exclusões e motivos de falha; não escolher o limiar
usando o conjunto final de teste.

Comparar a versão anterior e cada alteração isolada nos mesmos vídeos:
iluminação adequada, pouca luz, contraluz, LED, fala, movimento, óculos,
congelamento e perda de quadros. Registrar câmera, resolução, FPS entregue,
codec e bitrate quando conhecidos. Avaliar tom de pele somente quando a
classificação e o uso desses dados estiverem previstos no protocolo.

Incluir todas as falhas no denominador declarado. Relatar erro junto com
cobertura, falsa aceitação, tempo até a primeira leitura, atraso em mudanças
de frequência e custo computacional. Para aprimoramento de imagem, incluir
vídeos sem pulso e movimentos periódicos: um pico artificial não pode contar
como recuperação. O ganho deve permanecer em participantes não vistos.

## Calibração e uso com pessoas

O modelo distribuído foi treinado em 349 janelas sintéticas. As correções de
tempo, pele e contexto alteram suas entradas; o número apresentado como
qualidade ainda não tem calibração demonstrada em vídeo real. O treino real
precisa incluir compressão, movimento e falhas de câmera, com validação de
calibração e curva de erro contra cobertura em participantes separados.

Os documentos de [ética](iniciacao-cientifica/06-etica-plataforma-brasil.md) e
[consentimento](iniciacao-cientifica/07-tcle.md) são propostas para revisão
institucional. Definir acesso, prazo de retenção, descarte, uso das gravações e
responsabilidades antes da coleta. O protótipo atual processa localmente e não
grava quadros; arquivos de resultados ainda podem conter dados fisiológicos.
Este protocolo não representa aprovação ética, regulatória ou clínica.

## Dependências de pesquisa

LGI e OMIT têm implementações experimentais independentes; PBV adaptativo usa
uma assinatura estimada da própria série, diferente de PBV com assinatura
calibrada por câmera e iluminação. Os métodos não foram promovidos para a
captura padrão com base apenas em testes sintéticos.

SSR exige estatísticas espaciais dos pixels, ausentes na média RGB atual.
Landmarks, fluxo óptico, seleção de pequenas regiões e fusão precisam de testes
de ablação. Skin-AE depende de controle de exposição que a câmera realmente
aceite. Retinexformer, Zero-DCE, modelos neurais, pupilometria e video-BCG
exigem dados, licenças, referências e custo de execução compatíveis com o
experimento. A [revisão de fontes](fontes-de-pesquisa.md) registra essas restrições.
