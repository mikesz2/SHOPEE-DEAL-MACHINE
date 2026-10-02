# Validação V7

- Suíte Python: 40 testes aprovados (25 anteriores + 15 novos).
- Sintaxe dos módulos Python validada por compileall.
- Sintaxe de app.js e command-center.js validada por node --check.
- API local inicializou com banco SQLite vazio e criação das novas tabelas.
- Testes novos cobrem: padrões pausados, fontes distintas, histórico mínimo de preço,
  ingestão idempotente, uma oferta ativa por produto, fila persistente, repetição de links,
  fonte pausada, retry de coleta, envio parcial e retomada sem repetir destino,
  envio ambíguo bloqueado, payload WhatsApp com mídia, IDs de grupo, ausência de
  fallback após timeout, preço anterior não inventado, recuperação por cursor,
  autenticação das rotas e preservação dos destinos ao salvar políticas.
- Chamadas externas nos testes são simuladas. Nenhum envio real foi feito.
- Renderização visual no navegador não validada: o Chromium não estava disponível
  e seu download falhou no ambiente. Não se afirma aprovação visual desktop/mobile.
- Não houve build Docker, instalação Ubuntu, deploy na VPS, pareamento WhatsApp
  ou validação real com Shopee/Telegram/Evolution.
- Evolução testada sobre o esquema da V6 por adição de tabelas; backup antes da atualização
  continua necessário. Não há migração destrutiva de dados antigos.
- O pacote mantém dependências Python em faixas como na V6; não é um build reprodutível travado.
