"""Testes de integracao da API (TestClient — LLM mockado, filesystem isolado)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import time

from app.server import app
from core import agy, config, dialogo, produtos, robo, textos


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(produtos, "PASTA_PRODUTOS", tmp_path / "produtos")
    monkeypatch.setattr(config, "ARQUIVO_SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PASTA_CONFIG", tmp_path)
    return tmp_path


@pytest.fixture
def cliente():
    return TestClient(app)


@pytest.fixture
def pasta_ebooks(tmp_path):
    pasta = tmp_path / "ebooks"
    pasta.mkdir()
    for nome in (
        "Meu Ebook - Principal - Brasil.pdf",
        "Meu Ebook - Principal - Filipinas.pdf",
        "Meu Ebook - Order Bump - Brasil.pdf",
    ):
        (pasta / nome).write_bytes(b"x")
    (pasta / "Meu Ebook - Principal - Brasil.jpg").write_bytes(b"img")
    return pasta


def importar(cliente, pasta) -> list[dict]:
    r = cliente.post("/api/produtos", json={"pasta": str(pasta)})
    assert r.status_code == 200, r.text
    return r.json()["criados"]


# ---------------------------------------------------------------------------
# Status / settings
# ---------------------------------------------------------------------------
def test_status_provider_agy_disponivel(cliente, monkeypatch):
    monkeypatch.setattr(agy, "diagnostico",
                        lambda: {"disponivel": True, "tipo": "agy", "detalhe": "agy.cmd"})
    r = cliente.get("/api/status")
    assert r.status_code == 200
    assert r.json()["provider"] == "agy"
    assert r.json()["pronto"] is True


def test_status_provider_agy_ausente(cliente, monkeypatch):
    monkeypatch.setattr(agy, "diagnostico",
                        lambda: {"disponivel": False, "tipo": "", "detalhe": "agy nao encontrado"})
    r = cliente.get("/api/status")
    assert r.json()["pronto"] is False
    assert "agy" in r.json()["detalhe"]


def test_status_provider_openai_sem_key(cliente):
    cliente.post("/api/settings", json={"provider": "openai"})
    r = cliente.get("/api/status")
    assert r.json()["provider"] == "openai"
    assert r.json()["pronto"] is False


def test_settings_roundtrip(cliente):
    r = cliente.post("/api/settings", json={"openai": {"api_key": "sk-x"}})
    assert r.status_code == 200
    r2 = cliente.get("/api/settings")
    assert r2.json()["openai"]["api_key"] == "sk-x"
    assert r2.json()["precos"]["Principal"] == 19.90  # merge preservou defaults


def test_idiomas(cliente):
    r = cliente.get("/api/idiomas")
    assert len(r.json()) == 20


# ---------------------------------------------------------------------------
# Seletor de pasta nativo (dialogo mockado — nao abre janela em teste)
# ---------------------------------------------------------------------------
def test_escolher_pasta_retorna_caminho(cliente, monkeypatch):
    monkeypatch.setattr(dialogo, "escolher_pasta", lambda **kw: r"C:\HOTMART\FILIPINAS")
    r = cliente.post("/api/escolher-pasta")
    assert r.status_code == 200
    assert r.json()["pasta"] == r"C:\HOTMART\FILIPINAS"


def test_escolher_pasta_cancelado_retorna_none(cliente, monkeypatch):
    monkeypatch.setattr(dialogo, "escolher_pasta", lambda **kw: None)
    r = cliente.post("/api/escolher-pasta")
    assert r.status_code == 200
    assert r.json()["pasta"] is None


# ---------------------------------------------------------------------------
# Pastas recentes
# ---------------------------------------------------------------------------
def test_scan_registra_pasta_nas_recentes(cliente, pasta_ebooks):
    cliente.post("/api/scan", json={"pasta": str(pasta_ebooks)})
    s = cliente.get("/api/settings").json()
    assert str(pasta_ebooks) in s["pastas_recentes"]


def test_scan_repetido_nao_duplica_recente(cliente, pasta_ebooks):
    cliente.post("/api/scan", json={"pasta": str(pasta_ebooks)})
    cliente.post("/api/scan", json={"pasta": str(pasta_ebooks)})
    s = cliente.get("/api/settings").json()
    assert s["pastas_recentes"].count(str(pasta_ebooks)) == 1


def test_recentes_limitado_a_8(cliente, tmp_path):
    for n in range(10):
        p = tmp_path / f"pasta{n}"
        p.mkdir()
        (p / f"Ebook {n} - Brasil.pdf").write_bytes(b"x")
        cliente.post("/api/scan", json={"pasta": str(p)})
    s = cliente.get("/api/settings").json()
    assert len(s["pastas_recentes"]) == 8
    assert s["pastas_recentes"][0].endswith("pasta9")  # mais recente primeiro


# ---------------------------------------------------------------------------
# Scan / importacao
# ---------------------------------------------------------------------------
def test_scan_detecta_grupos_e_capa(cliente, pasta_ebooks):
    r = cliente.post("/api/scan", json={"pasta": str(pasta_ebooks)})
    assert r.status_code == 200
    grupos = r.json()["grupos"]
    assert len(grupos) == 2
    principal = next(g for g in grupos if g["tipo"] == "Principal")
    assert len(principal["idiomas"]) == 2
    ptbr = next(i for i in principal["idiomas"] if i["codigo"] == "pt-br")
    assert ptbr["capa"] is not None
    assert all(g["ja_importado"] is False for g in grupos)


def test_scan_pasta_invalida_da_400(cliente):
    r = cliente.post("/api/scan", json={"pasta": r"C:\nao\existe"})
    assert r.status_code == 400


def test_importar_cria_produtos_com_preco_da_tabela(cliente, pasta_ebooks):
    criados = importar(cliente, pasta_ebooks)
    assert len(criados) == 2
    principal = next(p for p in criados if p["tipo"] == "Principal")
    bump = next(p for p in criados if p["tipo"] == "Order Bump")
    assert principal["idiomas"][0]["preco"] == 19.90
    assert bump["idiomas"][0]["preco"] == 12.90


def test_scan_marca_ja_importado(cliente, pasta_ebooks):
    importar(cliente, pasta_ebooks)
    r = cliente.post("/api/scan", json={"pasta": str(pasta_ebooks)})
    assert all(g["ja_importado"] is True for g in r.json()["grupos"])


def test_importar_selecao_especifica(cliente, pasta_ebooks):
    r = cliente.post("/api/produtos", json={
        "pasta": str(pasta_ebooks),
        "grupos": [{"titulo": "Meu Ebook", "tipo": "Principal"}],
    })
    assert len(r.json()["criados"]) == 1
    assert r.json()["criados"][0]["tipo"] == "Principal"


# ---------------------------------------------------------------------------
# Edicao
# ---------------------------------------------------------------------------
def test_patch_produto_e_item(cliente, pasta_ebooks):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    r = cliente.patch(f"/api/produtos/{pid}", json={"descricao_pt": "Desc PT"})
    assert r.json()["descricao_pt"] == "Desc PT"

    r2 = cliente.patch(f"/api/produtos/{pid}/idiomas/pt-br",
                       json={"titulo": "Novo", "status": "revisado", "preco": 24.9})
    assert r2.status_code == 200
    assert r2.json()["titulo"] == "Novo"
    assert r2.json()["status"] == "revisado"


def test_patch_status_invalido_da_400(cliente, pasta_ebooks):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    r = cliente.patch(f"/api/produtos/{pid}/idiomas/pt-br", json={"status": "voando"})
    assert r.status_code == 400


def test_remover_produto(cliente, pasta_ebooks):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    assert cliente.delete(f"/api/produtos/{pid}").status_code == 200
    assert cliente.get(f"/api/produtos/{pid}").status_code == 404


# ---------------------------------------------------------------------------
# Geracao de textos (LLM mockado)
# ---------------------------------------------------------------------------
def test_gerar_descricao_salva_no_produto(cliente, pasta_ebooks, monkeypatch):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    monkeypatch.setattr(textos, "gerar_descricao", lambda *a, **kw: "Descricao gerada!")
    r = cliente.post(f"/api/produtos/{pid}/descricao")
    assert r.status_code == 200
    assert r.json()["descricao_pt"] == "Descricao gerada!"


def test_traduzir_atualiza_item_e_avanca_status(cliente, pasta_ebooks, monkeypatch):
    prods = importar(cliente, pasta_ebooks)
    pid = next(p for p in prods if p["tipo"] == "Principal")["id"]
    cliente.patch(f"/api/produtos/{pid}", json={"descricao_pt": "Desc PT"})
    monkeypatch.setattr(
        textos, "traduzir_textos",
        lambda *a, **kw: {"titulo": "Ang Ebook", "descricao": "Paglalarawan"},
    )
    r = cliente.post(f"/api/produtos/{pid}/traduzir/fil")
    assert r.status_code == 200
    assert r.json()["titulo"] == "Ang Ebook"
    assert r.json()["status"] == "textos_gerados"


def test_traduzir_nao_rebaixa_status_revisado(cliente, pasta_ebooks, monkeypatch):
    prods = importar(cliente, pasta_ebooks)
    pid = next(p for p in prods if p["tipo"] == "Principal")["id"]
    cliente.patch(f"/api/produtos/{pid}", json={"descricao_pt": "Desc PT"})
    cliente.patch(f"/api/produtos/{pid}/idiomas/fil", json={"status": "revisado"})
    monkeypatch.setattr(
        textos, "traduzir_textos",
        lambda *a, **kw: {"titulo": "T2", "descricao": "D2"},
    )
    r = cliente.post(f"/api/produtos/{pid}/traduzir/fil")
    assert r.json()["status"] == "revisado"  # continua revisado


def test_traduzir_sem_descricao_da_400(cliente, pasta_ebooks):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    r = cliente.post(f"/api/produtos/{pid}/traduzir/fil")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Titulos colados do Discord
# ---------------------------------------------------------------------------
@pytest.fixture
def pasta_rede(tmp_path):
    pasta = tmp_path / "rede"
    pasta.mkdir()
    for nome in (
        "PRINCIPAL REDE 4 GEMEOS - Italia.pdf",
        "ORDER BUMP 1 - REDE 4 - Italia.pdf",
        "ORDER BUMP 2 - REDE 4 - Italia.pdf",
        "OPSELL 1 - REDE 4 - Italia.pdf",
    ):
        (pasta / nome).write_bytes(b"x")
    return pasta


def test_aplicar_titulos_do_discord(cliente, pasta_rede):
    importar(cliente, pasta_rede)
    texto = (
        "rede 4 lucas signo GEMEOS\n"
        "EBOOK PRINCIPAL ; O GRANDE SEGREDO DO UNIVERSO!\n"
        "BONUS 1 ; TITULO DE BONUS QUE NAO ENTRA\n"
        "ORDEM BUMP 1; OS PRINCIPIOS DE UMA MENTE GENIAL!\n"
        "ORDEM BUMP 2; AS 30 FREQUENCIAS DO UNIVERSO!\n"
        "OPSELL 1 ;  O SEGREDO POR TRAS DA INVEJA! -\n"
    )
    r = cliente.post("/api/titulos/aplicar", json={"texto": texto, "pasta": str(pasta_rede)})
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["aplicados"]) == 4
    assert corpo["sem_match"] == []

    por_tipo = {}
    for p in cliente.get("/api/produtos").json():
        por_tipo[(p["tipo"], p.get("numero"))] = p["titulo_pt"]
    assert por_tipo[("Principal", None)] == "O GRANDE SEGREDO DO UNIVERSO!"
    assert por_tipo[("Order Bump", 1)] == "OS PRINCIPIOS DE UMA MENTE GENIAL!"
    assert por_tipo[("Order Bump", 2)] == "AS 30 FREQUENCIAS DO UNIVERSO!"
    assert por_tipo[("Upsell", 1)] == "O SEGREDO POR TRAS DA INVEJA!"


def test_aplicar_titulos_reporta_sem_match(cliente, pasta_rede):
    importar(cliente, pasta_rede)
    r = cliente.post("/api/titulos/aplicar", json={
        "texto": "EBOOK PRINCIPAL ; SO O PRINCIPAL TEM TITULO\n",
        "pasta": str(pasta_rede),
    })
    corpo = r.json()
    assert len(corpo["aplicados"]) == 1
    assert len(corpo["sem_match"]) == 3  # bumps 1 e 2 + opsell 1 sem titulo no texto


def test_aplicar_titulos_nao_afeta_outra_pasta(cliente, pasta_rede, pasta_ebooks):
    importar(cliente, pasta_rede)
    importar(cliente, pasta_ebooks)
    cliente.post("/api/titulos/aplicar", json={
        "texto": "EBOOK PRINCIPAL ; TITULO NOVO\n", "pasta": str(pasta_rede),
    })
    outros = [p for p in cliente.get("/api/produtos").json()
              if str(pasta_ebooks) in p["pasta"]]
    assert all(p["titulo_pt"] == "Meu Ebook" for p in outros)


# ---------------------------------------------------------------------------
# Capas
# ---------------------------------------------------------------------------
def test_detectar_capas_depois_de_importar(cliente, pasta_ebooks):
    prods = importar(cliente, pasta_ebooks)
    pid = next(p for p in prods if p["tipo"] == "Principal")["id"]
    # Filipinas comecou sem capa; usuario joga o arquivo na pasta DEPOIS
    (pasta_ebooks / "Meu Ebook - Principal - Filipinas.png").write_bytes(b"img")
    r = cliente.post(f"/api/produtos/{pid}/detectar-capas")
    assert r.status_code == 200
    assert r.json()["achadas"] == 1
    fil = [i for i in r.json()["produto"]["idiomas"] if i["codigo"] == "fil"][0]
    assert fil["capa"].endswith(".png")


def test_escolher_capa_manual(cliente, pasta_ebooks, monkeypatch, tmp_path):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    img = tmp_path / "capa_avulsa.jpg"
    img.write_bytes(b"img")
    monkeypatch.setattr(dialogo, "escolher_arquivo_imagem", lambda **kw: str(img))
    r = cliente.post(f"/api/produtos/{pid}/idiomas/pt-br/escolher-capa")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["item"]["capa"] == str(img)


def test_escolher_capa_cancelado(cliente, pasta_ebooks, monkeypatch):
    pid = importar(cliente, pasta_ebooks)[0]["id"]
    monkeypatch.setattr(dialogo, "escolher_arquivo_imagem", lambda **kw: None)
    r = cliente.post(f"/api/produtos/{pid}/idiomas/pt-br/escolher-capa")
    assert r.json()["ok"] is False


# ---------------------------------------------------------------------------
# Publicacao (robo — modo simulado, sem navegador)
# ---------------------------------------------------------------------------
def aguardar_estado(cliente, estado, timeout=5.0):
    fim = time.time() + timeout
    while time.time() < fim:
        r = cliente.get("/api/publicacao").json()
        if r["job"] and r["job"]["estado"] == estado:
            return r["job"]
        time.sleep(0.03)
    raise AssertionError(f"job nao chegou no estado '{estado}'")


@pytest.fixture(autouse=True)
def robo_limpo(monkeypatch):
    monkeypatch.setattr(robo, "_DELAY_SIMULADO", 0.02)
    robo._JOB = None
    yield
    if robo._JOB and robo._JOB.estado in robo.ESTADOS_ATIVOS:
        robo._JOB.cancelar()


def preparar_revisado(cliente, pasta_ebooks) -> str:
    prods = importar(cliente, pasta_ebooks)
    pid = next(p for p in prods if p["tipo"] == "Principal")["id"]
    cliente.patch(f"/api/produtos/{pid}/idiomas/fil",
                  json={"titulo": "T", "descricao": "D", "status": "revisado"})
    return pid


def test_publicacao_simulada_ponta_a_ponta(cliente, pasta_ebooks):
    pid = preparar_revisado(cliente, pasta_ebooks)

    r = cliente.post(f"/api/produtos/{pid}/publicar/fil", json={"modo": "simulado"})
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "simulado"

    aguardar_estado(cliente, "aguardando_2fa")
    assert cliente.post("/api/publicacao/codigo", json={"codigo": "123456"}).status_code == 200

    aguardar_estado(cliente, "aguardando_confirmacao")
    assert cliente.post("/api/publicacao/confirmar").status_code == 200

    job = aguardar_estado(cliente, "concluido")
    assert any("simulado" in m["texto"].lower() for m in job["mensagens"])


def test_publicar_item_nao_revisado_da_400(cliente, pasta_ebooks):
    prods = importar(cliente, pasta_ebooks)
    pid = prods[0]["id"]
    r = cliente.post(f"/api/produtos/{pid}/publicar/pt-br", json={"modo": "simulado"})
    assert r.status_code == 400
    assert "revisado" in r.json()["detail"]


def test_segundo_job_simultaneo_da_400(cliente, pasta_ebooks):
    pid = preparar_revisado(cliente, pasta_ebooks)
    assert cliente.post(f"/api/produtos/{pid}/publicar/fil",
                        json={"modo": "simulado"}).status_code == 200
    r2 = cliente.post(f"/api/produtos/{pid}/publicar/fil", json={"modo": "simulado"})
    assert r2.status_code == 400
    cliente.post("/api/publicacao/cancelar")


def test_codigo_fora_de_hora_da_400(cliente):
    r = cliente.post("/api/publicacao/codigo", json={"codigo": "111111"})
    assert r.status_code == 400


def test_cancelar_via_api(cliente, pasta_ebooks):
    pid = preparar_revisado(cliente, pasta_ebooks)
    cliente.post(f"/api/produtos/{pid}/publicar/fil", json={"modo": "simulado"})
    aguardar_estado(cliente, "aguardando_2fa")
    assert cliente.post("/api/publicacao/cancelar").status_code == 200
    aguardar_estado(cliente, "cancelado")
    item = [i for i in cliente.get(f"/api/produtos/{pid}").json()["idiomas"]
            if i["codigo"] == "fil"][0]
    assert item["status"] == "revisado"
