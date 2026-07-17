"""Fila de cupons PENDENTES — cupons que a Hotmart recusou na hora.

Caso típico: o robô finaliza o cadastro e tenta criar o cupom SEGUNDOS depois,
mas o produto ainda está "Em análise" — a API devolve 400. O cupom fica
guardado aqui (data/cupons_pendentes.jsonl) e é retentado:
  - automaticamente a cada nova publicação (o produto anterior já pode ter
    sido aprovado), e
  - pelo botão "Tentar criar cupons pendentes" na aba Histórico.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from core import hotmart_api

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "data" / "cupons_pendentes.jsonl"

_TRAVA = threading.Lock()


def registrar(*, product_id: str, codigo: str, desconto_pct: float,
              titulo: str = "", pais: str = "", erro: str = "") -> dict:
    """Guarda (ou atualiza) o cupom pendente do produto. 1 registro por produto."""
    reg = {
        "product_id": str(product_id),
        "codigo": codigo,
        "desconto_pct": float(desconto_pct),
        "titulo": titulo or "",
        "pais": pais or "",
        "erro": (erro or "")[:300],
        "quando": datetime.now().isoformat(timespec="seconds"),
    }
    with _TRAVA:
        atuais = [r for r in _ler() if r.get("product_id") != reg["product_id"]]
        atuais.append(reg)
        _gravar(atuais)
    return reg


def listar() -> list[dict]:
    with _TRAVA:
        return _ler()


def remover(product_id: str) -> None:
    with _TRAVA:
        _gravar([r for r in _ler() if r.get("product_id") != str(product_id)])


def tentar_todos(client_id: str, client_secret: str) -> dict:
    """Tenta criar TODOS os cupons pendentes. Sucesso sai da fila; falha fica
    (com o erro atualizado). Retorna {"criados": [...], "falhas": [...]}."""
    pendentes = listar()
    criados, falhas = [], []
    for reg in pendentes:
        try:
            hotmart_api.criar_cupom(
                product_id=reg["product_id"],
                codigo=reg["codigo"],
                desconto_pct=reg["desconto_pct"],
                client_id=client_id,
                client_secret=client_secret,
            )
            remover(reg["product_id"])
            criados.append(reg)
        except hotmart_api.HotmartApiError as e:
            registrar(product_id=reg["product_id"], codigo=reg["codigo"],
                      desconto_pct=reg["desconto_pct"], titulo=reg.get("titulo", ""),
                      pais=reg.get("pais", ""), erro=str(e))
            falhas.append({**reg, "erro": str(e)[:300]})
    return {"criados": criados, "falhas": falhas}


# ---------------------------------------------------------------------------
def _ler() -> list[dict]:
    if not ARQUIVO.is_file():
        return []
    out: list[dict] = []
    try:
        linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        try:
            out.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return out


def _gravar(registros: list[dict]) -> None:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
