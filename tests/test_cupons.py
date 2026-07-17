"""Testes da fila de cupons pendentes (Hotmart recusou na hora -> retenta depois)."""
import pytest

from core import cupons, hotmart_api


@pytest.fixture(autouse=True)
def arquivo_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(cupons, "ARQUIVO", tmp_path / "cupons_pendentes.jsonl")


def test_registrar_listar_remover():
    cupons.registrar(product_id="111", codigo="25OFF", desconto_pct=25,
                     titulo="Ebook X", pais="Brasil", erro="HTTP 400")
    cupons.registrar(product_id="222", codigo="25OFF", desconto_pct=25)
    assert len(cupons.listar()) == 2
    cupons.remover("111")
    restam = cupons.listar()
    assert len(restam) == 1 and restam[0]["product_id"] == "222"


def test_registrar_mesmo_produto_atualiza_sem_duplicar():
    cupons.registrar(product_id="111", codigo="25OFF", desconto_pct=25, erro="erro 1")
    cupons.registrar(product_id="111", codigo="30OFF", desconto_pct=30, erro="erro 2")
    regs = cupons.listar()
    assert len(regs) == 1
    assert regs[0]["codigo"] == "30OFF" and regs[0]["erro"] == "erro 2"


def test_tentar_todos_sucesso_sai_da_fila_falha_fica(monkeypatch):
    cupons.registrar(product_id="111", codigo="25OFF", desconto_pct=25)
    cupons.registrar(product_id="222", codigo="25OFF", desconto_pct=25)

    def fake_criar(**kw):
        if kw["product_id"] == "222":
            raise hotmart_api.HotmartApiError("HTTP 400: em análise")
        return {}

    monkeypatch.setattr(cupons.hotmart_api, "criar_cupom", fake_criar)
    r = cupons.tentar_todos("id", "sec")
    assert [c["product_id"] for c in r["criados"]] == ["111"]
    assert [f["product_id"] for f in r["falhas"]] == ["222"]
    # o que criou saiu; o que falhou continua na fila com o erro atualizado
    restam = cupons.listar()
    assert len(restam) == 1
    assert restam[0]["product_id"] == "222"
    assert "em análise" in restam[0]["erro"]


def test_tentar_todos_fila_vazia_nao_chama_api(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cupons.hotmart_api, "criar_cupom",
                        lambda **kw: chamadas.append(kw))
    r = cupons.tentar_todos("id", "sec")
    assert r == {"criados": [], "falhas": []}
    assert chamadas == []
