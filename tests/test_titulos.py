"""Testes do parser de titulos colados do Discord."""
from core import titulos

TEXTO_REAL = """rede 4 lucas signo GÊMEOS
EBOOK PRINCIPAL ; O GRANDE SEGREDO DO UNIVERSO PARA AFASTAR A INVEJA DA VIDA DE GÊMEOS!
BONUS 1 ; AS 9 MUDANÇAS ESPIRITUAIS QUE DEUS ESTÁ PREPARANDO PARA O DESTINO DE GÊMEOS!
BONUS 2 ; AS 7 BARREIRAS CÁRMICAS QUE ATRASAM A PROSPERIDADE DO SIGNO DE GÊMEOS!
ORDEM BUMP 1; OS PRINCÍPIOS DE UMA MENTE GENIAL PARA O SUCESSO DO SIGNO DE GÊMEOS!
ORDEM BUMP 2; AS 30 FREQUÊNCIAS DO UNIVERSO QUE DESPERTAM A PROSPERIDADE DO SIGNO DE GÊMEOS!
----
OPSELL 1 ;   O SEGREDO DO UNIVERSO POR TRÁS DA INVEJA CONTRA O SIGNO DE GÊMEOS! -
BONUS 1;    OS 9 HÁBITOS QUE FAZEM O SIGNO DE GÊMEOS ATRAIR PROSPERIDADE!
BONUS 2;    O SEGREDO DO UNIVERSO POR TRÁS DA ENERGIA DO SIGNO DE GÊMEOS!
------------------------------------
OPSELL 2;   AS 7 PROTEÇÕES DO UNIVERSO CONTRA A INVEJA NO SIGNO DE GÊMEOS! -
"""


def test_parse_formato_real_do_discord():
    r = titulos.parse_titulos(TEXTO_REAL)
    assert r["principal"] == "O GRANDE SEGREDO DO UNIVERSO PARA AFASTAR A INVEJA DA VIDA DE GÊMEOS!"
    assert r["bumps"][1].startswith("OS PRINCÍPIOS DE UMA MENTE GENIAL")
    assert r["bumps"][2].startswith("AS 30 FREQUÊNCIAS")
    # trailing " -" do opsell tem que ser limpo
    assert r["upsells"][1] == "O SEGREDO DO UNIVERSO POR TRÁS DA INVEJA CONTRA O SIGNO DE GÊMEOS!"
    assert r["upsells"][2] == "AS 7 PROTEÇÕES DO UNIVERSO CONTRA A INVEJA NO SIGNO DE GÊMEOS!"


def test_bonus_sao_capturados_com_titulo():
    r = titulos.parse_titulos(TEXTO_REAL)
    # BONUS agora vira titulo de anexo (casado por numero)
    assert r["bonus"][1].startswith("OS 9 HÁBITOS")  # ultimo BONUS 1 vence
    assert r["bonus"][2].startswith("O SEGREDO DO UNIVERSO POR TRÁS DA ENERGIA")
    # o header "rede 4..." continua sendo ignorado (nao vira titulo)
    assert any("rede 4" in ig["linha"].lower() for ig in r["ignoradas"])
    assert "BONUS" not in (r["principal"] or "")


def test_variacoes_de_rotulo():
    texto = (
        "PRINCIPAL: Titulo A\n"
        "ORDER BUMP 3 - Titulo B\n"
        "UPSELL 1; Titulo C\n"
    )
    r = titulos.parse_titulos(texto)
    assert r["principal"] == "Titulo A"
    assert r["bumps"][3] == "Titulo B"
    assert r["upsells"][1] == "Titulo C"


def test_texto_vazio():
    r = titulos.parse_titulos("")
    assert r["principal"] is None
    assert r["bumps"] == {}
    assert r["upsells"] == {}


def test_numero_do_produto():
    assert titulos.numero_do_produto("ORDER BUMP 7 - REDE 1 SIGNO TOURO") == 7
    assert titulos.numero_do_produto("OPSELL 2 - REDE 1") == 2
    assert titulos.numero_do_produto("UPSELL 3") == 3
    assert titulos.numero_do_produto("PRINCIPAL REDE 1") is None
