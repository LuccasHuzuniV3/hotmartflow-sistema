"""Testes do gerador de manifest.json."""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import make_manifest  # noqa: E402


def montar_projeto(tmp_path):
    (tmp_path / "app" / "web").mkdir(parents=True)
    (tmp_path / "core").mkdir()
    (tmp_path / "app" / "server.py").write_text("x", encoding="utf-8")
    (tmp_path / "app" / "web" / "app.js").write_text("x", encoding="utf-8")
    (tmp_path / "core" / "scanner.py").write_text("x", encoding="utf-8")
    (tmp_path / "start.bat").write_text("x", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("x", encoding="utf-8")
    # coisas que NAO entram no manifest:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text("x", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.json").write_text("x", encoding="utf-8")
    (tmp_path / "core" / "__pycache__").mkdir()
    (tmp_path / "core" / "__pycache__" / "c.pyc").write_text("x", encoding="utf-8")
    (tmp_path / "sys-config.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_lista_codigo_e_ignora_dados(tmp_path):
    montar_projeto(tmp_path)
    files = make_manifest.listar_arquivos(tmp_path)
    assert "app/server.py" in files
    assert "app/web/app.js" in files
    assert "core/scanner.py" in files
    assert "start.bat" in files
    assert "requirements.txt" in files
    # NAO pode listar dados/config/cache
    assert not any(f.startswith("config/") for f in files)
    assert not any(f.startswith("data/") for f in files)
    assert not any("__pycache__" in f for f in files)
    assert "sys-config.json" not in files


def test_gerar_cria_manifest_e_incrementa_versao(tmp_path):
    montar_projeto(tmp_path)
    (tmp_path / "version.json").write_text(json.dumps({"version": 4}), encoding="utf-8")
    r = make_manifest.gerar(tmp_path)
    assert r["version"] == 5
    man = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert man["version"] == 5
    assert "app/server.py" in man["files"]
    assert json.loads((tmp_path / "version.json").read_text(encoding="utf-8"))["version"] == 5


def test_gerar_sem_version_comeca_em_1(tmp_path):
    montar_projeto(tmp_path)
    r = make_manifest.gerar(tmp_path)
    assert r["version"] == 1


def test_paths_usam_barra_normal(tmp_path):
    montar_projeto(tmp_path)
    files = make_manifest.listar_arquivos(tmp_path)
    assert all("\\" not in f for f in files)
