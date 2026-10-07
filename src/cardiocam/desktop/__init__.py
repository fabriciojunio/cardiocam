"""Aplicativo de desktop: mede durante a reunião, com sobreposição na tela.

Existe porque a versão do navegador não consegue três coisas que este uso pede:
ficar medindo com a aba em segundo plano, que o navegador congela; ler a janela
de uma reunião sem o seletor de compartilhamento aparecer toda vez; e ajustar a
exposição da câmera pelo driver, que é controle bem mais fino que o pouco que
`applyConstraints` expõe.

Três módulos, e a divisão é por natureza da falha, não por camada:

- `janelas`: a API do Windows, onde um retângulo errado vira captura torta em
  silêncio;
- `medicao`: o laço, que roda fora da linha da interface porque a detecção custa
  dezenas de milissegundos por quadro;
- `sobreposicao` e `aplicativo`: o que a pessoa vê.

O processamento de sinal não mora aqui. É o mesmo de `cardiocam.pipeline`, que a
suíte já cobre.
"""
