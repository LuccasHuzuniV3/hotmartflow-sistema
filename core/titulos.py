"""Parser da lista de titulos em portugues (colada do Discord).

Formato real da operacao (separador ';', ':' ou '-', numeracao livre):

    rede 4 lucas signo GEMEOS                <- header, ignorado
    EBOOK PRINCIPAL ; O GRANDE SEGREDO...    <- titulo do Principal
    BONUS 1 ; ...                            <- ignorado (anexo nao tem titulo no cadastro)
    ORDEM BUMP 1; ...                        <- titulo do Order Bump 1
    ----                                     <- separador, ignorado
    OPSELL 1 ;  ... ! -                      <- titulo do Upsell 1 (limpa o '-' do fim)
"""
from __future__ import annotations

import re

_RE_LINHA = re.compile(
    r"^\s*(?P<rotulo>ebook\s+principal|principal|ordem\s+bump|order\s+bump|opsell|upsell|bonus|extra)"
    r"\s*(?P<numero>\d+)?\s*[;:\-–—]\s*(?P<titulo>.+?)\s*$",
    re.IGNORECASE,
)

_RE_NUMERO_PRODUTO = re.compile(r"^(?:order\s+bump|ordem\s+bump|opsell|upsell)\s*(\d+)", re.IGNORECASE)


def _limpar_titulo(titulo: str) -> str:
    """Apara espacos e tracos soltos no fim ('...GÊMEOS! -' -> '...GÊMEOS!')."""
    return re.sub(r"[\s\-–—]+$", "", titulo.strip())


def parse_titulos(texto: str) -> dict:
    """Extrai os titulos de produto do texto colado.

    Retorna:
        {"principal": str|None, "bumps": {n: titulo}, "upsells": {n: titulo},
         "bonus": {n: titulo}, "extras": {n: titulo},
         "ignoradas": [{"linha", "motivo"}]}
    """
    resultado = {"principal": None, "bumps": {}, "upsells": {},
                 "bonus": {}, "extras": {}, "ignoradas": []}

    for linha in (texto or "").splitlines():
        bruta = linha.strip()
        if not bruta or set(bruta) <= set("-–—_= "):
            continue  # vazia ou separador visual

        m = _RE_LINHA.match(bruta)
        if not m:
            resultado["ignoradas"].append({"linha": bruta, "motivo": "linha não reconhecida"})
            continue

        rotulo = re.sub(r"\s+", " ", m.group("rotulo").lower())
        numero = int(m.group("numero")) if m.group("numero") else None
        titulo = _limpar_titulo(m.group("titulo"))

        if rotulo in ("ebook principal", "principal"):
            resultado["principal"] = titulo
        elif rotulo in ("ordem bump", "order bump"):
            if numero is None:
                resultado["ignoradas"].append({"linha": bruta, "motivo": "order bump sem número"})
            else:
                resultado["bumps"][numero] = titulo
        elif rotulo in ("opsell", "upsell"):
            if numero is None:
                resultado["ignoradas"].append({"linha": bruta, "motivo": "opsell sem número"})
            else:
                resultado["upsells"][numero] = titulo
        elif rotulo == "bonus":
            if numero is None:
                resultado["ignoradas"].append({"linha": bruta, "motivo": "bônus sem número"})
            else:
                resultado["bonus"][numero] = titulo
        else:  # extra
            if numero is None:
                resultado["ignoradas"].append({"linha": bruta, "motivo": "extra sem número"})
            else:
                resultado["extras"][numero] = titulo

    return resultado


def numero_do_produto(titulo_arquivo: str) -> int | None:
    """Extrai o numero do produto do titulo vindo do nome do arquivo.

    'ORDER BUMP 7 - REDE 1...' -> 7 | 'OPSELL 2 - ...' -> 2 | 'PRINCIPAL...' -> None
    """
    m = _RE_NUMERO_PRODUTO.match((titulo_arquivo or "").strip())
    return int(m.group(1)) if m else None
