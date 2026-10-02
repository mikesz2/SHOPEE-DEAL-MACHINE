# Deal Machine V7 — WhatsApp + radar de ofertas

Esta atualização parte do pacote Command Center V6 recuperado do último trabalho.
Inclui o código completo. Não instala nada na sua VPS e não conecta contas automaticamente.

## O que mudou

- Aba WhatsApp: estado da conexão, QR Code da instância, seleção de até 30 grupos e histórico de envios.
- Telegram e WhatsApp podem publicar juntos ou separadamente. Cada destino tem link afiliado com tracking próprio.
- Falha antes do envio: tentativa posterior com espera. Envio sem confirmação: conferência manual; não há reenvio automático cego.
- Repetição em um mesmo grupo não multiplica o sinal de tendência.
- Uma oferta ativa por produto. Outras aparições são registradas sem criar várias publicações concorrentes.
- Referência de preço pela mediana diária observada em até 30 dias, com pelo menos 3 dias de dados. Dias com muitas coletas não pesam mais.
- Preço “de” não é mais inventado a partir do desconto anunciado. Frete, variantes e cupons não são considerados verificados.
- Avaliações, vendas e comissão são exigidas por padrão; o painel permite mudar a regra.
- Radar Shopee percorre até 5 páginas por palavra, com limite configurável.
- Dados e score são revalidados antes de publicar; ofertas antigas expiram da fila.
- Telegram: fila persistente de links, deduplicação, tentativas com espera e recuperação por cursor a cada minuto.
- A coleta preserva o horário original da mensagem; importações antigas não parecem novidades recém-publicadas.
- Links ocultos em entidades, botões e prévias continuam sendo lidos.
- Novas tabelas são criadas na inicialização sem remover as tabelas antigas.
- Corrigida a rede Docker: worker e reader precisam de saída para acessar Shopee e Telegram.

## Configurar WhatsApp

A implementação é um cliente da **Evolution API v2**, que precisa estar instalada à parte ou disponível em um serviço contratado. O pacote não contém o servidor Evolution. Crie uma instância com integração WhatsApp/Baileys no gerenciador Evolution.

Preencha no arquivo de ambiente usado pelo robô:

```dotenv
EVOLUTION_URL=https://seu-servidor-evolution
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=deal-machine
```

Use o nome exato da instância criada. A URL é a base da API, sem `/manager`.
Não publique a chave em grupos nem inclua o arquivo `.env` em backups compartilhados.
Em Docker, `localhost` aponta para o próprio container; use um endereço alcançável pelo web e pelo worker.

Reinicie o web e o worker depois de alterar essas variáveis. No painel:

1. Abra **WhatsApp → Mostrar QR Code** e pareie a conta.
2. Clique **Atualizar conexão** até aparecer **Conectado**.
3. Clique **Carregar grupos da conta**.
4. Selecione apenas os grupos em que você pode divulgar ofertas.
5. Marque **Enviar aos grupos WhatsApp selecionados**, escolha o intervalo e salve.
6. Para testar, deixe o piloto automático pausado, selecione um único grupo e publique uma oferta manualmente.
7. Confira preço, imagem, mensagem e seu link afiliado no grupo antes de ativar a automação.

O QR Code não cria a instância. Se ela não existir, crie primeiro no Evolution.
A integração não é a API oficial Meta: não há garantia contra desconexões ou bloqueios do WhatsApp.
Uma resposta com identificador confirma a aceitação pelo gateway, não a leitura pelos participantes.

## Coleta dos grupos maiores (Telegram)

Cadastre as fontes na aba Radar Telegram e conecte a conta leitora como antes. A conta precisa ter acesso às fontes; a atualização não entra em grupos privados nem procura/invade grupos automaticamente.

Na primeira execução de cada fonte, são examinadas as **200 mensagens mais recentes**, respeitando a idade máxima de oferta. Depois, o cursor avança em ordem, até **200 mensagens por fonte por rodada**, recuperando períodos de desconexão. O leitor em tempo real continua ativo durante essa recuperação. Grupos maiores que essa capacidade podem acumular atraso; isso não é uma promessa de coleta ilimitada.

A captura dos links é separada da consulta à Shopee. Uma API temporariamente indisponível não precisa fazer a mensagem se perder. Consultas que falham têm até 5 tentativas com espera; o painel mostra pendentes, processadas, expiradas e falhas. Histórico manual também entra na fila e passa pelas mesmas regras.

O novo monitor de coleta fica na aba WhatsApp. A coleta de grupos **WhatsApp como fontes** não foi implementada nesta versão; WhatsApp é destino de publicação, e Telegram continua sendo a fonte dos grupos monitorados.

## Atualizar no Ubuntu

Mantenha um backup do banco e pause a publicação antes da atualização. Preserve seu `.env`, sessões Telegram, dados e volumes Docker. Não copie arquivos vazios por cima das suas configurações.

Se você usa o deploy Enterprise, substitua apenas o código do projeto e o Compose, acrescente as três variáveis Evolution ao seu `deploy/enterprise/.env` e execute, na raiz:

```bash
docker compose --project-directory deploy/enterprise --env-file deploy/enterprise/.env -f deploy/enterprise/docker-compose.yml up -d --build
```

Esse comando atualiza uma instalação Docker já configurada. Não é um instalador completo de Ubuntu/Docker/Evolution. A instalação Ubuntu “do zero em um comando” pedida no chat anterior ainda não fazia parte do pacote V6 encontrado e não está sendo apresentada aqui como concluída.

Na instalação Windows, mantenha os mesmos lançadores e acrescente as variáveis no `.env` utilizado por eles. Os serviços precisam ser reiniciados para carregar as variáveis novas.

## Como tratar envio sem confirmação

Na aba WhatsApp, o histórico inclui os dois canais. Confira o destino antes de escolher **Recebido no grupo** ou **Não recebido**. A segunda opção permite nova tentativa conforme as regras de automação. Envios ainda em andamento não podem ser reconciliados. O sistema usa uma janela conservadora de 125 minutos para recuperar operações interrompidas, pois uma rodada pode envolver vários destinos.

## Validação e limites

Leia `VALIDATION_V7.md`. As integrações novas foram testadas com respostas simuladas, sem credenciais e sem disparos reais. Uma conta Evolution conectada, credenciais Shopee válidas e a configuração da VPS ainda precisam ser validadas no seu ambiente.
