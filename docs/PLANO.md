# Plano — para onde este projeto vai

> Anotado em 07/09/2026. Nada aqui está decidido. É a lista do que eu quero fazer
> quando voltar a sentar neste projeto.
>
> ⚠️ **Este repositório é público.** Nenhum saldo, extrato, relatório, id de conta ou
> cache do Pluggy pode ser commitado aqui. Nem como artifact do Actions, que é
> baixável em repo público. Os números da análise ficam no vault cifrado.

## Onde o projeto está hoje

- **O sync está parado desde 30/01/2026.** O workflow está `disabled_inactivity`: o
  GitHub desliga cron agendado depois de 60 dias sem commit no repositório. O YNAB
  recebeu 984 transações até 30/01 e nada depois.
- **O YNAB foi cancelado.** Eu parei de pagar e migrei para o app do Breno. O destino
  atual do código não existe mais.
- **A fonte já mudou uma vez.** Era pynubank, virou Pluggy. Vai mudar de novo.
- **O Pluggy entrega muito mais do que o projeto usa.** Hoje o código lê só
  `/transactions` de 3 contas. A conexão dá também investimentos posição a posição,
  faturas de cartão, categoria, método de pagamento e contraparte.

## A direção

Uma fonte, vários destinos, e os dois lados trocáveis.

```
fontes                  núcleo                     destinos
------                  ------                     --------
Pluggy      ─┐                                 ┌─ app do Breno (Supabase)
pynubank     ├─→  Transaction (schemas.py)  ──→├─ YNAB
CSV/OFX      │    + normalização + dedup       ├─ SQLite local (análise)
extrato PJ  ─┘                                 └─ relatório markdown
```

O que isso resolve:

- Trocar de agregador (Pluggy → outro) mexe em um arquivo, não no fluxo.
- Mandar para o app do Breno **e** manter o YNAB é configuração, não fork.
- A **PJ continua fora do Pluggy** (só tenho acesso pessoa física). A conta PJ entra
  como fonte de arquivo: CSV do extrato, mesma normalização, mesmo destino. Ela muda
  pouco, então uma carga manual por mês resolve.
- Um destino novo (planilha, Telegram, o que for) vira uma classe.

### Contrato

- **Fonte**: recebe um período, devolve `list[Transaction]`. Não sabe para onde vai.
- **Destino**: recebe `list[Transaction]`, escreve. Idempotente pelo `external_id`.
- **Núcleo**: normaliza, deduplica e decide o que é gasto, o que é poupança e o que é
  transferência entre contas minhas.

## Fases

### Fase 0 — destravar

1. Decidir o destino do YNAB: aposentar, manter como comando manual, ou religar.
2. Consertar o que já está quebrado (lista abaixo).
3. Religar o agendamento só depois que existir um destino vivo.

### Fase 1 — fontes e destinos plugáveis

1. Extrair `sources/pluggy.py` e `sinks/ynab.py` do código atual, sem mudar comportamento.
2. Definir os dois protocolos (`Source`, `Sink`) com `typing.Protocol`.
3. `sources/csv_file.py` para o extrato da PJ e para backfill histórico.
4. Configuração declarativa: quais fontes, quais destinos, qual período.

### Fase 2 — atualização técnica

Este é o laboratório de aprender **ty** antes de propor no trabalho.

| Item | Hoje | Para onde |
|---|---|---|
| Python | 3.12 | **3.14** (EOL 2030), local já tem |
| Type checker | nenhum | **ty** (Astral, 0.0.78, em preview) |
| HTTP | `requests` | **httpx** (a `TODO.md` já pedia) |
| Mock de HTTP | `requests-mock` | **respx** (é o par do httpx) |
| Config | `python-decouple` | **pydantic-settings** (a `TODO.md` já pedia) |
| Lint/format | ruff 0.6 | ruff 0.16 |
| Teste | pytest 8 | pytest 9 |

Sobre o **ty**, que é o ponto do exercício:

- `uv add --dev ty`, depois `ty check`. Configuração em `[tool.ty]` no `pyproject.toml`,
  regras em `[tool.ty.rules]`.
- **Fixar a versão exata.** É 0.0.x, a superfície de configuração ainda muda entre
  releases. Um upgrade que quebra o CI é o custo de estar cedo.
- Adicionar como `task typecheck` no taskipy e no CI, começando sem falhar o build.
- O aprendizado que interessa levar para o trabalho: como o ty trata `Unknown` contra
  `Any`, quanto ele pega sem anotação nenhuma, e o que quebra numa base que hoje não
  tem type hint. Anotar as diferenças contra o mypy num arquivo aqui mesmo.
