"""Scanner da pasta de produto.

Convencao de nome:

    Titulo do Ebook - Pais.pdf            -> formato padrao (tipo detectado pelo titulo)
    Titulo do Ebook - Tipo - Pais.pdf     -> tipo explicito no slot (Order Bump, Upsell...)
    Titulo do Ebook - Pais.jpg            -> capa (nome igual OU comeco do nome do PDF)

TIPO pelo comeco do titulo (padrao real da operacao):
    PRINCIPAL...    -> produto Principal
    ORDER BUMP n... -> produto Order Bump
    OPSELL n... / UPSELL n... -> produto Upsell (n identifica o opsell)

ANEXOS (nao viram produto — sobem JUNTO com o produto dono, no mesmo pais):
    BONUS n...        -> anexo do Principal (PDF no conteudo + imagem nas infos basicas)
    EXTRA x OP y...   -> anexo do OPSELL y  (mesma logica)
    Titulo - Bonus - Pais.pdf (slot antigo) -> tambem vira anexo do Principal
"""
from __future__ import annotations

import re
from pathlib import Path

from core import idiomas

SEPARADOR = " - "
EXTENSOES_IMAGEM = (".jpg", ".jpeg", ".png", ".webp")
TIPOS_PADRAO = ["Principal", "Order Bump", "Upsell", "Bonus"]
TIPO_IMPLICITO = "Principal"
SUBPASTA_CAPAS = "capas"

_RE_EXTRA = re.compile(r"^extra\b.*?\bop\s*(\d+)")
_RE_OPSELL = re.compile(r"^(?:opsell|upsell)\s*(\d+)?")


class ScannerError(Exception):
    pass


def _classificar(titulo: str, tipo_slot: str | None) -> tuple[str, object]:
    """Decide o papel do PDF: ('produto', (tipo, num_opsell)) ou ('anexo', destino).

    destino: ('principal', None) ou ('opsell', numero).
    """
    if tipo_slot == "Bonus":
        return "anexo", ("principal", None)
    if tipo_slot is not None:
        return "produto", (tipo_slot, None)

    t = idiomas.normalizar(titulo)
    if t.startswith("bonus"):
        return "anexo", ("principal", None)
    m = _RE_EXTRA.match(t)
    if m:
        return "anexo", ("opsell", int(m.group(1)))
    if t.startswith("principal"):
        return "produto", ("Principal", None)
    if t.startswith("order bump"):
        return "produto", ("Order Bump", None)
    m = _RE_OPSELL.match(t)
    if m and (t.startswith("opsell") or t.startswith("upsell")):
        num = int(m.group(1)) if m.group(1) else None
        return "produto", ("Upsell", num)
    return "produto", (TIPO_IMPLICITO, None)


