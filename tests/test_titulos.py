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


def test_bonus_e_linhas_estranhas_sao_ignoradas_sem_erro():
    r = titulos.parse_titulos(TEXTO_REAL)
    # 4 linhas de BONUS + 1 header "rede 4..." — nada disso vira titulo de produto
    assert len(r["ignoradas"]) >= 5
    assert not any("BONUS" in (r["principal"] or "") for _ in [0])


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
