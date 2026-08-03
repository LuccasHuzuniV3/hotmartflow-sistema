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


def _classificar_tipo_export(tipo: str):
    """(ordem, rótulo) do tipo pro export, ou None se não entra (Order Bump/Bônus).
    Só Principal, Upsells e Extras."""
    tl = (tipo or "").strip().lower()
    if tl == "principal":
        return (0, 0), "PRINCIPAL"
    m = re.match(r"upsell\s*(\d+)", tl)
    if m:
        return (1, int(m.group(1))), f"UPSELL {m.group(1)}"
    if tl == "upsell":
        return (1, 0), "UPSELL"
    m = re.match(r"extra\s*(\d+)", tl)
    if m:
        return (2, int(m.group(1))), f"EXTRA {m.group(1)}"
    if tl == "extra":
        return (2, 0), "EXTRA"
    return None


def montar_lista_titulos(registros: list[dict]) -> str:
    """Monta a lista de títulos JÁ PUBLICADOS (do histórico) por país, pra colar:

        ALEMÃO
        PRINCIPAL: ...
        UPSELL 1: ...
        EXTRA 1: ...
        --------------------------------------------------------
        BRASIL
        ...

    Só Principal, Upsells e Extras (Order Bumps e Bônus do principal ficam de
    fora). `registros` = histórico (historico.listar()). Agrupa por rede -> país;
    o cabeçalho da rede só aparece se houver mais de uma. Dedupe por rede+país+
    tipo: vence o mais recente (última linha do histórico). País vazio sai com o
    rótulo em branco.
    """
    from core import idiomas as _idiomas

    # rede -> pais -> {ordem: (rotulo, titulo)}  (dedupe: última linha vence)
    redes: dict[str, dict] = {}
    for r in registros:
        cls = _classificar_tipo_export(r.get("tipo"))
        if not cls:
            continue
        ordem, rotulo = cls
        rede = r.get("rede", "")
        pais = r.get("pais", "")
        titulo = (r.get("titulo") or "").strip()
        redes.setdefault(rede, {}).setdefault(pais, {})[ordem] = (rotulo, titulo)

    def _ord_pais(nome: str) -> int:
        info = _idiomas.por_pais(nome)
        return _idiomas.ordem(info["codigo"]) if info else len(_idiomas.IDIOMAS)

    sep = "-" * 56
    multi = len(redes) > 1
    partes = []
    for rede in sorted(redes):
        if multi:
            partes.append(f"===== {rede.upper()} =====")
        blocos = []
        for pais in sorted(redes[rede], key=_ord_pais):
            itens = redes[rede][pais]
            linhas = [pais.upper()]
            for ordem in sorted(itens):
                rotulo, titulo = itens[ordem]
                linhas.append(f"{rotulo}: {titulo}")
            blocos.append("\n".join(linhas))
        partes.append(("\n" + sep + "\n").join(blocos))
    return "\n\n".join(partes)


def numero_do_produto(titulo_arquivo: str) -> int | None:
    """Extrai o numero do produto do titulo vindo do nome do arquivo.

    'ORDER BUMP 7 - REDE 1...' -> 7 | 'OPSELL 2 - ...' -> 2 | 'PRINCIPAL...' -> None
    """
    m = _RE_NUMERO_PRODUTO.match((titulo_arquivo or "").strip())
    return int(m.group(1)) if m else None
