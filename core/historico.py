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
    return _parse(ARQUIVO)


def _parse(arquivo: Path) -> list[dict]:
    if not arquivo.is_file():
        return []
    out: list[dict] = []
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
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
    """'Limpa' o histórico movendo o arquivo pra um BACKUP datado — nada é
    apagado de verdade (recuperável pelo botão Recuperar). Retorna quantos havia."""
    with _TRAVA:
        n = len(listar())
        if ARQUIVO.is_file():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ARQUIVO.rename(ARQUIVO.with_name(f"historico-backup-{stamp}.jsonl"))
        return n


def restaurar_ultimo_backup() -> int:
    """Traz de volta o backup mais recente feito pelo 'Limpar histórico',
    juntando com o que existir hoje (sem duplicar). Retorna quantos voltaram."""
    with _TRAVA:
        backups = sorted(ARQUIVO.parent.glob("historico-backup-*.jsonl"))
        if not backups:
            return 0
        atuais = _parse(ARQUIVO)
        vistos = {json.dumps(r, sort_keys=True, ensure_ascii=False) for r in atuais}
        novos = [r for r in _parse(backups[-1])
                 if json.dumps(r, sort_keys=True, ensure_ascii=False) not in vistos]
        if novos:
            ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
            with open(ARQUIVO, "a", encoding="utf-8") as f:
                for r in novos:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(novos)
