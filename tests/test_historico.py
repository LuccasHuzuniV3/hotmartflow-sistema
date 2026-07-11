"""Testes do histórico de publicações."""
import pytest

from core import historico


@pytest.fixture(autouse=True)
def arquivo_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(historico, "ARQUIVO", tmp_path / "historico.jsonl")
    return tmp_path


def test_registrar_e_listar():
    historico.registrar(rede="REDE 2", pais="Alemao", titulo="O Segredo", tipo="Principal")
    lst = historico.listar()
    assert len(lst) == 1
    assert lst[0]["rede"] == "REDE 2"
    assert lst[0]["titulo"] == "O Segredo"
    assert lst[0]["quando"]  # tem timestamp


def test_registrar_guarda_hotmart_id():
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal", hotmart_id="8099033")
    assert historico.listar()[0]["hotmart_id"] == "8099033"


def test_agrupado_por_rede_e_pais():
    historico.registrar(rede="REDE A", pais="Alemao", titulo="Principal DE", tipo="Principal")
    historico.registrar(rede="REDE A", pais="Alemao", titulo="Bump 1 DE", tipo="Order Bump")
    historico.registrar(rede="REDE A", pais="Brasil", titulo="Principal BR", tipo="Principal")
    historico.registrar(rede="REDE B", pais="Italia", titulo="Principal IT", tipo="Principal")

    arv = historico.agrupado()
    assert set(arv.keys()) == {"REDE A", "REDE B"}
    assert set(arv["REDE A"].keys()) == {"Alemao", "Brasil"}
    assert len(arv["REDE A"]["Alemao"]) == 2
    titulos = [x["titulo"] for x in arv["REDE A"]["Alemao"]]
    assert "Principal DE" in titulos and "Bump 1 DE" in titulos


def test_listar_vazio():
    assert historico.listar() == []
    assert historico.agrupado() == {}


def test_remover_tudo():
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal")
    historico.registrar(rede="R", pais="Ingles", titulo="T2", tipo="Principal")
    assert historico.remover_tudo() == 2
    assert historico.listar() == []


def test_linha_corrompida_nao_derruba():
    historico.ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    historico.ARQUIVO.write_text('{"rede":"R","pais":"Brasil","titulo":"ok","tipo":"Principal"}\nLIXO\n',
                                 encoding="utf-8")
    lst = historico.listar()
    assert len(lst) == 1 and lst[0]["titulo"] == "ok"
