"""Histórico de publicações na Hotmart — o que já foi postado.

Grava um registro por publicação (append-only em data/historico.jsonl):
rede, país, título, tipo, id da Hotmart (se capturado) e quando.
Serve pra saber exatamente o que já subiu, agrupado por rede -> país.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "data" / "historico.jsonl"

_TRAVA = threading.Lock()


def registrar(*, rede: str, pais: str, titulo: str, tipo: str,
              hotmart_id: str = "", quando: str | None = None) -> dict:
    """Adiciona uma publicação ao histórico (append-only, seguro entre threads)."""
    reg = {
        "rede": rede or "",
        "pais": pais or "",
        "titulo": titulo or "",
        "tipo": tipo or "",
        "hotmart_id": hotmart_id or "",
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
            continue  # linha corrompida nao derruba o resto
    return out


def agrupado() -> dict:
    """{rede: {pais: [registros...]}} — pra montar a árvore rede -> país -> títulos."""
    arv: dict[str, dict] = {}
    for r in listar():
        arv.setdefault(r.get("rede", ""), {}).setdefault(r.get("pais", ""), []).append(r)
    return arv


def remover_tudo() -> int:
    """Limpa o histórico inteiro. Retorna quantos registros havia."""
    with _TRAVA:
        n = len(listar())
        if ARQUIVO.is_file():
            ARQUIVO.unlink()
        return n
