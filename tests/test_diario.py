from datetime import date

import diario

# Fixos de outubro/2026, com os valores reais de setembro.
FIXOS = [
    {"nome": "Pai", "valor": 2000.00, "dia": 1},
    {"nome": "Spotify", "valor": 40.90, "dia": 9},
    {"nome": "Netflix", "valor": 59.90, "dia": 14},
    {"nome": "Condomínio", "valor": 1558.67, "dia": 15},
    {"nome": "Itaú", "valor": 4704.35, "dia": 15},
    {"nome": "Magali (1ª)", "valor": 300.00, "dia": 15},
    {"nome": "Carro", "valor": 2193.27, "dia": 21},
    {"nome": "Nucel", "valor": 45.00, "dia": 24},
    {"nome": "Magali (2ª)", "valor": 300.00, "dia": 29},
]


def test_numero_do_dia_nao_conta_o_dia_que_ja_foi_gasto():
    # A foto sai às 23h30: o saldo de 10/10 já desconta o gasto de 10/10.
    numero, faltam, dias = diario.numero_do_dia(13379.14, FIXOS, date(2026, 10, 10), [])
    assert dias == 21
    assert round(sum(f["valor"] for f in faltam), 2) == 9161.19
    assert round(numero, 2) == 200.85


def test_fixo_do_proprio_dia_ja_saiu_do_saldo():
    _, faltam, _ = diario.numero_do_dia(16465.68, FIXOS, date(2026, 10, 9), [])
    assert "Spotify" not in [f["nome"] for f in faltam]


def test_ultimo_dia_do_mes_nao_divide_por_zero():
    numero, faltam, dias = diario.numero_do_dia(310.95, FIXOS, date(2026, 9, 30), [])
    assert dias == 1
    assert faltam == []
    assert numero == 310.95


def test_fixo_com_prazo_so_conta_dentro_do_prazo():
    advogada = {
        "nome": "Advogada",
        "valor": 1000.00,
        "dia": 10,
        "de": "2026-10",
        "ate": "2027-06",
    }
    fixos = FIXOS + [advogada]

    _, faltam_set, _ = diario.numero_do_dia(5000.0, fixos, date(2026, 9, 5), [])
    _, faltam_jun, _ = diario.numero_do_dia(5000.0, fixos, date(2027, 6, 5), [])
    _, faltam_jul, _ = diario.numero_do_dia(5000.0, fixos, date(2027, 7, 5), [])

    assert "Advogada" not in [f["nome"] for f in faltam_set]
    assert "Advogada" in [f["nome"] for f in faltam_jun]
    assert "Advogada" not in [f["nome"] for f in faltam_jul]


def test_teto_de_ontem_vem_da_foto_de_anteontem(tmp_path, monkeypatch):
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    foto = {
        "contas": [{"id": "pf", "type": "BANK", "balance": 16465.68}],
        "transacoes": {"pf": []},
    }
    (tmp_path / "2026-10-08.json").write_text(diario.json.dumps(foto), encoding="utf-8")

    # Relatório de 10/10 julga o gasto de 09/10 contra o número da noite de 08/10.
    teto = diario.teto_de(date(2026, 10, 9), FIXOS)
    assert round(teto, 2) == round((16465.68 - 9202.09) / 23, 2)


def test_sem_foto_de_anteontem_nao_inventa_teto(tmp_path, monkeypatch):
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    assert diario.teto_de(date(2026, 10, 9), FIXOS) is None


def test_dia_1_nao_tem_teto(tmp_path, monkeypatch):
    # No dia 1 entra a distribuição, então a foto do mês anterior não serve de régua.
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    (tmp_path / "2026-09-30.json").write_text(
        diario.json.dumps(
            {
                "contas": [{"id": "pf", "type": "BANK", "balance": 310.95}],
                "transacoes": {"pf": []},
            }
        ),
        encoding="utf-8",
    )
    assert diario.teto_de(date(2026, 10, 1), FIXOS) is None


# Fixos de novembro/2026 e a foto da noite de 20/11, com os valores reais.
FIXOS_NOV = [
    {"nome": "Magali (1ª)", "valor": 300.00, "dia": 15},
    {"nome": "Carro", "valor": 2193.27, "dia": 22},
    {"nome": "Nucel", "valor": 45.00, "dia": 24},
    {"nome": "Magali (2ª)", "valor": 300.00, "dia": 29},
]


def nomes(faltam):
    return [f["nome"] for f in faltam]


def test_fixo_pago_antes_do_dia_agendado_nao_conta_de_novo():
    # A parcela do carro vence dia 22 e saiu em 19/11. O saldo de 20/11 já está sem ela.
    _, faltam, _ = diario.numero_do_dia(
        1237.56, FIXOS_NOV, date(2026, 11, 20), [2193.27]
    )
    assert "Carro" not in nomes(faltam)


def test_fixo_ainda_nao_pago_continua_contando():
    _, faltam, _ = diario.numero_do_dia(1237.56, FIXOS_NOV, date(2026, 11, 20), [])
    assert "Carro" in nomes(faltam)


def test_um_pagamento_quita_so_um_dos_fixos_de_mesmo_valor():
    # Duas Magalis de R$ 300. Um Pix de R$ 300 paga a 1ª, a 2ª continua faltando.
    _, faltam, _ = diario.numero_do_dia(5000.0, FIXOS_NOV, date(2026, 11, 10), [300.00])
    assert nomes(faltam).count("Magali (2ª)") == 1
    assert "Magali (1ª)" not in nomes(faltam)


