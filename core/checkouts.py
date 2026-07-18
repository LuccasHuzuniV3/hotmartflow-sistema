"""Histórico dos LINKS de checkout gerados (custom-checkout.hotmart.com).

Um registro por página publicada: rede, país, título do principal e o link
https://pay.hotmart.com/... capturado na tela de sucesso. Append-only em
data/checkouts.jsonl — mesmo padrão do histórico de publicações.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "data" / "checkouts.jsonl"

_TRAVA = threading.Lock()


def registrar(*, rede: str, pais: str, titulo: str, link: str,
              quando: str | None = None) -> dict:
    reg = {
        "rede": rede or "",
        "pais": pais or "",
        "titulo": titulo or "",
        "link": link or "",
        "quando": quando or datetime.now().isoformat(timespec="seconds"),
    }
    with _TRAVA:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQUIVO, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg


def listar() -> list[dict]:
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


def agrupado() -> dict:
    """{rede: {pais: [registros...]}} — árvore rede -> país -> links."""
    arv: dict[str, dict] = {}
    for r in listar():
        arv.setdefault(r.get("rede", ""), {}).setdefault(r.get("pais", ""), []).append(r)
    return arv
