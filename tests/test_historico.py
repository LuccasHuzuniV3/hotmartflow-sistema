"""Testes do histórico de publicações."""
import pytest

from core import historico


@pytest.fixture(autouse=True)
def arquivo_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(historico, "ARQUIVO", tmp_path / "historico.jsonl")
    return tmp_path


def test_registrar_e_listar():
    historico.registrar(rede="REDE 2", pais="Alemao", titulo="O Segredo", tipo="Principal")
    lst = historico.listar()
    assert len(lst) == 1
    assert lst[0]["rede"] == "REDE 2"
    assert lst[0]["titulo"] == "O Segredo"
    assert lst[0]["quando"]  # tem timestamp


def test_registrar_guarda_hotmart_id():
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal", hotmart_id="8099033")
    assert historico.listar()[0]["hotmart_id"] == "8099033"


def test_agrupado_por_rede_e_pais():
    historico.registrar(rede="REDE A", pais="Alemao", titulo="Principal DE", tipo="Principal")
    historico.registrar(rede="REDE A", pais="Alemao", titulo="Bump 1 DE", tipo="Order Bump")
    historico.registrar(rede="REDE A", pais="Brasil", titulo="Principal BR", tipo="Principal")
    historico.registrar(rede="REDE B", pais="Italia", titulo="Principal IT", tipo="Principal")

    arv = historico.agrupado()
    assert set(arv.keys()) == {"REDE A", "REDE B"}
    assert set(arv["REDE A"].keys()) == {"Alemao", "Brasil"}
    assert len(arv["REDE A"]["Alemao"]) == 2
    titulos = [x["titulo"] for x in arv["REDE A"]["Alemao"]]
    assert "Principal DE" in titulos and "Bump 1 DE" in titulos


def test_listar_vazio():
    assert historico.listar() == []
    assert historico.agrupado() == {}


def test_remover_tudo():
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal")
    historico.registrar(rede="R", pais="Ingles", titulo="T2", tipo="Principal")
    assert historico.remover_tudo() == 2
    assert historico.listar() == []


def test_remover_tudo_vira_backup_e_recuperar_traz_de_volta(arquivo_isolado):
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal")
    historico.registrar(rede="R", pais="Ingles", titulo="T2", tipo="Upsell 1")
    historico.remover_tudo()
    assert historico.listar() == []                       # some da tela...
    backups = list(arquivo_isolado.glob("historico-backup-*.jsonl"))
    assert len(backups) == 1                              # ...mas virou backup

    voltaram = historico.restaurar_ultimo_backup()
    assert voltaram == 2
    titulos = {r["titulo"] for r in historico.listar()}
    assert titulos == {"T", "T2"}


def test_restaurar_backup_nao_duplica_registros_existentes():
    historico.registrar(rede="R", pais="Brasil", titulo="T", tipo="Principal")
    historico.remover_tudo()
    # depois do limpar, um novo registro identico foi criado de novo
    historico.restaurar_ultimo_backup()
    assert len(historico.listar()) == 1
    # restaurar de novo nao duplica
    assert historico.restaurar_ultimo_backup() == 0
    assert len(historico.listar()) == 1


def test_restaurar_sem_backup_retorna_zero():
    assert historico.restaurar_ultimo_backup() == 0


def test_remover_registro_tira_so_o_item_certo():
    historico.registrar(rede="R", pais="Brasil", titulo="TESTE", tipo="Principal")
    historico.registrar(rede="R", pais="Brasil", titulo="Real", tipo="Principal")
    alvo = [r for r in historico.listar() if r["titulo"] == "TESTE"][0]
    ok = historico.remover_registro(rede=alvo["rede"], pais=alvo["pais"],
                                    titulo=alvo["titulo"], tipo=alvo["tipo"],
                                    quando=alvo["quando"])
    assert ok is True
    restam = historico.listar()
    assert len(restam) == 1 and restam[0]["titulo"] == "Real"
    # remover de novo (nao existe mais) -> False, sem efeito
    assert historico.remover_registro(rede=alvo["rede"], pais=alvo["pais"],
                                      titulo=alvo["titulo"], tipo=alvo["tipo"],
                                      quando=alvo["quando"]) is False
    assert len(historico.listar()) == 1


def test_linha_corrompida_nao_derruba():
    historico.ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    historico.ARQUIVO.write_text('{"rede":"R","pais":"Brasil","titulo":"ok","tipo":"Principal"}\nLIXO\n',
                                 encoding="utf-8")
    lst = historico.listar()
    assert len(lst) == 1 and lst[0]["titulo"] == "ok"
