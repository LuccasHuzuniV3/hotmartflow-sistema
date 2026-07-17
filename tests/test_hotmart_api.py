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
# criar_cupom — só é sucesso quando o cupom EXISTE de verdade (verificado por GET)
# ---------------------------------------------------------------------------
def _mock_existe(monkeypatch, sequencia):
    """Substitui _cupom_existe pela sequência dada (pre-check, pós-POST 1, ...)."""
    it = iter(sequencia)
    monkeypatch.setattr(hotmart_api, "_cupom_existe", lambda *a, **k: next(it))


def test_criar_cupom_converte_pct_e_verifica(monkeypatch):
    chamadas = _mock_http(monkeypatch, [TOKEN_OK, (200, "{}")])
    _mock_existe(monkeypatch, [False, True])  # pre-check: nao existe; pós-POST: existe
    r = hotmart_api.criar_cupom(product_id="8108732", codigo="PROMO10", desconto_pct=10,
                                client_id="id1", client_secret="sec1")
    assert r["verificado"] is True
    corpo = json.loads(chamadas[1]["dados"].decode())
    assert corpo == {"code": "PROMO10", "discount": 0.10}      # 10% -> 0.10
    assert chamadas[1]["headers"]["Authorization"] == "Bearer tok123"
    assert chamadas[1]["url"].endswith("/product/8108732/coupon")
    assert "/payments/" in chamadas[1]["url"]   # tenta payments primeiro


def test_criar_cupom_200_fantasma_cai_pro_outro_dominio(monkeypatch):
    # payments responde 200 mas NAO cria (fantasma) -> tenta products e confirma
    chamadas = _mock_http(monkeypatch, [TOKEN_OK, (200, "{}"), (200, "{}")])
    _mock_existe(monkeypatch, [False, False, True])
    r = hotmart_api.criar_cupom(product_id="8142700", codigo="25OFF", desconto_pct=25,
                                client_id="id1", client_secret="sec1")
    assert r["verificado"] is True
    assert "/payments/" in chamadas[1]["url"]
    assert "/products/" in chamadas[2]["url"]


def test_criar_cupom_nenhuma_rota_confirma_levanta_erro(monkeypatch):
    _mock_http(monkeypatch, [TOKEN_OK, (200, "{}"), (400, '{"error":"x"}')])
    _mock_existe(monkeypatch, [False, False, False, False])
    with pytest.raises(hotmart_api.HotmartApiError, match="NÃO foi criado"):
        hotmart_api.criar_cupom(product_id="1", codigo="PROMO10", desconto_pct=10,
                                client_id="a", client_secret="b")


def test_criar_cupom_ja_existente_nao_reposta(monkeypatch):
    chamadas = _mock_http(monkeypatch, [TOKEN_OK])
    _mock_existe(monkeypatch, [True])   # pre-check: ja existe
    r = hotmart_api.criar_cupom(product_id="1", codigo="PROMO10", desconto_pct=10,
                                client_id="a", client_secret="b")
    assert r["ja_existia"] is True
    assert chamadas == []   # nenhum POST — nao duplica cupom


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


# ---------------------------------------------------------------------------
# listar_cupons / _cupom_existe
# ---------------------------------------------------------------------------
def test_listar_cupons_pula_corpo_vazio_e_tenta_outro_dominio(monkeypatch):
    _mock_http(monkeypatch, [TOKEN_OK])  # token
    gets = [(200, ""),  # bug conhecido: 200 com corpo vazio -> pula
            (200, '{"items":[{"code":"25OFF","discount":0.25}]}')]
    monkeypatch.setattr(hotmart_api, "_http_get",
                        lambda url, h, timeout=30: gets.pop(0))
    itens = hotmart_api.listar_cupons("8142700", "id1", "sec1")
    assert itens and itens[0]["code"] == "25OFF"


def test_cupom_existe_compara_sem_case(monkeypatch):
    monkeypatch.setattr(hotmart_api, "listar_cupons",
                        lambda *a, **k: [{"code": "25off"}])
    assert hotmart_api._cupom_existe("1", "25OFF", "id", "sec") is True


def test_cupom_existe_nao_acha_retorna_false(monkeypatch):
    monkeypatch.setattr(hotmart_api, "listar_cupons", lambda *a, **k: [])
    monkeypatch.setattr(hotmart_api.time, "sleep", lambda s: None)
    assert hotmart_api._cupom_existe("1", "X", "id", "sec", tentativas=2) is False
