"""Testes do auto-updater (baixa a versao nova do GitHub). Nada bate na rede:
os downloaders sao injetados nos testes."""
import json

import pytest

from core import updater


def montar_root(tmp_path, versao_local=1, rawbase="https://raw.githubusercontent.com/user/repo/main"):
    (tmp_path / "version.json").write_text(json.dumps({"version": versao_local}), encoding="utf-8")
    (tmp_path / "sys-config.json").write_text(json.dumps({"rawBase": rawbase}), encoding="utf-8")
    (tmp_path / "core").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text('{"provider":"agy"}', encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Leitura de versao / rawbase
# ---------------------------------------------------------------------------
def test_ler_versao_local(tmp_path):
    montar_root(tmp_path, versao_local=7)
    assert updater.ler_versao_local(tmp_path) == 7


def test_ler_versao_local_ausente_retorna_zero(tmp_path):
    assert updater.ler_versao_local(tmp_path) == 0


def test_rawbase_configurada(tmp_path):
    montar_root(tmp_path)
    assert updater.ler_rawbase(tmp_path).endswith("/main")


def test_rawbase_ausente_retorna_none(tmp_path):
    assert updater.ler_rawbase(tmp_path) is None


# ---------------------------------------------------------------------------
# Checar versao (local vs remoto)
# ---------------------------------------------------------------------------
def test_checar_versao_ha_atualizacao(tmp_path):
    montar_root(tmp_path, versao_local=3)
    r = updater.checar_versao(tmp_path, baixar_json=lambda url: {"version": 5, "files": []})
    assert r["local"] == 3
    assert r["latest"] == 5
    assert r["ha_atualizacao"] is True


def test_checar_versao_em_dia(tmp_path):
    montar_root(tmp_path, versao_local=5)
    r = updater.checar_versao(tmp_path, baixar_json=lambda url: {"version": 5, "files": []})
    assert r["ha_atualizacao"] is False


def test_checar_versao_sem_rawbase(tmp_path):
    (tmp_path / "version.json").write_text('{"version": 1}', encoding="utf-8")
    r = updater.checar_versao(tmp_path, baixar_json=lambda url: {"version": 9})
    assert r["latest"] is None
    assert r["ha_atualizacao"] is False


# ---------------------------------------------------------------------------
# Atualizar
# ---------------------------------------------------------------------------
def test_atualizar_baixa_e_escreve_arquivos(tmp_path):
    montar_root(tmp_path)
    manifest = {"version": 2, "files": ["core/novo.py", "app/web/app.js"]}
    conteudos = {
        "core/novo.py": b"print('novo')",
        "app/web/app.js": b"// js novo",
    }
    r = updater.atualizar(
        tmp_path,
        baixar_json=lambda url: manifest,
        baixar_bytes=lambda url: conteudos[url.split("/main/")[1].split("?")[0]],
    )
    assert r["ok"] is True
    assert r["version"] == 2
    assert set(r["updated"]) == {"core/novo.py", "app/web/app.js"}
    assert (tmp_path / "core" / "novo.py").read_bytes() == b"print('novo')"
    assert (tmp_path / "app" / "web" / "app.js").read_bytes() == b"// js novo"
    # version.json local foi atualizado
    assert updater.ler_versao_local(tmp_path) == 2


def test_atualizar_nunca_sobrescreve_dados_e_config(tmp_path):
    montar_root(tmp_path)
    manifest = {"version": 2, "files": ["config/settings.json", "sys-config.json",
                                        "data/produtos/x.json", "core/ok.py"]}
    r = updater.atualizar(
        tmp_path,
        baixar_json=lambda url: manifest,
        baixar_bytes=lambda url: b"HACKEADO",
    )
    # so o core/ok.py foi escrito; o resto ficou de fora
    assert r["updated"] == ["core/ok.py"]
    assert (tmp_path / "config" / "settings.json").read_text(encoding="utf-8") == '{"provider":"agy"}'
    assert not (tmp_path / "data").exists()


def test_atualizar_rejeita_path_traversal(tmp_path):
    montar_root(tmp_path)
    manifest = {"version": 2, "files": ["../fora.py", "core/../../escapou.py"]}
    r = updater.atualizar(
        tmp_path,
        baixar_json=lambda url: manifest,
        baixar_bytes=lambda url: b"x",
    )
    assert r["updated"] == []
    assert not (tmp_path.parent / "fora.py").exists()


def test_atualizar_detecta_necessidade_de_restart(tmp_path):
    montar_root(tmp_path)
    # arquivo .py -> precisa reiniciar
    r = updater.atualizar(tmp_path,
                          baixar_json=lambda url: {"version": 2, "files": ["core/x.py"]},
                          baixar_bytes=lambda url: b"x")
    assert r["restart"] is True


def test_atualizar_so_web_nao_precisa_restart(tmp_path):
    montar_root(tmp_path)
    r = updater.atualizar(tmp_path,
                          baixar_json=lambda url: {"version": 2, "files": ["app/web/style.css"]},
                          baixar_bytes=lambda url: b"x")
    assert r["restart"] is False


def test_atualizar_sem_rawbase_erro(tmp_path):
    (tmp_path / "version.json").write_text('{"version": 1}', encoding="utf-8")
    r = updater.atualizar(tmp_path,
                          baixar_json=lambda url: {"version": 2, "files": []},
                          baixar_bytes=lambda url: b"x")
    assert r["ok"] is False
    assert "configurada" in r["error"].lower()


def test_atualizar_manifest_ausente_erro(tmp_path):
    montar_root(tmp_path)
    r = updater.atualizar(tmp_path,
                          baixar_json=lambda url: None,
                          baixar_bytes=lambda url: b"x")
    assert r["ok"] is False


def test_atualizar_continua_se_um_arquivo_falha(tmp_path):
    montar_root(tmp_path)
    manifest = {"version": 2, "files": ["core/bom.py", "core/ruim.py"]}

    def baixar(url):
        if "ruim" in url:
            raise OSError("404")
        return b"ok"

    r = updater.atualizar(tmp_path, baixar_json=lambda url: manifest, baixar_bytes=baixar)
    assert "core/bom.py" in r["updated"]
    assert "core/ruim.py" in r["failed"]