def test_numero_do_dia_de_20_11_com_o_que_ja_foi_pago():
    # Em 20/11 já tinham saído o carro (19/11) e as duas Magalis (05/11 e 19/11).
    # Falta só o Nucel: (1237,56 - 45) / 10 dias.
    numero, faltam, dias = diario.numero_do_dia(
        1237.56, FIXOS_NOV, date(2026, 11, 20), [300.00, 2193.27, 300.00]
    )
    assert nomes(faltam) == ["Nucel"]
    assert dias == 10
    assert round(numero, 2) == 119.26


def test_debitos_do_mes_so_pega_saidas_da_conta_no_mes_ate_o_dia():
    foto = {
        "contas": [{"id": "pf", "type": "BANK"}, {"id": "cartao", "type": "CREDIT"}],
        "transacoes": {
            "pf": [
                {"date": "2026-10-31T15:00:00.000Z", "amount": -50.00},  # mês anterior
                {"date": "2026-11-05T00:26:12.602Z", "amount": -300.00},
                {"date": "2026-11-19T11:21:30.717Z", "amount": -2193.27},
                {"date": "2026-11-19T12:00:00.000Z", "amount": 1000.00},  # entrada
                {"date": "2026-11-21T10:00:00.000Z", "amount": -45.00},  # depois do dia
            ],
            "cartao": [{"date": "2026-11-10T10:00:00.000Z", "amount": -300.00}],
        },
    }
    assert diario.debitos_do_mes(foto, date(2026, 11, 20)) == [300.00, 2193.27]


def test_teto_desconta_o_fixo_que_a_foto_mostra_pago(tmp_path, monkeypatch):
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    foto = {
        "contas": [{"id": "pf", "type": "BANK", "balance": 1237.56}],
        "transacoes": {
            "pf": [
                {"date": "2026-11-05T00:26:12.602Z", "amount": -300.00},
                {"date": "2026-11-19T11:21:30.717Z", "amount": -2193.27},
                {"date": "2026-11-19T11:55:56.704Z", "amount": -300.00},
            ]
        },
    }
    (tmp_path / "2026-11-20.json").write_text(diario.json.dumps(foto), encoding="utf-8")

    # O relatório de 22/11 julga o gasto de 21/11 contra o número da noite de 20/11.
    assert round(diario.teto_de(date(2026, 11, 21), FIXOS_NOV), 2) == 119.26


def test_data_de_usa_o_horario_de_porto_alegre():
    # 21h30 de 20/11 em Porto Alegre é 00h30 de 21/11 em UTC.
    assert diario.data_de({"date": "2026-11-21T00:30:00.000Z"}) == date(2026, 11, 20)


def test_lancamento_sem_hora_fica_no_dia_que_o_banco_informou():
    # O banco manda lançamentos só com data (IOF, por exemplo) como meia-noite UTC.
    assert diario.data_de({"date": "2026-09-30T00:00:00.001Z"}) == date(2026, 9, 30)


def test_debito_da_noite_do_ultimo_dia_fica_no_mes_anterior():
    # 22h de 31/10 em Porto Alegre é 01h de 01/11 em UTC: não paga o carro de novembro.
    foto = {
        "contas": [{"id": "pf", "type": "BANK"}],
        "transacoes": {
            "pf": [
                {"date": "2026-11-01T01:00:00.000Z", "amount": -2193.27},
                {"date": "2026-11-21T00:30:00.000Z", "amount": -45.00},
            ]
        },
    }
    assert diario.debitos_do_mes(foto, date(2026, 11, 20)) == [45.00]


def test_relatorio_desconta_os_fixos_ja_pagos(tmp_path, monkeypatch):
    fixos = tmp_path / "fixos.json"
    fixos.write_text(diario.json.dumps({"fixos": FIXOS_NOV}), encoding="utf-8")
    monkeypatch.setattr(diario, "FIXOS", fixos)
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    foto = {
        "contas": [{"id": "pf", "type": "BANK", "balance": 1237.56}],
        "investimentos": [],
        "transacoes": {
            "pf": [
                {
                    "date": "2026-11-05T00:26:12.602Z",
                    "amount": -300.00,
                    "description": "Transferência enviada pelo Pix|Magali",
                    "categoryId": "05000000",
                },
                {
                    "date": "2026-11-19T11:21:30.717Z",
                    "amount": -2193.27,
                    "description": "Pagamento efetuado|BANCO GM S.A.",
                    "categoryId": "05000000",
                },
                {
                    "date": "2026-11-19T11:55:56.704Z",
                    "amount": -300.00,
                    "description": "Transferência enviada pelo Pix|Magali",
                    "categoryId": "05000000",
                },
            ]
        },
    }
    texto = diario.relatorio(foto, date(2026, 11, 20))
    assert "**R$ 119,26 por dia**" in texto


def test_hora_do_gasto_sai_no_horario_de_porto_alegre(tmp_path, monkeypatch):
    fixos = tmp_path / "fixos.json"
    fixos.write_text(diario.json.dumps({"fixos": FIXOS_NOV}), encoding="utf-8")
    monkeypatch.setattr(diario, "FIXOS", fixos)
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    uber = {
        "date": "2026-11-19T18:35:00.000Z",
        "amount": -18.75,
        "description": "Compra no débito via NuPay|Uber",
        "categoryId": "05070000",
    }
    foto = {
        "contas": [{"id": "pf", "type": "BANK", "balance": 1237.56}],
        "investimentos": [],
        "transacoes": {"pf": [uber]},
    }
    texto = diario.relatorio(foto, date(2026, 11, 20))
    assert "| 15:35 | 18,75 |" in texto
