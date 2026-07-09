"""Testes do repositorio de produtos (fila de publicacao persistida em JSON)."""
import pytest

from core import produtos


@pytest.fixture(autouse=True)
def pasta_isolada(tmp_path, monkeypatch):
    """Redireciona a persistencia pra uma pasta temporaria em todos os testes."""
    monkeypatch.setattr(produtos, "PASTA_PRODUTOS", tmp_path)
    return tmp_path


def grupo_exemplo():
    return {
        "titulo": "Meu Ebook",
        "tipo": "Principal",
        "idiomas": [
            {"codigo": "pt-br", "pais": "Brasil", "pdf": "C:/x/a.pdf", "capa": "C:/x/a.jpg"},
            {"codigo": "fil", "pais": "Filipinas", "pdf": "C:/x/b.pdf", "capa": None},
        ],
    }


PRECOS = {"Principal": 19.90, "Order Bump": 12.90, "Upsell": 15.90}


# ---------------------------------------------------------------------------
# Criacao
# ---------------------------------------------------------------------------
def test_criar_produto_basico():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    assert reg["id"]
    assert reg["titulo_pt"] == "Meu Ebook"
    assert reg["tipo"] == "Principal"
    assert reg["descricao_pt"] == ""
    assert len(reg["idiomas"]) == 2


def test_criar_aplica_preco_da_tabela_pelo_tipo():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    assert all(i["preco"] == 19.90 for i in reg["idiomas"])


def test_criar_tipo_sem_preco_na_tabela_usa_zero():
    g = grupo_exemplo()
    g["tipo"] = "Bonus"
    reg = produtos.criar(g, pasta_origem="C:/x", precos=PRECOS)
    assert all(i["preco"] == 0 for i in reg["idiomas"])


def test_criar_itens_comecam_como_rascunho():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    assert all(i["status"] == "rascunho" for i in reg["idiomas"])
    assert all(i["titulo"] == "" and i["descricao"] == "" for i in reg["idiomas"])


def test_criar_persiste_e_listar_recupera():
    produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    lista = produtos.listar()
    assert len(lista) == 1
    assert lista[0]["titulo_pt"] == "Meu Ebook"


def test_ids_unicos_mesmo_com_mesmo_titulo():
    r1 = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    r2 = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    assert r1["id"] != r2["id"]


# ---------------------------------------------------------------------------
# Leitura / remocao
# ---------------------------------------------------------------------------
def test_obter_por_id():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    assert produtos.obter(reg["id"])["id"] == reg["id"]


def test_obter_inexistente_levanta_erro():
    with pytest.raises(produtos.ProdutoError):
        produtos.obter("nao_existe")


def test_remover():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    produtos.remover(reg["id"])
    assert produtos.listar() == []


# ---------------------------------------------------------------------------
# Atualizacao do produto (campos PT)
# ---------------------------------------------------------------------------
def test_atualizar_descricao_pt():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    atualizado = produtos.atualizar(reg["id"], {"descricao_pt": "Nova descricao"})
    assert atualizado["descricao_pt"] == "Nova descricao"
    assert produtos.obter(reg["id"])["descricao_pt"] == "Nova descricao"


def test_atualizar_campo_nao_permitido_levanta_erro():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    with pytest.raises(produtos.ProdutoError):
        produtos.atualizar(reg["id"], {"id": "hack"})


# ---------------------------------------------------------------------------
# Atualizacao de item (por idioma)
# ---------------------------------------------------------------------------
def test_atualizar_item_textos_e_status():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    item = produtos.atualizar_item(reg["id"], "fil", {
        "titulo": "Ang Aking Ebook",
        "descricao": "Descricao em tagalog",
        "status": "textos_gerados",
    })
    assert item["titulo"] == "Ang Aking Ebook"
    assert item["status"] == "textos_gerados"
    # nao vazou pros outros idiomas
    outro = [i for i in produtos.obter(reg["id"])["idiomas"] if i["codigo"] == "pt-br"][0]
    assert outro["titulo"] == ""


def test_atualizar_item_preco():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    item = produtos.atualizar_item(reg["id"], "fil", {"preco": 24.90})
    assert item["preco"] == 24.90


def test_atualizar_item_status_invalido_levanta_erro():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    with pytest.raises(produtos.ProdutoError):
        produtos.atualizar_item(reg["id"], "fil", {"status": "voando"})


def test_atualizar_item_idioma_inexistente_levanta_erro():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    with pytest.raises(produtos.ProdutoError):
        produtos.atualizar_item(reg["id"], "de", {"titulo": "x"})


def test_atualizar_item_campo_nao_permitido_levanta_erro():
    reg = produtos.criar(grupo_exemplo(), pasta_origem="C:/x", precos=PRECOS)
    with pytest.raises(produtos.ProdutoError):
        produtos.atualizar_item(reg["id"], "fil", {"pdf": "C:/malicioso.pdf"})


# ---------------------------------------------------------------------------
# Concorrencia (traducoes paralelas e "revisar todos" batem no mesmo JSON)
# ---------------------------------------------------------------------------
def test_atualizacoes_concorrentes_nao_perdem_dados_nem_estouram():
    from concurrent.futures import ThreadPoolExecutor

    grupo = {
        "titulo": "Ebook Concorrente",
        "tipo": "Principal",
        "idiomas": [
            {"codigo": c, "pais": c, "pdf": f"C:/x/{c}.pdf", "capa": None}
            for c in ("pt-br", "en", "es", "fr", "de", "it", "pl", "fil")
        ],
    }
    reg = produtos.criar(grupo, pasta_origem="C:/x", precos=PRECOS)

    def gravar(codigo):
        # cada worker atualiza o SEU idioma 5x — simula fim de traducoes paralelas
        for n in range(5):
            produtos.atualizar_item(reg["id"], codigo, {"titulo": f"T-{codigo}-{n}"})

    codigos = [i["codigo"] for i in reg["idiomas"]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        # se alguma thread estourar (PermissionError etc), o result() relanca aqui
        for futuro in [pool.submit(gravar, c) for c in codigos]:
            futuro.result()

    final = produtos.obter(reg["id"])
    for item in final["idiomas"]:
        assert item["titulo"] == f"T-{item['codigo']}-4", \
            f"update perdido no idioma {item['codigo']}: {item['titulo']!r}"
