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


def montar_lista_titulos(lista_produtos: list[dict]) -> str:
    """Monta a lista de títulos TRADUZIDOS agrupada por país, pra colar/conferir:

        ALEMÃO
        PRINCIPAL: ...
        ORDER BUMP 1: ...
        UPSELL 1: ...
        BONUS 1: ...
        EXTRA 1: ...
        --------------------------------------------------------
        BRASIL
        ...

    Junta todos os produtos da fila. Ordem dentro do país: Principal, Order
    Bumps, Upsells, Bônus (do principal), Extras (dos upsells). Países na ordem
    canônica dos idiomas. Título vazio (ainda não traduzido) sai em branco.
    """
    from core import idiomas as _idiomas

    # codigo -> {"pais": str, "itens": [(ordem, rotulo, titulo)]}
    paises: dict[str, dict] = {}

    def _add(codigo, pais, ordem, rotulo, titulo):
        p = paises.setdefault(codigo, {"pais": pais, "itens": []})
        p["itens"].append((ordem, rotulo, (titulo or "").strip()))

    for prod in lista_produtos:
        tipo = prod.get("tipo")
        numero = prod.get("numero") or 0
        for item in prod.get("idiomas", []):
            cod = item.get("codigo", "")
            pais = item.get("pais", "")
            tit = item.get("titulo", "")
            if tipo == "Principal":
                _add(cod, pais, (0, 0), "PRINCIPAL", tit)
                for a in item.get("anexos", []):
                    if a.get("papel") == "bonus":
                        num = a.get("numero") or 0
                        _add(cod, pais, (3, num), f"BONUS {num}", a.get("titulo"))
            elif tipo == "Order Bump":
                _add(cod, pais, (1, numero), f"ORDER BUMP {numero}", tit)
            elif tipo == "Upsell":
                _add(cod, pais, (2, numero), f"UPSELL {numero}", tit)
                for a in item.get("anexos", []):
                    if a.get("papel") == "extra":
                        num = a.get("numero") or 0
                        _add(cod, pais, (4, num), f"EXTRA {num}", a.get("titulo"))

    sep = "-" * 56
    blocos = []
    for cod in sorted(paises, key=_idiomas.ordem):
        info = paises[cod]
        linhas = [info["pais"].upper()]
        for _ordem, rotulo, titulo in sorted(info["itens"], key=lambda x: x[0]):
            linhas.append(f"{rotulo}: {titulo}")
        blocos.append("\n".join(linhas))
    return ("\n" + sep + "\n").join(blocos)


def numero_do_produto(titulo_arquivo: str) -> int | None:
    """Extrai o numero do produto do titulo vindo do nome do arquivo.

    'ORDER BUMP 7 - REDE 1...' -> 7 | 'OPSELL 2 - ...' -> 2 | 'PRINCIPAL...' -> None
    """
    m = _RE_NUMERO_PRODUTO.match((titulo_arquivo or "").strip())
    return int(m.group(1)) if m else None
