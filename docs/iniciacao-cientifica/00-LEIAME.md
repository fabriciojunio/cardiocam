# Documentação de iniciação científica

Pasta montada em 04/10/2026 para a conversa com o professor da UNESP indicado
pela Profa. Cidinha (FOB-USP).

**Leia nesta ordem.** Os dois primeiros documentos decidem se o caminho existe;
os demais são o material que você entrega.

| # | Documento | Para que serve | Vai na submissão |
| --- | --- | --- | :-: |
| 01 | [Bolsa e vínculo](01-bolsa-e-vinculo.md) | **Leia primeiro.** A regra da bolsa contra o seu trabalho como PJ, com a fonte de cada afirmação. Tem uma conclusão que muda o plano | não |
| 02 | [Como funciona a IC na UNESP](02-como-funciona-ic-unesp.md) | Modalidades, quem submete, prazos, o que o certificado exige, e **a lista do que só o orientador pode preencher** | não |
| 03 | [Projeto de pesquisa](03-projeto-de-pesquisa.md) | O documento principal, com todas as seções que o comitê exige | **sim** |
| 04 | [Plano de trabalho e cronograma](04-plano-de-trabalho.md) | As atividades mês a mês, em 12 meses, com os riscos do plano | **sim** |
| 05 | [Resultados preliminares](05-resultados-preliminares.md) | O que já está medido e rodando, inclusive os dois defeitos achados e corrigidos | **sim** |
| 06 | [Ética e Plataforma Brasil](06-etica-plataforma-brasil.md) | O caminho obrigatório do comitê, a lista de anexos e as pendências que ele costuma pedir | não |
| 07 | [Termo de consentimento](07-tcle.md) | TCLE completo, no formato da Resolução 466/12 | **sim** |
| 08 | [Termos complementares](08-termos-complementares.md) | Uso de imagem, ficha de sessão, compromisso, confidencialidade e declaração da unidade | **sim** |
| 09 | [Referências](09-referencias.md) | A bibliografia, com o número que cada trabalho reporta | **sim** |
| 10 | [Roteiro da conversa](10-roteiro-da-conversa.md) | O que dizer, o que perguntar e o que não prometer | não |

Para conferir a formatação de todos de uma vez:

```bash
python docs/iniciacao-cientifica/validar_documentos.py
```

Ele checa travessão, espaçamento, acentuação por lista fechada, link interno
quebrado, codificação, consistência de coluna em tabela e chave de preenchimento
sem fechar. O que ele **não** checa é concordância e sentido, e para isso não
existe atalho.

## Resumo de uma página

**O que é o projeto.** Medir frequência cardíaca por câmera comum, sem contato,
usando a variação de cor da pele causada pelo pulso. A técnica tem nome na
literatura: fotopletismografia remota, ou rPPG.

**O que já existe.** Um sistema completo e funcionando, com quatro algoritmos
clássicos implementados do zero, 2.005 testes automatizados e validação contra
sinal de frequência conhecida. Não é protótipo de slide.

**O que a IC acrescenta.** O que o sistema ainda não tem é exatamente o que a
literatura aponta como problema aberto: comportamento sob **movimento** e sob
**tom de pele diverso**. Essas duas coisas são a proposta.

**Por que é um bom projeto de IC.** Tem pergunta clara, método mensurável,
dados públicos disponíveis para comparação, e um resultado que vale mesmo se for
negativo. Não depende de equipamento caro: câmera comum e um oxímetro de dedo.

**O que precisa de aprovação.** Coleta com pessoas exige comitê de ética. O
cronograma já reserva os três primeiros meses para isso, e a primeira fase do
projeto usa **somente dados públicos**, então o trabalho começa no mês 1 sem
esperar o parecer.
