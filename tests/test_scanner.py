"""Testes do scanner de pastas — parsing da convencao 'Titulo - Tipo - Pais.ext'."""
from pathlib import Path

import pytest

from core import scanner


def criar(pasta: Path, *nomes: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for n in nomes:
        (pasta / n).write_bytes(b"conteudo-fake")


# ---------------------------------------------------------------------------
# Parsing basico
# ---------------------------------------------------------------------------
def test_parse_nome_simples(tmp_path):
    criar(tmp_path, "Meu Ebook - Principal - Brasil.pdf")
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1
    g = r["grupos"][0]
    assert g["titulo"] == "Meu Ebook"
    assert g["tipo"] == "Principal"
    assert len(g["idiomas"]) == 1
    item = g["idiomas"][0]
    assert item["pais"] == "Brasil"
    assert item["codigo"] == "pt-br"
    assert item["pdf"].endswith("Meu Ebook - Principal - Brasil.pdf")


def test_titulo_pode_conter_hifen(tmp_path):
    criar(tmp_path, "Dinheiro - O Guia Completo - Principal - Filipinas.pdf")
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    assert g["titulo"] == "Dinheiro - O Guia Completo"
    assert g["tipo"] == "Principal"
    assert g["idiomas"][0]["codigo"] == "fil"


def test_titulo_com_hifen_sem_tipo(tmp_path):
    criar(tmp_path, "Dinheiro - O Guia Completo - Filipinas.pdf")
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    assert g["titulo"] == "Dinheiro - O Guia Completo"
    assert g["tipo"] == "Principal"


def test_tipo_com_espaco_e_case_insensitive(tmp_path):
    criar(tmp_path, "X - order bump - Franca.pdf")
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    assert g["tipo"] == "Order Bump"  # normaliza pro nome canonico
    assert g["idiomas"][0]["codigo"] == "fr"


def test_sem_tipo_no_nome_assume_principal(tmp_path):
    # formato real do EbookFlow: 'Conselhos de Daniel - Franca.pdf' (sem tipo)
    criar(tmp_path, "Conselhos de Daniel - Franca.pdf")
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    assert g["titulo"] == "Conselhos de Daniel"
    assert g["tipo"] == "Principal"
    assert g["idiomas"][0]["codigo"] == "fr"


def test_sem_tipo_agrupa_idiomas_do_mesmo_ebook(tmp_path):
    criar(
        tmp_path,
        "Conselhos de Daniel - Brasil.pdf",
        "Conselhos de Daniel - Ingles.pdf",
        "Conselhos de Daniel - Espanha.pdf",
        "Conselhos de Daniel - Franca.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1
    assert len(r["grupos"][0]["idiomas"]) == 4
    assert r["grupos"][0]["tipo"] == "Principal"


def test_pais_desconhecido_vai_pra_ignorados(tmp_path):
    criar(tmp_path, "X - Principal - Atlantida.pdf")
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"] == []
    assert len(r["ignorados"]) == 1
    assert "Atlantida" in r["ignorados"][0]["motivo"] or "pais" in r["ignorados"][0]["motivo"].lower()


def test_segmento_que_nao_e_tipo_vira_parte_do_titulo(tmp_path):
    # 'Coisa Estranha' nao e tipo conhecido -> pertence ao titulo, tipo Principal
    criar(tmp_path, "X - Coisa Estranha - Brasil.pdf")
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    assert g["titulo"] == "X - Coisa Estranha"
    assert g["tipo"] == "Principal"


def test_nome_sem_convencao_vai_pra_ignorados(tmp_path):
    criar(tmp_path, "relatorio_final.pdf")
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"] == []
    assert len(r["ignorados"]) == 1


# ---------------------------------------------------------------------------
# Agrupamento
# ---------------------------------------------------------------------------
def test_agrupa_idiomas_do_mesmo_produto(tmp_path):
    criar(
        tmp_path,
        "Meu Ebook - Principal - Brasil.pdf",
        "Meu Ebook - Principal - Filipinas.pdf",
        "Meu Ebook - Principal - Ingles.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1
    assert len(r["grupos"][0]["idiomas"]) == 3


def test_tipos_diferentes_geram_grupos_diferentes(tmp_path):
    criar(
        tmp_path,
        "Meu Ebook - Principal - Brasil.pdf",
        "Meu Ebook - Order Bump - Brasil.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 2
    tipos = {g["tipo"] for g in r["grupos"]}
    assert tipos == {"Principal", "Order Bump"}


def test_idiomas_ordenados_pela_ordem_canonica(tmp_path):
    criar(
        tmp_path,
        "X - Principal - Filipinas.pdf",
        "X - Principal - Brasil.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    codigos = [i["codigo"] for i in r["grupos"][0]["idiomas"]]
    assert codigos == ["pt-br", "fil"]  # pt-br vem antes na lista canonica


# ---------------------------------------------------------------------------
# Capas
# ---------------------------------------------------------------------------
def test_capa_no_mesmo_diretorio(tmp_path):
    criar(
        tmp_path,
        "Meu Ebook - Principal - Brasil.pdf",
        "Meu Ebook - Principal - Brasil.jpg",
    )
    r = scanner.analisar_pasta(tmp_path)
    item = r["grupos"][0]["idiomas"][0]
    assert item["capa"] is not None
    assert item["capa"].endswith(".jpg")


def test_capa_na_subpasta_capas(tmp_path):
    criar(tmp_path, "Meu Ebook - Principal - Brasil.pdf")
    criar(tmp_path / "capas", "Meu Ebook - Principal - Brasil.png")
    r = scanner.analisar_pasta(tmp_path)
    item = r["grupos"][0]["idiomas"][0]
    assert item["capa"] is not None
    assert item["capa"].endswith(".png")


def test_sem_capa_retorna_none(tmp_path):
    criar(tmp_path, "Meu Ebook - Principal - Brasil.pdf")
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"][0]["idiomas"][0]["capa"] is None


def test_capa_por_prefixo_do_nome(tmp_path):
    # padrao real da operacao: capa com o COMECO do nome do PDF
    criar(
        tmp_path,
        "PRINCIPAL REDE 1 SIGNO TOURO - LUCAS - Brasil.pdf",
        "PRINCIPAL.jpeg",
    )
    r = scanner.analisar_pasta(tmp_path)
    item = r["grupos"][0]["idiomas"][0]
    assert item["capa"] is not None
    assert item["capa"].endswith("PRINCIPAL.jpeg")


def test_capa_prefixo_nao_confunde_numeros(tmp_path):
    criar(
        tmp_path,
        "ORDER BUMP 1 REDE X - Brasil.pdf",
        "ORDER BUMP 2 - REDE X - Brasil.pdf",
        "ORDER BUMP 1.jpeg",
        "ORDER BUMP 2.jpeg",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 2
    capas = {g["titulo"]: g["idiomas"][0]["capa"] for g in r["grupos"]}
    for titulo, capa in capas.items():
        if titulo.startswith("ORDER BUMP 1"):
            assert capa.endswith("ORDER BUMP 1.jpeg")
        else:
            assert capa.endswith("ORDER BUMP 2.jpeg")


def test_capa_prefixo_nao_casa_1_com_10(tmp_path):
    criar(tmp_path, "ORDER BUMP 10 - REDE X - Brasil.pdf", "ORDER BUMP 1.jpeg")
    r = scanner.analisar_pasta(tmp_path)
    # "ORDER BUMP 1" NAO pode casar com "ORDER BUMP 10..."
    assert r["grupos"][0]["idiomas"][0]["capa"] is None


def test_capa_prefixo_prefere_match_mais_longo(tmp_path):
    criar(
        tmp_path,
        "Sabedoria Vol 1 - REDE X - Brasil.pdf",
        "Sabedoria.jpeg",
        "Sabedoria Vol 1.jpeg",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"][0]["idiomas"][0]["capa"].endswith("Sabedoria Vol 1.jpeg")


def test_capa_exata_continua_ganhando_do_prefixo(tmp_path):
    criar(
        tmp_path,
        "Meu Ebook - Brasil.pdf",
        "Meu Ebook - Brasil.jpg",   # exata
        "Meu Ebook.jpeg",           # prefixo
    )
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"][0]["idiomas"][0]["capa"].endswith("Meu Ebook - Brasil.jpg")


def test_imagem_solta_nao_vira_grupo(tmp_path):
    # imagens sao capas, nao produtos — nao devem gerar grupo nem ignorado
    criar(
        tmp_path,
        "Meu Ebook - Principal - Brasil.pdf",
        "Meu Ebook - Principal - Brasil.jpg",
        "logo_aleatorio.png",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1
    assert r["ignorados"] == []


# ---------------------------------------------------------------------------
# Tipo pelo comeco do titulo (padrao real: ORDER BUMP 1 - REDE X - Italia.pdf)
# ---------------------------------------------------------------------------
def test_tipo_pelo_comeco_do_titulo(tmp_path):
    criar(
        tmp_path,
        "PRINCIPAL REDE 1 SIGNO TOURO - LUCAS - Italia.pdf",
        "ORDER BUMP 3 - REDE 1 - Italia.pdf",
        "OPSELL 2 - REDE 1 - Italia.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    tipos = {g["titulo"]: g["tipo"] for g in r["grupos"]}
    assert tipos["PRINCIPAL REDE 1 SIGNO TOURO - LUCAS"] == "Principal"
    assert tipos["ORDER BUMP 3 - REDE 1"] == "Order Bump"
    assert tipos["OPSELL 2 - REDE 1"] == "Upsell"


def test_upsell_tambem_e_reconhecido(tmp_path):
    criar(tmp_path, "UPSELL 1 - REDE X - Brasil.pdf")
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"][0]["tipo"] == "Upsell"


# ---------------------------------------------------------------------------
# Anexos: BONUS -> Principal, EXTRA x OP y -> OPSELL y
# ---------------------------------------------------------------------------
def test_bonus_vira_anexo_do_principal(tmp_path):
    criar(
        tmp_path,
        "PRINCIPAL REDE 1 - Italia.pdf",
        "BONUS 1 REDE 1 - Italia.pdf",
        "BONUS 2 - REDE 1 - Italia.pdf",
        "BONUS 1.jpeg",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1  # bonus NAO vira produto
    item = r["grupos"][0]["idiomas"][0]
    assert len(item["anexos"]) == 2
    nomes = [a["nome"] for a in item["anexos"]]
    assert any("BONUS 1" in n for n in nomes)
    assert any("BONUS 2" in n for n in nomes)
    bonus1 = [a for a in item["anexos"] if "BONUS 1" in a["nome"]][0]
    assert bonus1["capa"].endswith("BONUS 1.jpeg")


def test_extra_vai_pro_opsell_certo(tmp_path):
    criar(
        tmp_path,
        "OPSELL 1 - REDE X - Italia.pdf",
        "OPSELL 2 - REDE X - Italia.pdf",
        "EXTRA 1 OP 1 - REDE X - Italia.pdf",
        "EXTRA 2 OP 1 - REDE X - Italia.pdf",
        "EXTRA 1 OP 2 - REDE X - Italia.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 2
    op1 = next(g for g in r["grupos"] if g["titulo"].startswith("OPSELL 1"))
    op2 = next(g for g in r["grupos"] if g["titulo"].startswith("OPSELL 2"))
    assert len(op1["idiomas"][0]["anexos"]) == 2   # EXTRA 1 OP 1 + EXTRA 2 OP 1
    assert len(op2["idiomas"][0]["anexos"]) == 1   # EXTRA 1 OP 2
    assert all("OP 1" in a["nome"] for a in op1["idiomas"][0]["anexos"])


def test_anexo_respeita_o_pais(tmp_path):
    criar(
        tmp_path,
        "PRINCIPAL REDE X - Italia.pdf",
        "PRINCIPAL REDE X - Brasil.pdf",
        "BONUS 1 - REDE X - Italia.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    g = r["grupos"][0]
    italia = next(i for i in g["idiomas"] if i["codigo"] == "it")
    brasil = next(i for i in g["idiomas"] if i["codigo"] == "pt-br")
    assert len(italia["anexos"]) == 1
    assert brasil["anexos"] == []


def test_extra_orfao_gera_aviso(tmp_path):
    criar(tmp_path, "EXTRA 1 OP 3 - REDE X - Italia.pdf")  # nao existe OPSELL 3
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"] == []
    assert len(r["ignorados"]) == 1
    assert "OPSELL 3" in r["ignorados"][0]["motivo"] or "OP 3" in r["ignorados"][0]["motivo"]


def test_bonus_orfao_gera_aviso(tmp_path):
    criar(tmp_path, "BONUS 1 - REDE X - Italia.pdf")  # nao existe principal
    r = scanner.analisar_pasta(tmp_path)
    assert r["grupos"] == []
    assert len(r["ignorados"]) == 1


def test_slot_bonus_tambem_vira_anexo(tmp_path):
    # formato antigo com tipo no slot: 'tst - Bonus - Brasil.pdf'
    criar(
        tmp_path,
        "tst - Principal - Brasil.pdf",
        "tst extra - Bonus - Brasil.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    assert len(r["grupos"]) == 1
    assert len(r["grupos"][0]["idiomas"][0]["anexos"]) == 1


def test_order_bump_nao_recebe_anexo(tmp_path):
    criar(
        tmp_path,
        "PRINCIPAL - REDE X - Italia.pdf",
        "ORDER BUMP 1 - REDE X - Italia.pdf",
        "BONUS 1 - REDE X - Italia.pdf",
    )
    r = scanner.analisar_pasta(tmp_path)
    bump = next(g for g in r["grupos"] if g["tipo"] == "Order Bump")
    assert bump["idiomas"][0]["anexos"] == []


# ---------------------------------------------------------------------------
# analisar_rede — pasta da REDE com subpastas por PAIS (país = nome da pasta)
# ---------------------------------------------------------------------------
def montar_rede(tmp_path):
    """Cria a estrutura REDE/PAIS/arquivos (país = pasta, sem sufixo no nome)."""
    def pais(nome, arquivos):
        p = tmp_path / nome
        p.mkdir()
        for a in arquivos:
            (p / a).write_bytes(b"x")

    pais("ALEMANHA", [
        "PRINCIPAL REDE 2 SIGNO ESCORPIAO - LUCAS.pdf", "PRINCIPAL.jpeg",
        "ORDER BUMP 1 REDE 2 SIGNO ESCORPIAO.pdf", "ORDER BUMP 1.jpeg",
        "BONUS 1 REDE 2 SIGNO ESCORPIAO.pdf", "BONUS 1.jpeg",
        "OPSELL 1 REDE 2 SIGNO ESCORPIAO.pdf", "OPSELL 1.jpeg",
        "EXTRA 1 OP 1 REDE 2 SIGNO ESCORPIAO.pdf", "EXTRA 1 OP 1.jpeg",
    ])
    pais("BRASIL", [
        "PRINCIPAL REDE 2 SIGNO ESCORPIAO - LUCAS.pdf",
        "ORDER BUMP 1 REDE 2 SIGNO ESCORPIAO.pdf",
    ])
    (tmp_path / "ZPAG CHECKOUT").mkdir()
    (tmp_path / "ZPAG CHECKOUT" / "qualquer.pdf").write_bytes(b"x")
    return tmp_path


def test_rede_le_paises_das_subpastas(tmp_path):
    montar_rede(tmp_path)
    r = scanner.analisar_rede(tmp_path)
    # PRINCIPAL existe em ALEMANHA e BRASIL -> 1 produto, 2 idiomas
    principal = next(g for g in r["grupos"] if g["tipo"] == "Principal")
    codigos = {i["codigo"] for i in principal["idiomas"]}
    assert codigos == {"de", "pt-br"}  # ALEMANHA->de, BRASIL->pt-br


def test_rede_ignora_zpag_checkout(tmp_path):
    montar_rede(tmp_path)
    r = scanner.analisar_rede(tmp_path)
    assert "ZPAG CHECKOUT" not in [pp["pasta"] for pp in r.get("paises", [])]
    # nenhum produto veio da pasta ZPAG CHECKOUT
    from pathlib import Path as _P
    assert all(_P(i["pdf"]).parent.name.upper() != "ZPAG CHECKOUT"
               for g in r["grupos"] for i in g["idiomas"])


def test_rede_tipos_e_anexos_dentro_da_pasta(tmp_path):
    montar_rede(tmp_path)
    r = scanner.analisar_rede(tmp_path)
    tipos = {g["tipo"] for g in r["grupos"]}
    assert tipos == {"Principal", "Order Bump", "Upsell"}
    # o BONUS de ALEMANHA vira anexo do Principal (idioma de)
    principal = next(g for g in r["grupos"] if g["tipo"] == "Principal")
    item_de = next(i for i in principal["idiomas"] if i["codigo"] == "de")
    assert any("BONUS 1" in a["nome"] for a in item_de["anexos"])
    # o EXTRA de ALEMANHA vira anexo do OPSELL
    ops = next(g for g in r["grupos"] if g["tipo"] == "Upsell")
    item_ops = next(i for i in ops["idiomas"] if i["codigo"] == "de")
    assert any("EXTRA 1 OP 1" in a["nome"] for a in item_ops["anexos"])


def test_rede_capa_por_prefixo_dentro_da_pasta(tmp_path):
    montar_rede(tmp_path)
    r = scanner.analisar_rede(tmp_path)
    principal = next(g for g in r["grupos"] if g["tipo"] == "Principal")
    item_de = next(i for i in principal["idiomas"] if i["codigo"] == "de")
    assert item_de["capa"] and item_de["capa"].endswith("PRINCIPAL.jpeg")


def test_rede_pais_desconhecido_vai_pra_avisos(tmp_path):
    (tmp_path / "ATLANTIDA").mkdir()
    (tmp_path / "ATLANTIDA" / "PRINCIPAL X.pdf").write_bytes(b"x")
    r = scanner.analisar_rede(tmp_path)
    assert any("Atlantida" in ig["motivo"] or "ATLANTIDA" in ig["arquivo"]
               for ig in r["ignorados"])


def test_rede_pasta_inexistente_levanta_erro():
    with pytest.raises(scanner.ScannerError):
        scanner.analisar_rede(r"C:\nao\existe")


def test_capa_casa_ordem_com_order_por_assinatura(tmp_path):
    # a capa e "ORDEM BUMP 7" (PT), o PDF e "ORDER BUMP 7..." (EN) -> casa por tipo+numero
    p = tmp_path / "GRECIA"
    p.mkdir()
    (p / "ORDER BUMP 7 REDE 2 SIGNO ESCORPIAO - LUCAS.pdf").write_bytes(b"x")
    (p / "ORDEM BUMP 7.jpeg").write_bytes(b"img")
    r = scanner.analisar_rede(tmp_path)
    bump = next(g for g in r["grupos"] if g["tipo"] == "Order Bump")
    assert bump["idiomas"][0]["capa"] and bump["idiomas"][0]["capa"].endswith("ORDEM BUMP 7.jpeg")


def test_assinatura_nao_confunde_bump_7_com_bump_1(tmp_path):
    p = tmp_path / "GRECIA"
    p.mkdir()
    (p / "ORDER BUMP 7 REDE X.pdf").write_bytes(b"x")
    (p / "ORDEM BUMP 1.jpeg").write_bytes(b"img")  # numero diferente -> NAO casa
    r = scanner.analisar_rede(tmp_path)
    bump = next(g for g in r["grupos"] if g["tipo"] == "Order Bump")
    assert bump["idiomas"][0]["capa"] is None


def test_rede_ignora_pag_checkout_sem_z(tmp_path):
    (tmp_path / "PAG CHECKOUT").mkdir()
    (tmp_path / "PAG CHECKOUT" / "x.pdf").write_bytes(b"x")
    (tmp_path / "BRASIL").mkdir()
    (tmp_path / "BRASIL" / "PRINCIPAL X.pdf").write_bytes(b"x")
    r = scanner.analisar_rede(tmp_path)
    assert "PAG CHECKOUT" not in [pp["pasta"] for pp in r["paises"]]
    assert not any("checkout" in ig["arquivo"].lower() for ig in r["ignorados"])


def test_rede_reconhece_republica_tcheca(tmp_path):
    p = tmp_path / "REPUBLICA TCHECA"
    p.mkdir()
    (p / "PRINCIPAL REDE X.pdf").write_bytes(b"x")
    r = scanner.analisar_rede(tmp_path)
    assert "REPUBLICA TCHECA" in [pp["pasta"] for pp in r["paises"]]
    assert r["grupos"][0]["idiomas"][0]["codigo"] == "cs"


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------
def test_pasta_inexistente_levanta_erro():
    with pytest.raises(scanner.ScannerError):
        scanner.analisar_pasta(r"C:\nao\existe\essa\pasta")
