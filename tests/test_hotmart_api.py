"""Testes do cliente da API oficial da Hotmart (HTTP mockado — sem rede)."""
import json

import pytest

from core import hotmart_api


@pytest.fixture(autouse=True)
def cache_limpo():
    hotmart_api.limpar_cache_token()
    yield
    hotmart_api.limpar_cache_token()


def _mock_http(monkeypatch, respostas):
    """respostas: lista de (status, corpo) devolvidas em ordem; grava as chamadas."""
    chamadas = []

    def fake_post(url, headers, dados=None, timeout=30):
        chamadas.append({"url": url, "headers": headers, "dados": dados})
        return respostas[min(len(chamadas) - 1, len(respostas) - 1)]

    monkeypatch.setattr(hotmart_api, "_http_post", fake_post)
    return chamadas


TOKEN_OK = (200, json.dumps({"access_token": "tok123", "expires_in": 3600}))


# ---------------------------------------------------------------------------
# obter_token
# ---------------------------------------------------------------------------
def test_token_sem_credenciais_erro():
    with pytest.raises(hotmart_api.HotmartApiError):
        hotmart_api.obter_token("", "")


def test_token_ok_e_cacheado(monkeypatch):
    chamadas = _mock_http(monkeypatch, [TOKEN_OK])
    t1 = hotmart_api.obter_token("id1", "sec1")
    t2 = hotmart_api.obter_token("id1", "sec1")   # 2a vez vem do cache
    assert t1 == t2 == "tok123"
    assert len(chamadas) == 1                     # so 1 chamada HTTP
    assert chamadas[0]["headers"]["Authorization"].startswith("Basic ")


def test_token_recusado_erro_legivel(monkeypatch):
    _mock_http(monkeypatch, [(401, '{"error":"invalid_client"}')])
    with pytest.raises(hotmart_api.HotmartApiError, match="401"):
        hotmart_api.obter_token("id1", "errada")


# ---------------------------------------------------------------------------
# criar_cupom
# ---------------------------------------------------------------------------
def test_criar_cupom_converte_pct_para_fracao(monkeypatch):
    chamadas = _mock_http(monkeypatch, [TOKEN_OK, (200, "{}")])
    hotmart_api.criar_cupom(product_id="8108732", codigo="PROMO10", desconto_pct=10,
                            client_id="id1", client_secret="sec1")
    corpo = json.loads(chamadas[1]["dados"].decode())
    assert corpo == {"code": "PROMO10", "discount": 0.10}      # 10% -> 0.10
    assert chamadas[1]["headers"]["Authorization"] == "Bearer tok123"
    assert chamadas[1]["url"].endswith("/product/8108732/coupon")


def test_criar_cupom_validacoes():
    with pytest.raises(hotmart_api.HotmartApiError, match="vazio"):
        hotmart_api.criar_cupom(product_id="1", codigo="", desconto_pct=10,
                                client_id="a", client_secret="b")
    with pytest.raises(hotmart_api.HotmartApiError, match="25 caracteres"):
        hotmart_api.criar_cupom(product_id="1", codigo="X" * 26, desconto_pct=10,
                                client_id="a", client_secret="b")
    with pytest.raises(hotmart_api.HotmartApiError, match="entre 1% e 98%"):
        hotmart_api.criar_cupom(product_id="1", codigo="OK", desconto_pct=0,
                                client_id="a", client_secret="b")
    with pytest.raises(hotmart_api.HotmartApiError, match="entre 1% e 98%"):
        hotmart_api.criar_cupom(product_id="1", codigo="OK", desconto_pct=99,
                                client_id="a", client_secret="b")


def test_criar_cupom_recusado_erro_legivel(monkeypatch):
    _mock_http(monkeypatch, [TOKEN_OK, (422, '{"error":"coupon exists"}')])
    with pytest.raises(hotmart_api.HotmartApiError, match="422"):
        hotmart_api.criar_cupom(product_id="1", codigo="PROMO10", desconto_pct=10,
                                client_id="a", client_secret="b")
