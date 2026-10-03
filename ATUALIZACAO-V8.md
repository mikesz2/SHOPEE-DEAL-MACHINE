# Deal Machine V8 — Discovery Studio

## Visual

Novo painel editorial: fundo marfim, navegação em verde escuro, ações em laranja, abertura tipográfica e etapas Descoberta → Curadoria → Distribuição. Layout responsivo, navegação por teclado, transições com respeito à preferência por movimento reduzido e acesso direto à busca de produtos.

## Descoberta de produtos

- Amplia os temas padrão com termos de produtos; alterna os termos relacionados por hora UTC.
- Deduplica palavras-chave e consulta primeiro uma página por tema, antes das páginas seguintes.
- Compara a correspondência do título com a busca, avaliação, vendas, desconto e comissão.
- Descarta identidades inválidas, campos numéricos não finitos, resultados pouco relevantes e ofertas fora do período informado pela API.
- Aplica os filtros de qualidade já configurados antes de salvar os candidatos.
- Intercala temas e limita produtos da mesma loja para diversificar a seleção.
- Mantém a comparação com histórico de preço já existente na V7.1 durante a ingestão. Exige pelo menos três dias observados; não inventa descontos históricos.
- Mostra o resultado da busca manual: consultas, candidatos, repetições, filtros e falhas parciais.
- Continua a processar os resultados obtidos quando uma consulta falha.

Em **Automação → Radar**, ajuste exploração de termos relacionados, candidatos por rodada (padrão 40) e produtos por loja (padrão 3). O score de publicação continua sendo controlado pelas políticas existentes; a classificação de descoberta seleciona candidatos, sem garantir vendas ou rentabilidade.

Limites: até 24 palavras-chave únicas, até 36 consultas e aproximadamente 100 segundos de consultas externas por rodada; ingestão pode acrescentar tempo. Temas iniciais são alternados a cada hora UTC. O limite por loja vale para cada rodada. A contagem de filtros é por resultado consultado e pode incluir o mesmo produto em buscas diferentes. A relevância é calculada por palavras e famílias de termos, sem modelo de linguagem. Frete, cupons pessoais e preço de variações não estão incluídos.

## Atualizar uma instalação existente

1. Faça backup do projeto e do banco de dados.
2. Pare os serviços Web, Worker e Reader.
3. Extraia o pacote em uma pasta temporária. Copie o conteúdo de `app/` para o `app/` da instalação, incluindo os arquivos novos. As dependências de produção não mudaram.
4. Preserve `.env`, banco de dados, sessões Telegram, backups e configurações de serviços da sua instalação.
5. Reinicie os três serviços pelo mesmo gerenciador já utilizado. Os novos parâmetros recebem valores padrão automaticamente, sem migração de tabelas.
6. Abra o painel e confira Automação → Radar. Use **Descobrir produtos** para testar com suas credenciais.

O pacote não contém `.env`, banco de usuários, credenciais cadastradas, sessões Telegram ou dados reais. Os arquivos `.env.example` são modelos. Não é necessário ativar a publicação automática para testar a descoberta.

## Validação

46 testes automatizados passaram, incluindo os novos testes de relevância, expiração, dados ausentes/inválidos, diversidade, deduplicação, novas ofertas por rodada e falha parcial. JavaScript validado e navegação das sete telas conferida em navegador; menu móvel, campos novos e ausência de rolagem horizontal conferidos em 390 px. Prévia de desktop em 1440 px.

A integração com contas reais da Shopee, Telegram e WhatsApp não foi executada. A instalação em produção não foi alterada. As imagens mostram a aplicação local sem contas conectadas e sem dados de operação.
