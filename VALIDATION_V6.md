# Validação V6 — 28/09/2026

- 25 testes Python aprovados: 22 herdados da V5 e 3 testes dos contratos usados pelo novo painel.
- Testes novos: fila e indicadores sem dados; pausa/ativação preservando políticas e auditoria; período de conversões e bloqueio sem autenticação.
- JavaScript verificado com `node --check` nos dois arquivos.
- Chromium: navegação nas seis telas em 1440px e 390px, sem overflow horizontal da página e sem erros JavaScript.
- Fluxos no navegador: prévia de oferta, Ctrl+K e Enter, salvar políticas, pausar e retomar, filtros, seleção em lote, download CSV, período de conversões, falha de rede e recuperação, estado vazio.
- Inspeção visual do dashboard e login. Fonte Inter servida localmente com licença incluída.

## Limites

Testes em ambiente Linux isolado, com dados fictícios apenas no banco de QA, não incluído no pacote. Nenhuma mensagem enviada ao Telegram. Credenciais e acesso à VPS não disponíveis nesta execução; integrações reais e inicialização PowerShell/Windows precisam ser verificadas na instalação. Backend de publicação, Shopee e leitura Telegram preservados da V5.

A prévia PNG é identificada como demonstração. Comissões nela são fictícias. O painel instalado consulta exclusivamente as APIs autenticadas do projeto.

A suíte existente apresenta avisos de depreciação de bibliotecas e de datetime.utcnow; eles não impediram os testes.
