# Arquitetura V5

## Windows single-node
Central Windows -> Supervisor -> Web + Worker + Reader -> SQLite WAL.

É o modo de menor atrito e o recomendado para quem quer operar por RDP. O supervisor reinicia processos, há heartbeat, lock local, backup e circuit breaker.

## Enterprise distributed-ready
Caddy -> Web -> PostgreSQL/Redis <- Worker / Reader.

- PostgreSQL: estado persistente e concorrência.
- Redis: locks e heartbeat distribuídos.
- Web: API/painel sem trabalho pesado de background.
- Worker: radar, conversões e publicação.
- Reader: conta Telegram leitora/MTProto.
- Backup: pg_dump periódico em volume separado.

A aplicação mantém os processos desacoplados para que Worker/Reader possam ser replicados ou movidos de máquina no futuro.
