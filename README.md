# Shopee Deal Machine V7.1

Plataforma de automação para **descoberta, curadoria e distribuição de ofertas da Shopee**, com painel web, radar de fontes no Telegram e publicação multicanal em **Telegram + WhatsApp**.

## Destaques

- Integração com Shopee Affiliate Open API.
- Radar de grupos/canais do Telegram via Telethon.
- Coleta persistente, deduplicação e recuperação por cursor.
- Deal Score e filtros de qualidade.
- Histórico de preços com referência por mediana diária.
- Revalidação da oferta antes da publicação.
- Links de afiliado com tracking por destino.
- Publicação em Telegram e WhatsApp, juntos ou separadamente.
- Integração WhatsApp via Evolution API v2.
- QR Code, seleção de grupos e histórico de envios no painel.
- Painel Command Center V7.1 responsivo.
- Deploy Windows e Docker/Linux.
- SQLite no modo local e arquitetura preparada para PostgreSQL/Redis.

## Stack

Python · FastAPI · SQLAlchemy · Telethon · HTTPX · Shopee Affiliate API · Telegram Bot API · Evolution API · Docker · Redis · PostgreSQL · JavaScript · HTML/CSS

## Segurança

Credenciais reais **não fazem parte deste repositório**.

- `.env` não é versionado.
- Bancos SQLite/PostgreSQL exportados não são versionados.
- Sessões do Telegram não são versionadas.
- Logs, backups e dados de runtime não são versionados.
- O projeto inclui apenas `.env.example` com placeholders.

## WhatsApp

A integração usa uma instância externa da **Evolution API v2**. O servidor Evolution não faz parte deste repositório.

```dotenv
EVOLUTION_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=deal-machine
```

## Objetivo de portfólio

Este projeto demonstra experiência prática com automação, APIs, filas, scraping/ingestão controlada de fontes autorizadas, integração de mensageria, troubleshooting, deploy e evolução de produto.
