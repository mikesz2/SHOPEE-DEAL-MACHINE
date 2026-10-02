# Atualização visual V7.1

- Menu verde-escuro, fundo claro e tipografia com mais contraste.
- Abertura do dashboard redesenhada; comissão destacada e indicadores maiores.
- Cards de produto com imagens maiores, score, desconto e ação de revisão.
- Estilos consistentes para ofertas, radar, automação, performance e WhatsApp.
- Tabelas, formulários, botões, prévia de oferta e estados vazios refinados.
- Transição suave de páginas e entrada dos indicadores. A preferência do sistema
  por movimento reduzido é respeitada.
- Menu móvel com fundo escurecido, fechamento por toque fora ou Escape e atributos
  de acessibilidade. Layouts adaptados para telas pequenas.
- Todos os números continuam vindo da API. Não foram inseridos resultados fictícios.

## Instalação

O arquivo contém o projeto completo. Para atualizar apenas o visual de uma V7 já instalada,
substitua `app/static/index.html`, `app/static/app.js` e acrescente `app/static/refined.css`.
Preserve dados, `.env` e sessões. Em Docker, reconstrua a imagem para incluir os arquivos novos.
O navegador recebe versões novas dos arquivos para evitar cache antigo.

## Validação desta alteração

- Sintaxe JavaScript verificada.
- HTML, CSS e JavaScript retornaram HTTP 200 na aplicação local.
- Não foi possível concluir inspeção visual automatizada: o ambiente bloqueou a abertura
  de sockets pelo navegador. Portanto o layout ainda precisa ser conferido no navegador
  da instalação, especialmente em celular.
- Não houve deploy nem envio real de ofertas. As funções de publicação da V7 foram preservadas.
