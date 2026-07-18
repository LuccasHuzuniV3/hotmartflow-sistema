"""Testes do histórico de links de checkout + helpers do fluxo de checkout."""
import pytest

from core import checkouts, hotmart_map as hm, idiomas, produtos, robo


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(checkouts, "ARQUIVO", tmp_path / "checkouts.jsonl")
    monkeypatch.setattr(produtos, "PASTA_PRODUTOS", tmp_path / "produtos")
    return tmp_path


# ---------------------------------------------------------------------------
# Registro de links
# ---------------------------------------------------------------------------
def test_registrar_e_agrupar_links():
    checkouts.registrar(rede="REDE 3", pais="Alemao", titulo="T DE",
                        link="https://pay.hotmart.com/AAA?checkoutMode=10")
    checkouts.registrar(rede="REDE 3", pais="Brasil", titulo="T BR",
                        link="https://pay.hotmart.com/BBB?checkoutMode=10")
    arv = checkouts.agrupado()
    assert set(arv["REDE 3"].keys()) == {"Alemao", "Brasil"}
    assert arv["REDE 3"]["Alemao"][0]["link"].startswith("https://pay.hotmart.com/AAA")


# ---------------------------------------------------------------------------
# Texto da contagem regressiva (tabela embutida, todos os idiomas)
# ---------------------------------------------------------------------------
def test_texto_contagem_cobre_todos_os_idiomas():
    for info in idiomas.IDIOMAS:
        assert info["codigo"] in hm.TEXTO_CONTAGEM, f"faltou {info['codigo']}"
        assert hm.texto_contagem(info["codigo"]).strip()


def test_texto_contagem_desconhecido_cai_pro_ingles():
    assert hm.texto_contagem("klingon") == hm.TEXTO_CONTAGEM["en"]


# ---------------------------------------------------------------------------
# _bumps_do_checkout — bumps publicados da mesma rede, no idioma, em ordem
# ---------------------------------------------------------------------------
def _criar_produto(tipo, numero, pasta, itens):
    grupo = {"titulo": f"{tipo} {numero or ''}".strip(), "tipo": tipo,
             "numero": numero, "idiomas": itens}
    return produtos.criar(grupo, pasta_origem=pasta, precos={"Principal": 19.9, "Order Bump": 12.9})


def _item(codigo, pais):
    return {"codigo": codigo, "pais": pais, "pdf": "C:/x/a.pdf", "capa": None}


def test_bumps_do_checkout_filtra_e_ordena():
    principal = _criar_produto("Principal", None, "C:/rede3", [_item("de", "Alemao")])
    b2 = _criar_produto("Order Bump", 2, "C:/rede3", [_item("de", "Alemao")])
    b1 = _criar_produto("Order Bump", 1, "C:/rede3", [_item("de", "Alemao")])
    b3 = _criar_produto("Order Bump", 3, "C:/rede3", [_item("de", "Alemao")])
    outra = _criar_produto("Order Bump", 9, "C:/OUTRA", [_item("de", "Alemao")])

    # publica b1 e b2 (com textos); b3 fica rascunho; o de outra rede publicado
    for reg, tit in ((b1, "Bump Eins"), (b2, "Bump Zwei"), (outra, "Bump Outro")):
        produtos.atualizar_item(reg["id"], "de",
                                {"titulo": tit, "descricao": "D" * 600, "status": "publicado"})

    bumps = robo._bumps_do_checkout(produtos.obter(principal["id"]), "de")
    assert [b["titulo"] for b in bumps] == ["Bump Eins", "Bump Zwei"]  # ordem 1, 2
    assert all(len(b["descricao"]) <= 500 for b in bumps)              # corta em 500


# ---------------------------------------------------------------------------
# _imagem_checkout — subpasta 'checkout' + arquivo com nome do pais
# ---------------------------------------------------------------------------
def test_imagem_checkout_acha_pelo_nome_do_pais(tmp_path):
    ck = tmp_path / "ZPAG DE CHECKOUT"
    ck.mkdir()
    (ck / "ALEMANHA.jpg").write_bytes(b"img")
    (ck / "BRASIL.png").write_bytes(b"img")
    (ck / "1784127731.jpg").write_bytes(b"img")   # lixo sem nome de pais
    assert robo._imagem_checkout(str(tmp_path), "de").endswith("ALEMANHA.jpg")
    assert robo._imagem_checkout(str(tmp_path), "pt-br").endswith("BRASIL.png")
    assert robo._imagem_checkout(str(tmp_path), "fil") is None  # pais sem imagem


def test_imagem_checkout_sem_pasta_retorna_none(tmp_path):
    assert robo._imagem_checkout(str(tmp_path), "de") is None
    assert robo._imagem_checkout("C:/nao/existe", "de") is None


# ---------------------------------------------------------------------------
# Validação do modo checkout
# ---------------------------------------------------------------------------
def test_validar_checkout_exige_principal_publicado():
    it = {"pais": "Alemao", "status": "publicado", "titulo": "T", "descricao": "D"}
    # ok: principal publicado
    robo._validar_item({"tipo": "Principal"}, it, "checkout")
    # bump nao pode
    with pytest.raises(robo.RoboError, match="PRINCIPAL"):
        robo._validar_item({"tipo": "Order Bump"}, it, "checkout")
    # nao publicado nao pode
    with pytest.raises(robo.RoboError, match="publique"):
        robo._validar_item({"tipo": "Principal"}, {**it, "status": "revisado"}, "checkout")
