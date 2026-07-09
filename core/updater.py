"""Auto-atualizacao do sistema — baixa a versao nova do GitHub (raw).

Mesmo padrao do thesalomoncode-landing, portado pra Python (sem Node):
  - O criador publica (PUBLICAR-ATUALIZACAO.bat -> manifest.json + push no GitHub).
  - O operador clica "Atualizar sistema" -> baixa os arquivos do raw.githubusercontent
    e sobrescreve os do sistema, SEM tocar em dados (data/) nem config (settings.json).

sys-config.json guarda o rawBase (ex.: https://raw.githubusercontent.com/USER/REPO/main).
version.json guarda a versao local (numero inteiro).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Prefixos/arquivos que a atualizacao NUNCA sobrescreve (dados e config do operador)
_NUNCA = ("config/settings.json", "sys-config.json", "version.json")
_NUNCA_PREFIXOS = ("data/", ".venv/", ".git/", "config/")


class UpdaterError(Exception):
    pass


# ---------------------------------------------------------------------------
# Downloaders padrao (injetaveis nos testes)
# ---------------------------------------------------------------------------
def _baixar_json_http(url: str):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _baixar_bytes_http(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        if r.status != 200:
            raise UpdaterError(f"HTTP {r.status}")
        return r.read()


# ---------------------------------------------------------------------------
# Leitura local
# ---------------------------------------------------------------------------
def ler_versao_local(root: Path | str = RAIZ) -> int:
    try:
        dados = json.loads((Path(root) / "version.json").read_text(encoding="utf-8"))
        return int(dados.get("version", 0)) or 0
    except Exception:
        return 0


def ler_rawbase(root: Path | str = RAIZ) -> str | None:
    try:
        dados = json.loads((Path(root) / "sys-config.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    raw = str(dados.get("rawBase", "")).rstrip("/")
    if raw.startswith("https://raw.githubusercontent.com/"):
        return raw
    return None


def _bust() -> str:
    return f"?t={int(time.time())}"


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def checar_versao(root: Path | str = RAIZ, *, baixar_json=_baixar_json_http) -> dict:
    """Compara a versao local com a ultima publicada no GitHub."""
    root = Path(root)
    local = ler_versao_local(root)
    raw = ler_rawbase(root)
    latest = None
    if raw:
        man = baixar_json(raw + "/manifest.json" + _bust())
        if man and "version" in man:
            try:
                latest = int(man["version"])
            except (TypeError, ValueError):
                latest = None
    return {
        "local": local,
        "latest": latest,
        "ha_atualizacao": latest is not None and latest > local,
    }


def _rel_seguro(caminho: str) -> str | None:
    """Normaliza e valida o caminho relativo do manifest (bloqueia traversal e protegidos)."""
    rel = str(caminho).replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    if rel in _NUNCA or rel.startswith(_NUNCA_PREFIXOS):
        return None
    return rel


def atualizar(root: Path | str = RAIZ, *,
              baixar_json=_baixar_json_http, baixar_bytes=_baixar_bytes_http) -> dict:
    """Baixa e sobrescreve os arquivos do sistema listados no manifest do GitHub.

    Retorna: {ok, version, updated, failed, restart, deps_changed, error}
    """
    root = Path(root).resolve()
    raw = ler_rawbase(root)
    if not raw:
        return {"ok": False, "error": "Atualização ainda não configurada (rode o CONFIGURAR-SISTEMA-GIT.bat).",
                "updated": [], "failed": [], "restart": False}

    bust = _bust()
    man = baixar_json(raw + "/manifest.json" + bust)
    if not man or not isinstance(man.get("files"), list):
        return {"ok": False, "error": "Não encontrei o manifest.json no GitHub (o criador já publicou?).",
                "updated": [], "failed": [], "restart": False}

    updated, failed = [], []
    for f in man["files"]:
        rel = _rel_seguro(f)
        if rel is None:
            continue
        destino = (root / rel).resolve()
        if root not in destino.parents and destino != root:
            continue  # defesa extra contra escapar da raiz
        try:
            url = raw + "/" + "/".join(urllib.parse.quote(p) for p in rel.split("/")) + bust
            conteudo = baixar_bytes(url)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            updated.append(rel)
        except Exception:
            failed.append(rel)

    if updated:
        versao = man.get("version", ler_versao_local(root))
        try:
            (root / "version.json").write_text(
                json.dumps({"version": int(versao)}, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    restart = any(rel.endswith(".py") for rel in updated)
    deps_changed = "requirements.txt" in updated
    return {
        "ok": len(updated) > 0,
        "version": man.get("version", ""),
        "updated": updated,
        "failed": failed,
        "restart": restart,
        "deps_changed": deps_changed,
        "error": "" if updated else "Nenhum arquivo atualizado.",
    }
