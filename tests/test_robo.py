"""Testes do robo (Fase B) — maquina de estados via modo simulado, sem navegador."""
import os
import time

import pytest

os.environ["HOTMARTFLOW_SIM_DELAY"] = "0.02"  # acelera o simulado nos testes

from core import produtos, robo  # noqa: E402 (env precisa vir antes)


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(produtos, "PASTA_PRODUTOS", tmp_path / "produtos")
    # zera o job global entre testes
    robo._JOB = None
    yield
    # se algum teste deixou job pendurado, destrava
    if robo._JOB and robo._JOB.estado in robo.ESTADOS_ATIVOS:
        robo._JOB.cancelar()
        aguardar(lambda: robo._JOB.estado not in robo.ESTADOS_ATIVOS)


def aguardar(cond, timeout=5.0):
    fim = time.time() + timeout
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def produto_revisado():
    grupo = {
        "titulo": "Meu Ebook",
        "tipo": "Principal",
        "idiomas": [
            {"codigo": "fil", "pais": "Filipinas", "pdf": "C:/x/a.pdf", "capa": None},
        ],
    }
    reg = produtos.criar(grupo, pasta_origem="C:/x", precos={"Principal": 19.9})
    produtos.atualizar_item(reg["id"], "fil", {
        "titulo": "Ang Ebook", "descricao": "Desc", "status": "revisado",
    })
    return produtos.obter(reg["id"])


# ---------------------------------------------------------------------------
# Renomear conteudo pro titulo traduzido (cliente nao ve o nome interno do PDF)
# ---------------------------------------------------------------------------
def test_nome_arquivo_seguro_remove_caracteres_invalidos():
    assert robo._nome_arquivo_seguro('O Segredo: Amor/Vida * Poder?') == "O Segredo Amor Vida Poder"


def test_nome_arquivo_seguro_preserva_acentos():
    assert robo._nome_arquivo_seguro("Das große Geheimnis") == "Das große Geheimnis"


def test_nome_arquivo_seguro_vazio_vira_ebook():
    assert robo._nome_arquivo_seguro("   ...   ") == "ebook"
    assert robo._nome_arquivo_seguro("") == "ebook"


def test_preparar_uploads_nomeia_principal_e_bonus_com_titulo_proprio(tmp_path):
    principal = tmp_path / "PRINCIPAL REDE 2 - Alemao.pdf"
    bonus1 = tmp_path / "BONUS 1 REDE 2 - Alemao.pdf"
    bonus2 = tmp_path / "BONUS 2 REDE 2 - Alemao.pdf"
    for f in (principal, bonus1, bonus2):
        f.write_bytes(b"%PDF-1.4 conteudo")
    destino = tmp_path / "temp_upload"
    destino.mkdir()

    # cada bonus tem SEU proprio titulo traduzido (nao numera o principal)
    itens = [
        (str(principal), "Das große Geheimnis"),
        (str(bonus1), "Die 10 spirituellen Gewohnheiten"),
        (str(bonus2), "Das Geheimnis der spirituellen Energie"),
    ]
    copias = robo.Tela._preparar_uploads(None, itens, str(destino))

    nomes = [os.path.basename(c) for c in copias]
    assert nomes == ["Das große Geheimnis.pdf",
                     "Die 10 spirituellen Gewohnheiten.pdf",
                     "Das Geheimnis der spirituellen Energie.pdf"]
    assert all(os.path.isfile(c) for c in copias)
    assert principal.read_bytes() == b"%PDF-1.4 conteudo"  # original intacto


