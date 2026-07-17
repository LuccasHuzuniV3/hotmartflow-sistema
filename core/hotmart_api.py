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
# A API de cupom da Hotmart tem rotas em DOIS dominios (/payments e /products) e
# ambos ja apresentaram comportamento errado (400 num, 200-fantasma que nao cria
# nada no outro). Por isso o criar_cupom tenta um, VERIFICA por GET se o cupom
# realmente existe, e se nao existir tenta o outro dominio — sucesso so quando o
# cupom aparece de verdade na lista do produto.
URL_PAGAMENTOS = "https://developers.hotmart.com/payments/api/v1"
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


def _http_get(url: str, headers: dict, timeout: float = 30) -> tuple[int, str]:
    """GET simples com urllib — mesmo contrato do _http_post."""
    req = urllib.request.Request(url, headers=headers, method="GET")
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


def listar_cupons(product_id: str, client_id: str, client_secret: str) -> list[dict]:
    """Lista os cupons do produto (GET /coupon/product/{id}) — usado pra VERIFICAR
    que o cupom criado existe de verdade. Tenta os dois domínios; devolve a
    primeira lista não-vazia (ou vazia se nenhum tiver)."""
    token = obter_token(client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}
    itens: list[dict] = []
    for base in (URL_PRODUTOS, URL_PAGAMENTOS):
        try:
            status, resp = _http_get(f"{base}/coupon/product/{product_id}", headers)
        except Exception:
            continue
        if status != 200 or not (resp or "").strip():
            continue  # 200 com corpo vazio = bug conhecido da API; tenta o outro
        try:
            dados = json.loads(resp)
        except json.JSONDecodeError:
            continue
        achados = dados.get("items") or dados.get("lista") or []
        if isinstance(achados, list) and achados:
            return achados
    return itens


def _cupom_existe(product_id: str, codigo: str, client_id: str,
                  client_secret: str, tentativas: int = 1) -> bool:
    """Confere se o cupom aparece na lista do produto (case-insensitive).
    Com tentativas=2 espera 2s entre elas — o cupom recém-criado pode demorar."""
    alvo = codigo.strip().lower()
    for tentativa in range(max(1, tentativas)):
        for c in listar_cupons(product_id, client_id, client_secret):
            code = str(c.get("code") or c.get("coupon_code") or "").strip().lower()
            if code == alvo:
                return True
        if tentativa < tentativas - 1:
            time.sleep(2)
    return False


def criar_cupom(*, product_id: str, codigo: str, desconto_pct: float,
                client_id: str, client_secret: str) -> dict:
    """Cria um cupom no produto e SÓ retorna sucesso depois de VERIFICAR (por
    GET) que ele existe de verdade — a API da Hotmart tem rota que responde 200
    sem criar nada (sucesso fantasma). Tenta /payments e depois /products.

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

    # já existe? (retentativa da fila de pendentes depois de um sucesso parcial)
    if _cupom_existe(product_id, codigo, client_id, client_secret):
        return {"verificado": True, "ja_existia": True}

    token = obter_token(client_id, client_secret)
    corpo = json.dumps({"code": codigo, "discount": desconto}).encode("utf-8")
    respostas = []
    for base in (URL_PAGAMENTOS, URL_PRODUTOS):
        url = f"{base}/product/{product_id}/coupon"
        try:
            status, resp = _http_post(url, {"Authorization": f"Bearer {token}",
                                            "Content-Type": "application/json"}, corpo)
        except Exception as e:
            respostas.append(f"{base.split('/')[3]}: erro de rede ({e})")
            continue
        respostas.append(f"{base.split('/')[3]}: HTTP {status} {resp[:120]}")
        if status in (200, 201):
            # nao confia no 200 — confere se o cupom REALMENTE existe
            if _cupom_existe(product_id, codigo, client_id, client_secret, tentativas=2):
                return {"verificado": True, "via": base}
    raise HotmartApiError(
        f"Cupom NÃO foi criado (nenhuma rota confirmou) — enviado: code='{codigo}', "
        f"discount={desconto} (={desconto_pct:g}%), produto={product_id}. "
        f"Tentativas: {' | '.join(respostas)}"
    )


def limpar_cache_token() -> None:
    """Zera o cache do token (usado nos testes / troca de credenciais)."""
    _cache_token.update({"token": "", "expira_em": 0.0, "chave": ""})
