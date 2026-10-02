# Shopee Deal Machine Enterprise V5 — Deploy

## Qual modo usar

### Windows VPS (mais simples / interface visual)
Use quando você quer operar tudo por RDP, com Central Windows, SQLite WAL, backups e supervisor locais. É excelente para uma operação pequena/média em uma única VPS.

Recomendação prática: **2 vCPU, 4 GB RAM e 40 GB SSD/NVMe**. Para uma operação com importações grandes de histórico e muitos canais, prefira **4 vCPU / 8 GB RAM**.

Passos: extraia a pasta em `C:\ShopeeDealMachine`, abra `ABRIR_CENTRAL_WINDOWS.cmd`, clique em **Instalar / Atualizar**, preencha Configurações, conecte a conta leitora e ative **Iniciar com Windows**.

### Enterprise Linux/Docker (recomendado para negócio crítico)
Para maior escala use `deploy/enterprise`: Web, Worker e Reader separados, PostgreSQL, Redis e Caddy/HTTPS. Isso permite reinício independente, locks distribuídos e banco preparado para crescer.

1. Copie `deploy/enterprise/.env.example` para `deploy/enterprise/.env` e preencha os segredos.
2. Aponte o DNS do `DOMAIN` para a VPS.
3. A partir de `deploy/enterprise`, suba o Compose.
4. Faça o primeiro login da conta leitora numa sessão interativa do container `reader` antes de deixá-lo 24/7.

Nunca exponha PostgreSQL ou Redis diretamente à internet.

## Checklist antes de produção

- Shopee: teste de API OK.
- Bot Telegram: teste de destino OK.
- Reader Telegram: sessão autorizada e fontes testadas.
- Painel: senha forte; em acesso público use HTTPS e `COOKIE_SECURE=true`.
- Publicação automática: primeiro valide 5–10 posts manualmente.
- Backup: confirme que um backup pode ser restaurado.
- Alertas: configure `TELEGRAM_ADMIN_CHAT`.
- Fila: ajuste `max_queue_depth` e `alert_queue_depth` para o volume real.
- Circuit breaker: mantenha habilitado via limites de falha na Automação.

## Escala

Uma única VPS Windows não é arquitetura de “empresa gigante”. A V5 mantém esse modo por simplicidade, mas o caminho de crescimento é o modo Docker + PostgreSQL + Redis. Em seguida é possível mover Web, Worker e Reader para máquinas separadas sem reescrever a aplicação.
