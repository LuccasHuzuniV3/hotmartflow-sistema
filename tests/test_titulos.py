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


# --- montar_lista_titulos (export do HISTÓRICO, por país) ---

def _hist_exemplo():
    # registros do histórico (como historico.listar() devolve)
    return [
        {"rede": "REDE 8", "pais": "Alemão", "tipo": "Principal", "titulo": "PRINC DE"},
        {"rede": "REDE 8", "pais": "Alemão", "tipo": "Order Bump 1", "titulo": "BUMP1 DE"},
        {"rede": "REDE 8", "pais": "Alemão", "tipo": "Upsell 1", "titulo": "UP1 DE"},
        {"rede": "REDE 8", "pais": "Alemão", "tipo": "Extra 1", "titulo": "EXTRA1 DE"},
        {"rede": "REDE 8", "pais": "Brasil", "tipo": "Principal", "titulo": "PRINC BR"},
    ]


def test_export_so_principal_upsell_extra_e_ignora_bump():
    txt = titulos.montar_lista_titulos(_hist_exemplo())
    assert "ALEMÃO" in txt and "BRASIL" in txt
    bloco_de = [b for b in txt.split("-" * 56) if "ALEMÃO" in b][0]
    # ordem: PRINCIPAL, UPSELL 1, EXTRA 1 — e Order Bump NÃO aparece
    assert "BUMP" not in txt.upper()
    assert bloco_de.index("PRINCIPAL: PRINC DE") < bloco_de.index("UPSELL 1: UP1 DE")
    assert bloco_de.index("UPSELL 1: UP1 DE") < bloco_de.index("EXTRA 1: EXTRA1 DE")
    assert "BUMP1 DE" not in txt


def test_export_dedupe_pega_o_mais_recente():
    regs = [
        {"rede": "R", "pais": "Brasil", "tipo": "Principal", "titulo": "VELHO"},
        {"rede": "R", "pais": "Brasil", "tipo": "Principal", "titulo": "NOVO"},
    ]
    txt = titulos.montar_lista_titulos(regs)
    assert "PRINCIPAL: NOVO" in txt and "VELHO" not in txt


def test_export_varias_redes_ganha_cabecalho():
    regs = [
        {"rede": "REDE 7", "pais": "Brasil", "tipo": "Principal", "titulo": "P7"},
        {"rede": "REDE 8", "pais": "Brasil", "tipo": "Principal", "titulo": "P8"},
    ]
    txt = titulos.montar_lista_titulos(regs)
    assert "===== REDE 7 =====" in txt and "===== REDE 8 =====" in txt


def test_export_uma_rede_sem_cabecalho():
    txt = titulos.montar_lista_titulos(_hist_exemplo())
    assert "=====" not in txt   # rede única não mostra cabeçalho


def test_export_vazio():
    assert titulos.montar_lista_titulos([]) == ""
