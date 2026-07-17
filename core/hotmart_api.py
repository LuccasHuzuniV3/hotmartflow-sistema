"""Cliente mínimo da API oficial da Hotmart (developers.hotmart.com).

Hoje é usado pra criar o CUPOM de desconto no ebook Principal recém-publicado.
Autenticação OAuth2 client_credentials: client_id + client_secret, colados na
aba Config > API da Hotmart (se criam em developers.hotmart.com > Credenciais).
O access_token vale horas — fica cacheado em memória e renova quando vence.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

URL_TOKEN = "https://api-sec-vlc.hotmart.com/security/oauth/token"
URL_PRODUTOS = "https://developers.hotmart.com/products/api/v1"

_cache_token = {"token": "", "expira_em": 0.0, "chave": ""}


class HotmartApiError(Exception):
    pass


def _http_post(url: str, headers: dict, dados: bytes | None = None,
               timeout: float = 30) -> tuple[int, str]:
    """POST simples com urllib. Retorna (status, corpo) — HTTPError não estoura,
    vira (status_de_erro, corpo) pra tratarmos a mensagem da Hotmart."""
    req = urllib.request.Request(url, data=dados, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            corpo = e.read().decode("utf-8", "replace")
        except Exception:
            corpo = ""
        return e.code, corpo


def obter_token(client_id: str, client_secret: str) -> str:
    """Autentica (client_credentials) e retorna o access_token — com cache."""
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        raise HotmartApiError(
            "Credenciais da API não configuradas — cole o client_id e o "
            "client_secret na aba Config (se criam em developers.hotmart.com)."
        )
    chave = f"{client_id}:{client_secret}"
    if (_cache_token["token"] and _cache_token["chave"] == chave
            and time.time() < _cache_token["expira_em"]):
        return _cache_token["token"]

    basic = base64.b64encode(chave.encode()).decode()
    url = (f"{URL_TOKEN}?grant_type=client_credentials"
           f"&client_id={client_id}&client_secret={client_secret}")
    try:
        status, corpo = _http_post(url, {"Authorization": f"Basic {basic}",
                                         "Content-Type": "application/json"})
    except Exception as e:  # rede fora, DNS, timeout...
        raise HotmartApiError(
            f"Não consegui falar com o servidor de autenticação "
            f"(api-sec-vlc.hotmart.com): {e}") from e

    try:
        dados = json.loads(corpo or "{}")
    except json.JSONDecodeError:
        dados = {}
    token = str(dados.get("access_token") or "")
    if status != 200 or not token:
        raise HotmartApiError(
            f"Autenticação recusada pela Hotmart (HTTP {status}) — "
            "confira o client_id/client_secret na Config."
        )
    _cache_token.update({
        "token": token,
        "chave": chave,
        "expira_em": time.time() + float(dados.get("expires_in", 3600)) - 60,
    })
    return token


def criar_cupom(*, product_id: str, codigo: str, desconto_pct: float,
                client_id: str, client_secret: str) -> dict:
    """Cria um cupom no produto (POST /product/{id}/coupon).

    desconto_pct em PORCENTO (ex.: 10 = 10%) — a API espera fração (0.10).
    Levanta HotmartApiError com mensagem legível em qualquer falha.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        raise HotmartApiError("Código do cupom vazio — preencha na Config > Cupom.")
    if len(codigo) > 25:
        raise HotmartApiError("Código do cupom passa de 25 caracteres (limite da Hotmart).")
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", codigo):
        raise HotmartApiError(
            f"Código do cupom '{codigo}' tem caractere inválido — use só letras e "
            "números, sem espaço nem acento (ex.: PROMO10)."
        )
    desconto = round(float(desconto_pct) / 100.0, 4)
    if not (0 < desconto < 0.99):
        raise HotmartApiError("Desconto do cupom precisa estar entre 1% e 98%.")
    if not str(product_id).strip():
        raise HotmartApiError("Sem o ID do produto na Hotmart — não dá pra criar o cupom.")

    token = obter_token(client_id, client_secret)
    corpo = json.dumps({"code": codigo, "discount": desconto}).encode("utf-8")
    url = f"{URL_PRODUTOS}/product/{product_id}/coupon"
    try:
        status, resp = _http_post(url, {"Authorization": f"Bearer {token}",
                                        "Content-Type": "application/json"}, corpo)
    except Exception as e:
        raise HotmartApiError(
            f"Não consegui falar com a API de produtos "
            f"(developers.hotmart.com): {e}") from e

    if status not in (200, 201):
        raise HotmartApiError(
            f"Hotmart recusou o cupom (HTTP {status}) — enviado: code='{codigo}', "
            f"discount={desconto} (={desconto_pct:g}%), produto={product_id}. "
            f"Resposta: {resp[:200]}"
        )
    try:
        return json.loads(resp or "{}")
    except json.JSONDecodeError:
        return {}


def limpar_cache_token() -> None:
    """Zera o cache do token (usado nos testes / troca de credenciais)."""
    _cache_token.update({"token": "", "expira_em": 0.0, "chave": ""})