- Um projeto pequeno, com Pydantic e cliente HTTP, é a amostra certa: é a forma da
  maioria do código do trabalho.

Enquanto arruma os tipos, corrigir as anotações erradas: `-> [dict]` e `[Transaction]`
não são tipos, são listas literais. O certo é `list[dict]` e `list[Transaction]`.

### Fase 3 — a camada de análise

O que transforma isto num instrumento de análise, e não num sincronizador.

1. **Guardar o histórico.** SQLite fora do repositório, upsert pelo id do Pluggy.
   O histórico de transação é bem melhor do que eu esperava: a conta do Nubank tem 2.974
   lançamentos desde 07/11/2022 e o cartão tem 5.416. Isso dá um backfill de quatro anos
   sem baixar CSV nenhum. **O que não tem histórico são os saldos e os investimentos**:
   `/accounts` e `/investments` devolvem só a foto de hoje. A série mês a mês da reserva
   tem que ser construída por mim, um snapshot por dia.
2. **Snapshot diário** de saldos, caixinhas e ações. É o que permite responder
   "quanto eu guardei em agosto" sem print.
3. **Portar as regras do `custo_de_vida.py`** (que hoje vive no vault do life_os):
   movimento de RDB é poupança, entrada da LTDA é receita, dedup por identificador.
   Traduzir para as categorias do Pluggy.
4. **Rótulo das caixinhas.** O Pluggy não expõe o nome da caixinha. Cada uma é um
   conjunto de posições de CDB. Dá para separar por `rate` (120% do CDI são as duas
   Turbo) e por `issueDate`, mas isso é heurística: precisa de um arquivo de rótulo
   por id, conferido uma vez contra o app.
5. **Parcelas futuras.** O feed do cartão já traz as parcelas que ainda não venceram, com
   `installmentNumber` e `totalInstallments` no `creditCardMetadata`. Dá para somar quanto
   das faturas futuras já está comprometido. Hoje é pouco (R$ 2,90/mês até 05/2027), mas o
   mecanismo é o que importa.
6. **Relatório diário, semanal e mensal** em markdown, para o vault.

### Fase 4 — destino app do Breno

Só depois de sentar e mapear a API do Supabase junto. Requisitos que já sei:

- `dry-run` obrigatório: lista o que vai lançar, eu aprovo, só então escreve.
- Idempotente pelo id do Pluggy, para não duplicar lançamento.
- Respeitar os fixos pré-cadastrados no dia 01, que já existem no app.

## Bugs e dívidas conhecidas

- **`my_pluggy.py:79` pagina errado.** Busca página 1 com `pageSize=50` num range de 7
  dias e ignora `totalPages`. Uma semana movimentada trunca em silêncio.
- **`my_pluggy.py:36` autentica no import.** `headers_with_api_key` chama `get_api_key`
  no nível do módulo. Isso faz uma chamada de rede só por importar o arquivo, e é
  variável morta: `get_transactions` monta o header de novo. Deletar.
- **`ynab.py:5` lê o token no import.** Mesmo problema: importar exige `.env`.
- **`main.py:1-5` usa import relativo implícito** (`import ynab`, `from config import`).
  Só funciona rodando o arquivo direto de dentro da pasta. Não roda como pacote.
- **Anotações erradas**: `[dict]`, `[Transaction]`, `list[ANY]` com `ANY` importado de
  `unittest.mock`.
- **O cartão Itaú Visa Click está conectado no Pluggy e nunca foi sincronizado.**
- **`cert.p12` existe em dois lugares na máquina**, sobra do tempo do pynubank. Está no
  `.gitignore` e não foi commitado (conferido com `git ls-files`), mas não serve mais para
  nada. Apagar.
- `pyproject.toml` aponta `packages = ["src/financas_automatizadas"]`, mas não existe
  pasta `src/`.
- `README.md` aponta para `lipemorais/financas-automatizadas` e para um workflow com
  outro nome. O repositório é `felipythondev/financas-automatizadas`.

## Decisões em aberto

- [ ] Aposentar o YNAB, manter como comando manual, ou religar o cron?
- [ ] Onde ficam o SQLite e os relatórios, já que este repo é público?
- [ ] O código continua aqui, ou vai para um repo privado?
- [ ] Quando sentar para mapear a API do app do Breno?
