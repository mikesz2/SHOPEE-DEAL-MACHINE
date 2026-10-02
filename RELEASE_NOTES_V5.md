# V5.0 Enterprise

- Dashboard redesenhado com navegação lateral e estética empresarial.
- KPIs de operação, timeline, fontes líderes e feed de atividade.
- Filtros e busca de ofertas, paginação e ações em lote.
- Radar Telegram com teste, importação de histórico, ativação/pausa e diagnóstico visual.
- Performance por fonte, template e categoria.
- Trilha de auditoria persistente.
- Rate limit de login e segredo de sessão independente.
- Request ID, headers de segurança e validação de Origin em mutações.
- Backpressure da fila e alertas de fila alta.
- Circuit breaker do publicador após falhas consecutivas.
- Heartbeat do Worker com profundidade de fila, breaker e última publicação.
- Limpeza automática da trilha de auditoria.
- Dockerfile e stack Enterprise com PostgreSQL + Redis + Caddy/HTTPS.
- Mantido o modo Windows visual com SQLite WAL, supervisor e backups locais.