def test_preparar_uploads_numera_nomes_repetidos(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    destino = tmp_path / "t"
    destino.mkdir()
    # dois arquivos caindo no mesmo titulo (ex.: bonus sem titulo -> principal)
    copias = robo.Tela._preparar_uploads(
        None, [(str(a), "Mesmo Título"), (str(b), "Mesmo Título")], str(destino))
    nomes = [os.path.basename(c) for c in copias]
    assert nomes == ["Mesmo Título.pdf", "Mesmo Título 2.pdf"]


def test_preparar_uploads_preserva_extensao_e_nome_vazio(tmp_path):
    origem = tmp_path / "algo - Alemao.epub"
    origem.write_bytes(b"epub")
    destino = tmp_path / "t"
    destino.mkdir()
    # com titulo
    c1 = robo.Tela._preparar_uploads(None, [(str(origem), "Meu Título")], str(destino))
    assert os.path.basename(c1[0]) == "Meu Título.epub"
    # sem titulo -> mantem o nome original do arquivo
    c2 = robo.Tela._preparar_uploads(None, [(str(origem), "")], str(destino))
    assert os.path.basename(c2[0]) == "algo - Alemao.epub"


# ---------------------------------------------------------------------------
# Fluxo simulado completo
# ---------------------------------------------------------------------------
def test_simulado_fluxo_completo():
    reg = produto_revisado()
    job = robo.iniciar(reg["id"], "fil", "simulado")

    # comeca publicando
    assert produtos.obter(reg["id"])["idiomas"][0]["status"] == "publicando"

    # chega na pausa do 2FA
    assert aguardar(lambda: job.estado == "aguardando_2fa")
    job.entregar_codigo("123456")

    # finaliza direto (sem pausa de confirmacao)
    assert aguardar(lambda: job.estado == "concluido")
    # simulado NAO marca publicado — volta pra revisado
    assert produtos.obter(reg["id"])["idiomas"][0]["status"] == "revisado"


def test_cancelar_durante_pausa_destrava_e_volta_pra_revisado():
    reg = produto_revisado()
    job = robo.iniciar(reg["id"], "fil", "simulado")
    assert aguardar(lambda: job.estado == "aguardando_2fa")
    job.cancelar()
    assert aguardar(lambda: job.estado == "cancelado")
    assert produtos.obter(reg["id"])["idiomas"][0]["status"] == "revisado"


def test_dois_jobs_simultaneos_bloqueado():
    reg = produto_revisado()
    job = robo.iniciar(reg["id"], "fil", "simulado")
    with pytest.raises(robo.RoboError):
        robo.iniciar(reg["id"], "fil", "simulado")
    job.cancelar()
    aguardar(lambda: job.estado == "cancelado")


# ---------------------------------------------------------------------------
# Validacoes de entrada
# ---------------------------------------------------------------------------
def test_publicar_item_nao_revisado_bloqueado():
    grupo = {"titulo": "X", "tipo": "Principal",
             "idiomas": [{"codigo": "en", "pais": "Ingles", "pdf": "C:/x.pdf", "capa": None}]}
    reg = produtos.criar(grupo, pasta_origem="C:/x", precos={})
    with pytest.raises(robo.RoboError, match="revisado"):
        robo.iniciar(reg["id"], "en", "simulado")


def test_publicar_real_sem_pdf_bloqueado(tmp_path):
    reg = produto_revisado()  # pdf aponta pra C:/x/a.pdf que nao existe
    with pytest.raises(robo.RoboError, match="PDF"):
        robo.iniciar(reg["id"], "fil", "real")


def test_publicar_real_sem_capa_bloqueado(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    grupo = {"titulo": "X", "tipo": "Principal",
             "idiomas": [{"codigo": "en", "pais": "Ingles", "pdf": str(pdf), "capa": None}]}
    reg = produtos.criar(grupo, pasta_origem=str(tmp_path), precos={})
    produtos.atualizar_item(reg["id"], "en", {"titulo": "T", "descricao": "D", "status": "revisado"})
    with pytest.raises(robo.RoboError, match="capa"):
        robo.iniciar(reg["id"], "en", "real")


def test_publicar_real_com_anexo_sem_pdf_bloqueado(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    capa = tmp_path / "a.jpg"
    capa.write_bytes(b"img")
    grupo = {"titulo": "X", "tipo": "Principal",
             "idiomas": [{"codigo": "en", "pais": "Ingles", "pdf": str(pdf), "capa": str(capa),
                          "anexos": [{"nome": "BONUS 1", "pdf": str(tmp_path / "sumiu.pdf"), "capa": None}]}]}
    reg = produtos.criar(grupo, pasta_origem=str(tmp_path), precos={})
    produtos.atualizar_item(reg["id"], "en", {"titulo": "T", "descricao": "D", "status": "revisado"})
    with pytest.raises(robo.RoboError, match="anexo"):
        robo.iniciar(reg["id"], "en", "real")


def test_modo_invalido_bloqueado():
    reg = produto_revisado()
    with pytest.raises(robo.RoboError, match="inválido"):
        robo.iniciar(reg["id"], "fil", "yolo")


def test_entregar_codigo_fora_de_hora_da_erro():
    reg = produto_revisado()
    job = robo.iniciar(reg["id"], "fil", "simulado")
    with pytest.raises(robo.RoboError):
        job.confirmar()  # ainda nem chegou na confirmacao
    assert aguardar(lambda: job.estado == "aguardando_2fa")
    job.cancelar()
    aguardar(lambda: job.estado == "cancelado")


def test_erro_marca_status_erro(monkeypatch):
    reg = produto_revisado()
    monkeypatch.setattr(robo, "_executar_simulado",
                        lambda job: (_ for _ in ()).throw(robo.RoboError("explodiu na etapa X")))
    job = robo.iniciar(reg["id"], "fil", "simulado")
    assert aguardar(lambda: job.estado == "erro")
    item = produtos.obter(reg["id"])["idiomas"][0]
    assert item["status"] == "erro"
    assert "explodiu" in item["erro"]
