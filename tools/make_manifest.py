"""Gera o manifest.json (lista de arquivos do SISTEMA) e incrementa version.json.

Rodado pelo PUBLICAR-ATUALIZACAO.bat antes do git push. O operador baixa
esses arquivos no "Atualizar sistema". NAO inclui dados (data/), config
(config/, sys-config.json) nem caches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# arquivos soltos na raiz que fazem parte do sistema
ARQUIVOS_RAIZ = ["start.bat", "requirements.txt", "README.md"]
# pastas de codigo varridas por completo (menos caches)
PASTAS_CODIGO = ["app", "core"]
IGNORAR_DIR = {"__pycache__", ".pytest_cache"}
IGNORAR_SUFIXO = {".pyc"}


def listar_arquivos(root: Path | str = RAIZ) -> list[str]:
    root = Path(root)
    files: list[str] = []

    for nome in ARQUIVOS_RAIZ:
        if (root / nome).is_file():
            files.append(nome)

    for pasta in PASTAS_CODIGO:
        base = root / pasta
        if not base.is_dir():
            continue
        for arq in base.rglob("*"):
            if not arq.is_file():
                continue
            if any(parte in IGNORAR_DIR for parte in arq.relative_to(root).parts):
                continue
            if arq.suffix in IGNORAR_SUFIXO:
                continue
            files.append(arq.relative_to(root).as_posix())

    return sorted(files)


def gerar(root: Path | str = RAIZ) -> dict:
    root = Path(root)
    try:
        v = int(json.loads((root / "version.json").read_text(encoding="utf-8")).get("version", 0))
    except Exception:
        v = 0
    v += 1

    files = listar_arquivos(root)
    manifest = {"version": v, "files": files}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "version.json").write_text(json.dumps({"version": v}, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = gerar()
    print(f"manifest.json gerado: versao {m['version']} ({len(m['files'])} arquivos)")
    sys.exit(0)