def analisar_pasta(pasta: str | Path, tipos: list[str] | None = None) -> dict:
    """Varre a pasta, agrupa PDFs por (titulo, tipo) e vincula anexos.

    Retorna:
        {
          "grupos": [{"titulo", "tipo", "idiomas": [
              {"codigo","pais","pdf","capa","anexos":[{"nome","pdf","capa"}]}]}],
          "ignorados": [{"arquivo", "motivo"}],
        }
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ScannerError(f"Pasta nao encontrada: {pasta}")

    tipos_slot = {idiomas.normalizar(t): t for t in (tipos or TIPOS_PADRAO)}
    ignorados: list[dict] = []
    registros: list[dict] = []

    # ---- fase 1: parse de todos os PDFs -----------------------------------
    for arq in sorted(pasta.iterdir()):
        if not arq.is_file() or arq.suffix.lower() != ".pdf":
            continue  # imagens sao capas; outros arquivos nao interessam

        partes = arq.stem.split(SEPARADOR)
        if len(partes) < 2:
            ignorados.append({"arquivo": arq.name,
                              "motivo": "Nome fora da convencao 'Titulo - Pais.pdf'"})
            continue

        info_idioma = idiomas.por_pais(partes[-1].strip())
        if info_idioma is None:
            ignorados.append({"arquivo": arq.name,
                              "motivo": f"Pais desconhecido: '{partes[-1].strip()}'"})
            continue

        tipo_slot = None
        if len(partes) >= 3:
            tipo_slot = tipos_slot.get(idiomas.normalizar(partes[-2].strip()))
        if tipo_slot is not None:
            titulo = SEPARADOR.join(partes[:-2]).strip()
        else:
            titulo = SEPARADOR.join(partes[:-1]).strip()

        papel, dado = _classificar(titulo, tipo_slot)
        registros.append({
            "arquivo": arq, "titulo": titulo, "papel": papel, "dado": dado,
            "codigo": info_idioma["codigo"], "pais": info_idioma["pais"],
        })

    lista_grupos = _montar_grupos(registros, ignorados)
    return {"grupos": lista_grupos, "ignorados": ignorados}


def _montar_grupos(registros: list[dict], ignorados: list[dict]) -> list[dict]:
    """Fases 2 e 3 (compartilhadas por analisar_pasta e analisar_rede): cria os
    produtos agrupando por (titulo, tipo), vincula os anexos (bonus/extra) ao
    dono do MESMO idioma, casa capas e ordena. A capa e buscada na PASTA DO
    PROPRIO ARQUIVO (arq.parent) — funciona pra pasta unica ou por-pais."""
    grupos: dict[tuple[str, str], dict] = {}
    principais: dict[str, list[dict]] = {}
    opsells: dict[tuple[int, str], dict] = {}

    for reg in registros:
        if reg["papel"] != "produto":
            continue
        tipo, num_opsell = reg["dado"]
        chave = (reg["titulo"], tipo)
        if chave not in grupos:
            from core import titulos as _titulos
            numero = num_opsell if num_opsell is not None else _titulos.numero_do_produto(reg["titulo"])
            grupos[chave] = {"titulo": reg["titulo"], "tipo": tipo,
                             "numero": numero, "idiomas": []}
        item = {
            "codigo": reg["codigo"],
            "pais": reg["pais"],
            "pdf": str(reg["arquivo"]),
            "capa": achar_capa(reg["arquivo"].parent, reg["arquivo"].stem),
            "anexos": [],
        }
        grupos[chave]["idiomas"].append(item)
        if tipo == "Principal":
            principais.setdefault(reg["codigo"], []).append(item)
        if tipo == "Upsell" and num_opsell is not None:
            opsells[(num_opsell, reg["codigo"])] = item

    for reg in registros:
        if reg["papel"] != "anexo":
            continue
        destino, num = reg["dado"]
        anexo = {
            "nome": reg["titulo"],
            "pdf": str(reg["arquivo"]),
            "capa": achar_capa(reg["arquivo"].parent, reg["arquivo"].stem),
        }
        if destino == "principal":
            candidatos = principais.get(reg["codigo"], [])
            if len(candidatos) == 1:
                candidatos[0]["anexos"].append(anexo)
            elif not candidatos:
                ignorados.append({"arquivo": reg["arquivo"].name,
                                  "motivo": f"Bônus sem produto Principal em {reg['pais']}"})
            else:
                ignorados.append({"arquivo": reg["arquivo"].name,
                                  "motivo": f"Vários Principais em {reg['pais']} — vincule a capa/bônus manualmente"})
        else:  # opsell
            item = opsells.get((num, reg["codigo"]))
            if item is not None:
                item["anexos"].append(anexo)
            else:
                ignorados.append({"arquivo": reg["arquivo"].name,
                                  "motivo": f"Extra do OPSELL {num} mas não existe OPSELL {num} em {reg['pais']}"})

    ordem_tipos = {"principal": 0, "order bump": 1, "upsell": 2}
    lista_grupos = sorted(
        grupos.values(),
        key=lambda g: (ordem_tipos.get(idiomas.normalizar(g["tipo"]), 9), g["titulo"].lower()),
    )
    for g in lista_grupos:
        g["idiomas"].sort(key=lambda i: idiomas.ordem(i["codigo"]))
        for item in g["idiomas"]:
            item["anexos"].sort(key=lambda a: a["nome"].lower())
    return lista_grupos


# Subpastas da rede que NUNCA sao paises (ignoradas no analisar_rede)
IGNORAR_PASTAS = ("zpag checkout",)


def analisar_auto(pasta: str | Path, tipos: list[str] | None = None) -> dict:
    """Detecta sozinho o formato e chama o scanner certo:
      - Tem PDF direto na pasta -> pasta única ('Título - Tipo - País.pdf').
      - Não tem PDF mas tem subpastas de país (ALEMANHA/, BRASIL/...) -> REDE.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ScannerError(f"Pasta nao encontrada: {pasta}")
    tem_pdf = any(a.is_file() and a.suffix.lower() == ".pdf" for a in pasta.iterdir())
    if tem_pdf:
        return analisar_pasta(pasta, tipos=tipos)
    tem_pais = any(
        s.is_dir() and idiomas.normalizar(s.name) not in IGNORAR_PASTAS
        and idiomas.por_pais(s.name) is not None
        for s in pasta.iterdir()
    )
    if tem_pais:
        return analisar_rede(pasta, tipos=tipos)
    return analisar_pasta(pasta, tipos=tipos)  # fallback (dará "nada encontrado")


