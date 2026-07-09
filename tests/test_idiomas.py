"""Testes do catalogo de idiomas/paises (compativel com a convencao do EbookFlow)."""
from core import idiomas


def test_lista_tem_20_idiomas():
    assert len(idiomas.IDIOMAS) == 20


def test_por_pais_match_exato():
    info = idiomas.por_pais("Filipinas")
    assert info is not None
    assert info["codigo"] == "fil"


def test_por_pais_case_insensitive():
    assert idiomas.por_pais("filipinas")["codigo"] == "fil"
    assert idiomas.por_pais("BRASIL")["codigo"] == "pt-br"


def test_por_pais_ignora_acentos():
    # EbookFlow grava "Alemao"/"Franca" sem acento, mas alguem pode nomear com acento
    assert idiomas.por_pais("Alemão")["codigo"] == "de"
    assert idiomas.por_pais("França")["codigo"] == "fr"


def test_por_pais_desconhecido_retorna_none():
    assert idiomas.por_pais("Atlantida") is None


def test_por_codigo():
    assert idiomas.por_codigo("en")["pais"] == "Ingles"
    assert idiomas.por_codigo("xx") is None


def test_ordem_do_idioma():
    # pt-br vem primeiro na lista (ordem canonica de exibicao)
    assert idiomas.ordem("pt-br") < idiomas.ordem("fil")
    # desconhecido vai pro final
    assert idiomas.ordem("xx") > idiomas.ordem("fil")
