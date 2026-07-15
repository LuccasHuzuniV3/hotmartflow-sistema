"""Repositorio de produtos — a fila de publicacao, persistida em JSON (1 arquivo por produto).

Um "produto" = 1 ebook x 1 tipo (Principal/Order Bump/...), com N idiomas.
Cada idioma vira um cadastro na Hotmart e caminha pelo ciclo de status:

    rascunho -> textos_gerados -> revisado -> publicando -> publicado | erro
"""
from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PRODUTOS = RAIZ / "data" / "produtos"

# Serializa todo acesso leitura-modificacao-gravacao aos JSONs. Necessario:
# traducoes paralelas e "revisar todos" disparam PATCHes simultaneos no MESMO
# produto (threads do FastAPI) — sem trava, os.replace colide (WinError 32)
# e updates se perdem.
_TRAVA = threading.Lock()

STATUS_VALIDOS = ("rascunho", "textos_gerados", "revisado", "publicando", "publicado", "erro")

# Campos editaveis via API (tudo que NAO esta aqui e gerenciado internamente)
CAMPOS_PRODUTO = {"titulo_pt", "descricao_pt"}
CAMPOS_ITEM = {"titulo", "descricao", "preco", "status", "capa", "erro"}


class ProdutoError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slug(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    limpo = re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")
    return limpo[:40] or "produto"


def _novo_id(titulo: str, tipo: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{_slug(titulo)}_{_slug(tipo)}_{uuid.uuid4().hex[:6]}"


def _caminho(produto_id: str) -> Path:
    # sanitiza pra impedir path traversal via id
    seguro = re.sub(r"[^A-Za-z0-9_\-]", "", produto_id)
    return PASTA_PRODUTOS / f"{seguro}.json"


def _salvar(registro: dict) -> None:
    """Escrita atomica: escreve em .tmp e troca — nunca deixa JSON pela metade."""
    PASTA_PRODUTOS.mkdir(parents=True, exist_ok=True)
    destino = _caminho(registro["id"])
    tmp = destino.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)
    os.replace(tmp, destino)


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def criar(grupo: dict, pasta_origem: str, precos: dict,
          precos_brasil: dict | None = None) -> dict:
    """Cria um produto a partir de um grupo do scanner + tabelas de preco por tipo.

    `precos` = tabela INTERNACIONAL (USD), usada em todos os idiomas MENOS o Brasil.
    `precos_brasil` = tabela do Brasil (BRL), aplicada só ao idioma 'pt-br'. Se não
    vier, o Brasil cai na tabela internacional (compatibilidade)."""
    tipo = grupo["tipo"]
    tabela_br = precos_brasil if precos_brasil is not None else precos

    def preco_do_idioma(codigo: str) -> float:
        tabela = tabela_br if codigo == "pt-br" else precos
        return float(tabela.get(tipo, 0) or 0)

    registro = {
        "id": _novo_id(grupo["titulo"], tipo),
        "titulo_pt": grupo["titulo"],
        "tipo": tipo,
        "numero": grupo.get("numero"),
        "pasta": str(pasta_origem),
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "descricao_pt": "",
        "idiomas": [
            {
                "codigo": item["codigo"],
                "pais": item["pais"],
                "pdf": item["pdf"],
                "capa": item.get("capa"),
                "anexos": item.get("anexos", []),
                "titulo": "",
                "descricao": "",
                "preco": preco_do_idioma(item["codigo"]),
                "status": "rascunho",
                "erro": "",
            }
            for item in grupo["idiomas"]
        ],
    }
    with _TRAVA:
        _salvar(registro)
    return registro


def listar() -> list[dict]:
    if not PASTA_PRODUTOS.is_dir():
        return []
    registros = []
    for arq in PASTA_PRODUTOS.glob("*.json"):
        try:
            with open(arq, "r", encoding="utf-8") as f:
                registros.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue  # arquivo corrompido nao derruba a listagem
    registros.sort(key=lambda r: r.get("criado_em", ""), reverse=True)
    return registros


def obter(produto_id: str) -> dict:
    with _TRAVA:
        return _obter_sem_trava(produto_id)


def _obter_sem_trava(produto_id: str) -> dict:
    arq = _caminho(produto_id)
    if not arq.is_file():
        raise ProdutoError(f"Produto nao encontrado: {produto_id}")
    with open(arq, "r", encoding="utf-8") as f:
        return json.load(f)


def remover(produto_id: str) -> None:
    with _TRAVA:
        arq = _caminho(produto_id)
        if arq.is_file():
            arq.unlink()


def remover_todos() -> int:
    """Apaga TODOS os produtos da fila. Retorna quantos foram removidos.
    NAO apaga PDFs/capas — so os registros JSON da fila."""
    with _TRAVA:
        if not PASTA_PRODUTOS.is_dir():
            return 0
        n = 0
        for arq in PASTA_PRODUTOS.glob("*.json"):
            try:
                arq.unlink()
                n += 1
            except OSError:
                pass
        return n


def atualizar(produto_id: str, patch: dict) -> dict:
    """Atualiza campos do produto (apenas os editaveis: titulo_pt, descricao_pt)."""
    invalidos = set(patch) - CAMPOS_PRODUTO
    if invalidos:
        raise ProdutoError(f"Campos nao editaveis: {', '.join(sorted(invalidos))}")
    with _TRAVA:
        registro = _obter_sem_trava(produto_id)
        registro.update(patch)
        _salvar(registro)
    return registro


def atualizar_item(produto_id: str, codigo_idioma: str, patch: dict) -> dict:
    """Atualiza um idioma do produto (titulo, descricao, preco, status, capa)."""
    invalidos = set(patch) - CAMPOS_ITEM
    if invalidos:
        raise ProdutoError(f"Campos nao editaveis: {', '.join(sorted(invalidos))}")
    if "status" in patch and patch["status"] not in STATUS_VALIDOS:
        raise ProdutoError(
            f"Status invalido: '{patch['status']}'. Validos: {', '.join(STATUS_VALIDOS)}"
        )
    if "preco" in patch:
        patch = {**patch, "preco": float(patch["preco"])}

    with _TRAVA:
        registro = _obter_sem_trava(produto_id)
        for item in registro["idiomas"]:
            if item["codigo"] == codigo_idioma:
                item.update(patch)
                _salvar(registro)
                return item
    raise ProdutoError(f"Idioma '{codigo_idioma}' nao existe no produto {produto_id}")


def definir_titulo_pt_anexos(produto_id: str, bonus: dict, extras: dict) -> int:
    """Grava o titulo PT nos anexos (bonus/extra) de TODOS os idiomas, casando
    pelo (papel, numero). `bonus`/`extras` = {numero: titulo}. Retorna quantos
    anexos foram nomeados. Chaves numericas toleram int ou str."""
    def _busca(mapa: dict, numero):
        if numero is None:
            return None
        return mapa.get(numero) or mapa.get(str(numero))

    with _TRAVA:
        registro = _obter_sem_trava(produto_id)
        n = 0
        for item in registro["idiomas"]:
            for anexo in item.get("anexos", []):
                papel = anexo.get("papel")
                if papel == "bonus":
                    novo = _busca(bonus, anexo.get("numero"))
                elif papel == "extra":
                    novo = _busca(extras, anexo.get("numero"))
                else:
                    novo = None
                if novo:
                    anexo["titulo_pt"] = novo
                    n += 1
        _salvar(registro)
        return n


def definir_titulo_traduzido_anexos(produto_id: str, codigo_idioma: str,
                                    traducao_por_pt: dict) -> int:
    """Grava o titulo traduzido nos anexos de UM idioma, casando pelo titulo_pt.
    `traducao_por_pt` = {titulo_pt: titulo_traduzido}. Retorna quantos anexos
    receberam traducao."""
    with _TRAVA:
        registro = _obter_sem_trava(produto_id)
        n = 0
        for item in registro["idiomas"]:
            if item["codigo"] != codigo_idioma:
                continue
            for anexo in item.get("anexos", []):
                pt = (anexo.get("titulo_pt") or "").strip()
                if pt and pt in traducao_por_pt:
                    anexo["titulo"] = traducao_por_pt[pt]
                    n += 1
            _salvar(registro)
            return n
    return 0