def analisar_rede(pasta_rede: str | Path, tipos: list[str] | None = None) -> dict:
    """Varre uma pasta de REDE com SUBPASTAS por país (ALEMANHA/, BRASIL/, ...).

    O país vem do NOME DA PASTA (não do nome do arquivo). Dentro de cada pasta,
    os PDFs seguem o padrão de sempre (PRINCIPAL..., ORDER BUMP n..., OPSELL n...,
    BONUS n..., EXTRA x OP y...) e as capas são JPEGs com o começo do nome.
    A pasta 'ZPAG CHECKOUT' é ignorada.

    Retorna: {"grupos", "ignorados", "paises": [{"pasta","codigo"}]}.
    """
    pasta_rede = Path(pasta_rede)
    if not pasta_rede.is_dir():
        raise ScannerError(f"Pasta nao encontrada: {pasta_rede}")

    ignorados: list[dict] = []
    registros: list[dict] = []
    paises: list[dict] = []

    for sub in sorted(pasta_rede.iterdir()):
        if not sub.is_dir():
            continue
        if idiomas.normalizar(sub.name) in IGNORAR_PASTAS:
            continue  # ex.: ZPAG CHECKOUT
        info = idiomas.por_pais(sub.name)
        if info is None:
            ignorados.append({"arquivo": sub.name,
                              "motivo": f"Pasta de país desconhecido: '{sub.name}'"})
            continue
        paises.append({"pasta": sub.name, "codigo": info["codigo"]})
        for arq in sorted(sub.iterdir()):
            if not arq.is_file() or arq.suffix.lower() != ".pdf":
                continue
            titulo = arq.stem.strip()  # o nome inteiro e o titulo (pais = a pasta)
            papel, dado = _classificar(titulo, None)
            registros.append({
                "arquivo": arq, "titulo": titulo, "papel": papel, "dado": dado,
                "codigo": info["codigo"], "pais": info["pais"],
            })

    lista_grupos = _montar_grupos(registros, ignorados)
    return {"grupos": lista_grupos, "ignorados": ignorados, "paises": paises}


def achar_capa(pasta: Path, stem: str) -> str | None:
    """Procura a capa de um PDF — na pasta e na subpasta capas/.

    Ordem de match:
      1. EXATO: imagem com o mesmo nome do PDF ('X - Brasil.pdf' -> 'X - Brasil.jpg').
      2. PREFIXO: imagem cujo nome e o COMECO do nome do PDF — padrao real da
         operacao ('BONUS 1.jpeg' pra 'BONUS 1 REDE 1 SIGNO... - Brasil.pdf').
         O caractere seguinte ao prefixo nao pode ser letra/numero (senao
         'BONUS 1' casaria com 'BONUS 10'). Vence o prefixo mais longo.
    """
    locais = [pasta, pasta / SUBPASTA_CAPAS]

    # 1) match exato
    for local in locais:
        for ext in EXTENSOES_IMAGEM:
            candidato = local / f"{stem}{ext}"
            if candidato.is_file():
                return str(candidato)

    # 2) match por prefixo
    stem_norm = idiomas.normalizar(stem)
    melhor: tuple[int, str] | None = None
    for local in locais:
        if not local.is_dir():
            continue
        for img in local.iterdir():
            if not img.is_file() or img.suffix.lower() not in EXTENSOES_IMAGEM:
                continue
            prefixo = idiomas.normalizar(img.stem)
            if len(prefixo) < 3 or not stem_norm.startswith(prefixo):
                continue
            resto = stem_norm[len(prefixo):]
            if resto and resto[0].isalnum():
                continue  # 'bonus 1' nao pode casar com 'bonus 10...'
            if melhor is None or len(prefixo) > melhor[0]:
                melhor = (len(prefixo), str(img))
    return melhor[1] if melhor else None
