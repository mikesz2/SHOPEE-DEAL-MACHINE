# Shopee Deal Machine V7.1

Plataforma de automação para **descoberta, curadoria e distribuição de ofertas da Shopee**, com painel web, radar de fontes no Telegram e publicação multicanal em **Telegram e WhatsApp**.

> Projeto prático de automação e integração de APIs. O foco do repositório é demonstrar arquitetura, confiabilidade operacional, integração multicanal, testes e deploy.

## Principais recursos

- Integração com **Shopee Affiliate Open API** para consulta e geração de links.
- Radar de canais e grupos do **Telegram** via Telethon.
- Coleta persistente com deduplicação, fila e recuperação por cursor.
- **Deal Score** e filtros de qualidade para priorização de ofertas.
- Histórico de preços com referência baseada em mediana diária.
- Revalidação de dados antes da publicação.
- Publicação em **Telegram e WhatsApp**, juntos ou separadamente.
- Integração WhatsApp via **Evolution API v2**.
- QR Code, seleção de grupos e histórico de envios no painel.
- Proteção contra reenvio automático quando a confirmação de entrega é incerta.
- Painel web responsivo com observabilidade e controles operacionais.
- Execução em **Windows VPS** e arquitetura Docker para Linux.

## Stack

**Backend:** Python, FastAPI, SQLAlchemy, HTTPX  
**Automação:** Telethon, Telegram Bot API, Evolution API v2  
**Dados:** SQLite no modo local; arquitetura preparada para PostgreSQL e Redis  
**Frontend:** HTML, CSS e JavaScript  
**Infra:** Docker, Caddy e scripts PowerShell para Windows

## Arquitetura

```text
                 +--------------------+
                 |    Painel Web      |
                 +---------+----------+
                           |
                           v
                 +--------------------+
                 |   FastAPI / API    |
                 +----+----------+----+
                      |          |
            +---------+          +----------------+
            v                                     v
     +-------------+                       +--------------+
     | Shopee API  |                       | Telegram     |
     +-------------+                       | Reader/Bot   |
                                           +------+-------+
                                                  |
                                                  v
                                           +--------------+
                                           | Fila / Score |
                                           +------+-------+
                                                  |
                                      +-----------+-----------+
                                      v                       v
                               +-------------+          +-------------+
                               |  Telegram   |          |  WhatsApp   |
                               +-------------+          +-------------+
```

## WhatsApp

A integração usa uma instância externa da **Evolution API v2**. O servidor Evolution não faz parte deste repositório.

```dotenv
EVOLUTION_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=deal-machine
```

As credenciais reais ficam em `.env`, que está ignorado pelo Git. O repositório contém somente exemplos sem segredos.

## Execução local

### Windows

Use a Central Windows incluída no projeto:

```text
ABRIR_CENTRAL_WINDOWS.cmd
```

### Python

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

Depois acesse `http://127.0.0.1:8787`.

## Testes

```bash
python -m pytest -q
```

A suíte cobre contratos do painel, integrações multicanal, coleta, idempotência, recuperação, filas e regras de publicação.

## Deploy

- `DEPLOY_VPS.md` — visão geral de implantação.
- `deploy/enterprise/` — Docker Compose, PostgreSQL, Redis e Caddy.
- `COMECE-AQUI-V7.md` — configuração da V7 e integração WhatsApp.
- `VALIDATION_V7.md` — validação e limites conhecidos.

## Segurança

- `.env`, sessões Telegram, bancos locais e backups não são versionados.
- Credenciais devem ser configuradas apenas no ambiente de execução.
- O painel possui autenticação e proteções operacionais.
- Antes de publicar, valide permissões e regras dos grupos/canais utilizados.

## Screenshots

Os screenshots do README serão adicionados a partir do **projeto real em execução**, sem mockups ou imagens geradas.

## Status

**Versão:** 7.1  
**Integrações:** Shopee, Telegram e WhatsApp  
**Objetivo:** automação de ofertas com curadoria, segurança operacional e distribuição multicanal.
