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
    numero, faltam, dias = diario.numero_do_dia(13379.14, FIXOS, date(2026, 10, 10))
    assert dias == 21
    assert round(sum(f["valor"] for f in faltam), 2) == 9161.19
    assert round(numero, 2) == 200.85


def test_fixo_do_proprio_dia_ja_saiu_do_saldo():
    _, faltam, _ = diario.numero_do_dia(16465.68, FIXOS, date(2026, 10, 9))
    assert "Spotify" not in [f["nome"] for f in faltam]


def test_ultimo_dia_do_mes_nao_divide_por_zero():
    numero, faltam, dias = diario.numero_do_dia(310.95, FIXOS, date(2026, 9, 30))
    assert dias == 1
    assert faltam == []
    assert numero == 310.95


def test_fixo_com_prazo_so_conta_dentro_do_prazo():
    advogada = {"nome": "Advogada", "valor": 1000.00, "dia": 10, "de": "2026-10", "ate": "2027-06"}
    fixos = FIXOS + [advogada]

    _, faltam_set, _ = diario.numero_do_dia(5000.0, fixos, date(2026, 9, 5))
    _, faltam_jun, _ = diario.numero_do_dia(5000.0, fixos, date(2027, 6, 5))
    _, faltam_jul, _ = diario.numero_do_dia(5000.0, fixos, date(2027, 7, 5))

    assert "Advogada" not in [f["nome"] for f in faltam_set]
    assert "Advogada" in [f["nome"] for f in faltam_jun]
    assert "Advogada" not in [f["nome"] for f in faltam_jul]


def test_teto_de_ontem_vem_da_foto_de_anteontem(tmp_path, monkeypatch):
    monkeypatch.setattr(diario, "SNAPSHOTS", tmp_path)
    foto = {"contas": [{"type": "BANK", "balance": 16465.68}]}
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
        diario.json.dumps({"contas": [{"type": "BANK", "balance": 310.95}]}), encoding="utf-8"
    )
    assert diario.teto_de(date(2026, 10, 1), FIXOS) is None
