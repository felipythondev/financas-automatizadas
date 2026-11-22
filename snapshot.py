"""Tira a foto do dia: contas, cartao e investimentos do Pluggy.

Roda todo dia. Saldo e investimento nao tem historico na API, so a foto de hoje,
entao cada dia sem snapshot e um dia que nao volta.

O JSON vai para o vault, que e cifrado com git-crypt. Nunca para este repositorio,
que e publico.
"""

import json
import sys
from datetime import date
from pathlib import Path

import requests
from decouple import Config, RepositoryEnv

ENV = Path(__file__).parent / ".env"
DESTINO = Path.home() / "dev/life_os/Pessoal/Finanças/Snapshots"
API = "https://api.pluggy.ai"
NUBANK_ITEM_ID = "09c9a9a6-898d-4ecb-b228-daabb7d8ca6d"

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


def main() -> int:
    key = api_key()
    item_id = cfg("PLUGGY_ITEM_ID", default=NUBANK_ITEM_ID)

    contas = get("accounts", key, itemId=item_id).get("results", [])
    investimentos = get("investments", key, itemId=item_id).get("results", [])

    foto = {
        "data": date.today().isoformat(),
        "itemId": item_id,
        "contas": contas,
        "investimentos": investimentos,
    }

    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivo = DESTINO / f"{foto['data']}.json"
    arquivo.write_text(json.dumps(foto, ensure_ascii=False, indent=2), encoding="utf-8")

    bruto = sum(i.get("amount") or 0 for i in investimentos)
    liquido = sum(i.get("balance") or 0 for i in investimentos)

    print(f"snapshot {foto['data']} -> {arquivo}")
    print(f"contas: {len(contas)} · investimentos: {len(investimentos)}")
    for c in contas:
        print(f"  {c.get('type')} {c.get('name')}: {c.get('balance')}")
    print(f"investido bruto: {bruto:.2f} · liquido: {liquido:.2f} · IR embutido: {bruto - liquido:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
