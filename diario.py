"""Tira a foto do dia no Pluggy e escreve o relatorio diario no vault.

Duas coisas em um passo:

1. Captura. Contas, cartao, investimentos e as transacoes do mes viram um JSON
   por dia. Saldo e investimento nao tem historico na API, so a foto de hoje,
   entao cada dia sem captura e um dia que nao volta.
2. Relatorio. Refaz a conta do "numero do dia" do painel financeiro e compara o
   gasto de ontem com o numero da noite anterior.

O JSON e o relatorio vao para o vault, que e cifrado. Nunca para este
repositorio, que e publico.
"""

import json
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from decouple import Config, RepositoryEnv

API = "https://api.pluggy.ai"
NUBANK_ITEM_ID = "09c9a9a6-898d-4ecb-b228-daabb7d8ca6d"

ENV = Path(__file__).parent / ".env"
VAULT = Path.home() / "dev/life_os/Pessoal/Finanças"
SNAPSHOTS = VAULT / "Snapshots"
RELATORIOS = VAULT / "Relatórios"
FIXOS = VAULT / "fixos.json"

cfg = Config(RepositoryEnv(str(ENV)))


def api_key() -> str:
    r = requests.post(
        f"{API}/auth",
        json={
            "clientId": cfg("PLUGGY_CLIENT_ID"),
            "clientSecret": cfg("PLUGGY_CLIENT_SECRET"),
        },
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["apiKey"]


def get(path: str, key: str, **params) -> dict:
    r = requests.get(
        f"{API}/{path}",
        headers={"accept": "application/json", "X-API-KEY": key},
        params=params,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def paginado(path: str, key: str, **params) -> list:
    saida, pagina = [], 1
    while True:
        d = get(path, key, page=pagina, pageSize=500, **params)
        saida.extend(d.get("results", []))
        if pagina >= d.get("totalPages", 1):
            return saida
        pagina += 1


def brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def capturar(hoje: date) -> dict:
    key = api_key()
    item = cfg("PLUGGY_ITEM_ID", default=NUBANK_ITEM_ID)

    contas = get("accounts", key, itemId=item).get("results", [])
    investimentos = get("investments", key, itemId=item).get("results", [])

    inicio = hoje.replace(day=1).isoformat()
    transacoes = {
        c["id"]: paginado("transactions", key, accountId=c["id"], **{"from": inicio})
        for c in contas
    }

    return {
        "data": hoje.isoformat(),
        "itemId": item,
        "contas": contas,
        "investimentos": investimentos,
        "transacoes": transacoes,
    }


def saldo_em_conta(foto: dict) -> float:
    conta = next((c for c in foto["contas"] if c["type"] == "BANK"), None)
    return float(conta["balance"]) if conta else 0.0


def vigentes(fixos: list, dia: date) -> list:
    """Os fixos que valem no mês do dia. `de` e `ate` são opcionais, no formato AAAA-MM."""
    mes = f"{dia.year}-{dia.month:02d}"
    return [f for f in fixos if f.get("de", mes) <= mes <= f.get("ate", mes)]


def data_de(t: dict) -> date:
    return datetime.fromisoformat(t["date"].replace("Z", "+00:00")).date()


def debitos_do_mes(foto: dict, dia: date) -> list[float]:
    """As saídas da conta corrente do dia 1 até o dia, em valor positivo."""
    conta = next((c for c in foto["contas"] if c["type"] == "BANK"), None)
    if conta is None:
        return []
    return [
        abs(float(t["amount"]))
        for t in foto["transacoes"][conta["id"]]
        if float(t["amount"]) < 0
        and (data_de(t).year, data_de(t).month) == (dia.year, dia.month)
        and data_de(t) <= dia
    ]


def ids_quitados(fixos: list, debitos: list[float]) -> set[int]:
    """Os fixos que um débito do mês já pagou, mesmo antes do dia agendado.

    Débito e fixo casam pelo valor. Cada débito paga um fixo só, e o fixo mais cedo
    no mês casa primeiro: com duas Magalis de R$ 300 e um Pix de R$ 300, a 1ª está
    paga e a 2ª ainda falta.
    """
    sobra = list(debitos)
    quitados = set()
    for f in sorted(fixos, key=lambda f: int(f["dia"])):
        casou = next(
            (i for i, v in enumerate(sobra) if abs(v - float(f["valor"])) < 0.01), None
        )
        if casou is not None:
            sobra.pop(casou)
            quitados.add(id(f))
    return quitados


def numero_do_dia(
    saldo: float, fixos: list, dia: date, debitos: list[float]
) -> tuple[float, list, int]:
    """O quanto cabe por dia do dia seguinte até o fim do mês.

    A foto sai às 23h30, então o saldo já desconta o gasto e os fixos do próprio
    dia. Contar o dia de hoje de novo dividiria o saldo por um dia que já passou.
    Um fixo pago antes do dia agendado também já saiu do saldo, então não conta.
    """
    do_mes = vigentes(fixos, dia)
    quitados = ids_quitados(do_mes, debitos)
    faltam = [f for f in do_mes if int(f["dia"]) > dia.day and id(f) not in quitados]
    dias_no_mes = monthrange(dia.year, dia.month)[1]
    dias_restantes = max(dias_no_mes - dia.day, 1)
    total_fixos = sum(float(f["valor"]) for f in faltam)
    return (saldo - total_fixos) / dias_restantes, faltam, dias_restantes


def teto_de(dia: date, fixos: list) -> float | None:
    """O teto de um dia é o número do dia calculado na noite anterior.

    Sem a foto da noite anterior não há teto, e no dia 1 a distribuição entra e a
    foto do mês anterior deixa de valer.
    """
    if dia.day == 1:
        return None
    arquivo = SNAPSHOTS / f"{(dia - timedelta(days=1)).isoformat()}.json"
    if not arquivo.exists():
        return None
    foto = json.loads(arquivo.read_text(encoding="utf-8"))
    anteontem = dia - timedelta(days=1)
    return numero_do_dia(
        saldo_em_conta(foto), fixos, anteontem, debitos_do_mes(foto, anteontem)
    )[0]


def relatorio(foto: dict, hoje: date) -> str:
    conf = json.loads(FIXOS.read_text(encoding="utf-8"))

    conta = next((c for c in foto["contas"] if c["type"] == "BANK"), None)
    cartao = next((c for c in foto["contas"] if c["type"] == "CREDIT"), None)
    saldo = saldo_em_conta(foto)

    numero, faltam, dias_restantes = numero_do_dia(
        saldo, conf["fixos"], hoje, debitos_do_mes(foto, hoje)
    )
    total_fixos = sum(float(f["valor"]) for f in faltam)
    dias_no_mes = monthrange(hoje.year, hoje.month)[1]

    ontem = hoje - timedelta(days=1)
    lancamentos = foto["transacoes"].get(conta["id"], []) if conta else []

    def eh_fixo(t):
        v = abs(float(t["amount"]))
        return any(
            abs(v - float(f["valor"])) < 0.01
            for f in vigentes(conf["fixos"], data_de(t))
        )

    def eh_gasto(t):
        """Poupanca e transferencia entre contas minhas nao sao gasto.

        O Pluggy ja separa: categoria 03 e investimento, 04 e transferencia para
        mim mesmo. E a mesma regra do custo_de_vida.py da revisao mensal.
        """
        cat = str(t.get("categoryId") or "")
        return not (cat.startswith("03") or cat.startswith("04")) and not eh_fixo(t)

    saidas_ontem = [
        t
        for t in lancamentos
        if data_de(t) == ontem and float(t["amount"]) < 0 and eh_gasto(t)
    ]
    nao_contados = [
        t
        for t in lancamentos
        if data_de(t) == ontem and float(t["amount"]) < 0 and not eh_gasto(t)
    ]
    gasto_ontem = sum(-float(t["amount"]) for t in saidas_ontem)

    bruto = sum(i.get("amount") or 0 for i in foto["investimentos"])
    liquido = sum(i.get("balance") or 0 for i in foto["investimentos"])

    teto = teto_de(ontem, conf["fixos"])
    if teto is None:
        comparacao = [
            f"Gastou **R$ {brl(gasto_ontem)}** em {ontem.strftime('%d/%m')}. Sem teto para",
            "comparar: não há foto da noite anterior, ou o dia foi o 1º do mês.",
        ]
    else:
        veredito = "abaixo do teto" if gasto_ontem <= teto else "**acima do teto**"
        comparacao = [
            f"Gastou **R$ {brl(gasto_ontem)}** em {ontem.strftime('%d/%m')}, contra o teto de R$ {brl(teto)}. Ficou {veredito}",
            f"por R$ {brl(abs(teto - gasto_ontem))}.",
        ]

    linhas = [
        "---",
        f'name: "Diário {hoje.isoformat()}"',
        "description: Relatório financeiro do dia, gerado pelo diario.py a partir do Pluggy",
        "metadata:",
        "  type: relatorio",
        "tags: [financas, diario, pluggy, gerado]",
        "---",
        "",
        f"# Diário — {hoje.strftime('%d/%m/%Y')}",
        "",
        "> Gerado por `diario.py`. **Nenhum número foi digitado à mão.**",
        "",
        "## O número do dia",
        "",
        f"**R$ {brl(numero)} por dia** de amanhã até {dias_no_mes}/{hoje.month:02d}.",
        "",
        f"- Saldo em conta: **R$ {brl(saldo)}**",
        f"- Fixos que ainda vencem: **R$ {brl(total_fixos)}** ({len(faltam)} lançamentos)",
        f"- Dias restantes, a partir de amanhã: **{dias_restantes}**",
        "",
        "## Ontem contra o teto",
        "",
        "O teto de um dia é o número do dia calculado na noite anterior.",
        "",
        *comparacao,
        "",
    ]

    if saidas_ontem:
        linhas += ["| Hora | Valor | O quê |", "|---|---:|---|"]
        for t in sorted(saidas_ontem, key=lambda x: x["date"]):
            hora = datetime.fromisoformat(t["date"].replace("Z", "+00:00")).strftime(
                "%H:%M"
            )
            linhas.append(
                f"| {hora} | {brl(-float(t['amount']))} | {t['description'].strip()} |"
            )
        linhas.append("")
    else:
        linhas += ["Nenhuma saída registrada.", ""]

    if nao_contados:
        linhas += [
            "**Não contados**, porque poupança e transferência entre contas minhas não são gasto:",
            "",
        ]
        for t in sorted(nao_contados, key=lambda x: x["date"]):
            linhas.append(
                f"- R$ {brl(-float(t['amount']))} · {t['description'].strip()} · _{t.get('category')}_"
            )
        linhas.append("")

    if faltam:
        linhas += [
            "## Os fixos que faltam",
            "",
            "| Dia | Valor | O quê |",
            "|---:|---:|---|",
        ]
        for f in sorted(faltam, key=lambda x: int(x["dia"])):
            linhas.append(f"| {f['dia']} | {brl(float(f['valor']))} | {f['nome']} |")
        linhas.append("")

    if cartao:
        cd = cartao.get("creditData") or {}
        linhas += [
            "## Cartão",
            "",
            f"**R$ {brl(float(cartao['balance']))} em aberto.** Vencimento informado pelo banco: {cd.get('balanceDueDate', '?')}.",
            f"Limite disponível: R$ {brl(float(cd.get('availableCreditLimit') or 0))} de R$ {brl(float(cd.get('creditLimit') or 0))}.",
            "",
        ]

    linhas += [
        "## Investido",
        "",
        f"**R$ {brl(bruto)} bruto**, R$ {brl(liquido)} líquido.",
        f"**R$ {brl(bruto - liquido)} de IR embutido** se eu resgatar tudo hoje.",
        "",
        "## Relacionadas",
        "",
        "- [[00 - Painel Financeiro]] — o estado corrente, e de onde vem o teto",
        "- [[Automação - Pluggy]] — o que esta automação substitui",
    ]
    return "\n".join(linhas) + "\n"


def main() -> int:
    hoje = date.today()
    foto = capturar(hoje)

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    alvo_json = SNAPSHOTS / f"{hoje.isoformat()}.json"
    alvo_json.write_text(
        json.dumps(foto, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    RELATORIOS.mkdir(parents=True, exist_ok=True)
    alvo_md = RELATORIOS / f"{hoje.isoformat()}.md"
    alvo_md.write_text(relatorio(foto, hoje), encoding="utf-8")

    print(f"snapshot  -> {alvo_json}")
    print(f"relatorio -> {alvo_md}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as e:
        print(
            f"pluggy respondeu {e.response.status_code}: {e.response.text[:200]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
