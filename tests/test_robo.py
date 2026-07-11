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
# Finalizar cadastro — SÓ é sucesso se a Hotmart confirmar (nunca mente sucesso)
# ---------------------------------------------------------------------------
class _BtnFake:
    def __init__(self, registro):
        self.registro = registro

    def scroll_into_view_if_needed(self, timeout=0):
        pass

    def click(self, force=False):
        self.registro.append("click_force" if force else "click")

    def dispatch_event(self, ev):
        self.registro.append(f"dispatch:{ev}")


class _TelaFake:
    """Stub mínimo pra exercitar Tela.finalizar_cadastro sem navegador.

    confirma_texto_na: em qual clique o existe_texto passa a retornar True (None = nunca).
    botao_some_apos: após quantos cliques o botão fica invisível (None = nunca some).
    """
    def __init__(self, confirma_texto_na=None, botao_some_apos=None):
        self.confirma_texto_na = confirma_texto_na
        self.botao_some_apos = botao_some_apos
        self.cliques: list[str] = []
        import types
        self.page = types.SimpleNamespace(wait_for_timeout=lambda ms: None)
        self.job = types.SimpleNamespace(log=lambda *a, **k: None)

    def _elemento_visivel(self, chave, timeout=0):
        if self.botao_some_apos is None:
            return True
        return len(self.cliques) < self.botao_some_apos

    def _localizar(self, chave, timeout=0):
        return _BtnFake(self.cliques)

    def existe_texto(self, texto, timeout=0):
        return self.confirma_texto_na is not None and len(self.cliques) >= self.confirma_texto_na


def test_finalizar_confirma_por_mensagem_na_primeira():
    fake = _TelaFake(confirma_texto_na=1)  # msg 'Enviado para aprovação' aparece
    assert robo.Tela.finalizar_cadastro(fake) is True
    assert fake.cliques == ["click"]  # nao precisou escalar


def test_finalizar_confirma_por_botao_sumir():
    # a msg NUNCA aparece, mas o botao some depois do 2o clique = finalizou
    fake = _TelaFake(confirma_texto_na=None, botao_some_apos=2)
    assert robo.Tela.finalizar_cadastro(fake) is True
    assert fake.cliques == ["click", "click_force"]  # sucesso reconhecido no 2o


def test_finalizar_falha_de_verdade_retorna_false():
    # msg nunca aparece E botao nunca some -> falhou mesmo
    fake = _TelaFake(confirma_texto_na=None, botao_some_apos=None)
    assert robo.Tela.finalizar_cadastro(fake) is False
    assert len(fake.cliques) == 3  # tentou as 3 vezes


def test_finalizar_nao_declara_sucesso_sem_clicar():
    # botao ausente desde o inicio (sem nunca clicar) -> NAO pode dizer sucesso
    fake = _TelaFake(confirma_texto_na=None, botao_some_apos=0)
    assert robo.Tela.finalizar_cadastro(fake) is False
    assert fake.cliques == []  # nunca clicou, entao nao inventa sucesso


# ---------------------------------------------------------------------------
# Cronometro por etapa (medicao de onde o tempo vai)
# ---------------------------------------------------------------------------
def test_job_cronometra_cada_etapa(monkeypatch):
    relogio = {"t": 0.0}
    monkeypatch.setattr(robo.time, "monotonic", lambda: relogio["t"])
    job = robo.Job({"id": "p", "titulo_pt": "X"},
                   {"titulo": "T", "descricao": "D", "codigo": "de", "pais": "Alemao"}, "real")

    relogio["t"] = 100.0
    job.marcar_etapa("upload", "subindo...")
    relogio["t"] = 130.0                       # upload durou 30s
    job.marcar_etapa("preco", "preco...")
    relogio["t"] = 135.0                       # preco durou 5s
    resumo = job.resumo_tempos()

    por_etapa = {t["etapa"]: t["segundos"] for t in job.tempos}
    assert por_etapa["upload"] == 30.0
    assert por_etapa["preco"] == 5.0
    # a etapa mais lenta (upload) aparece no topo do resumo
    assert resumo.index("upload") < resumo.index("preco")
    assert "total 0.6 min" in resumo   # 35s = 0.58 -> 0.6


def test_resumo_tempos_vazio_sem_etapas():
    job = robo.Job({"id": "p", "titulo_pt": "X"},
                   {"titulo": "T", "descricao": "D", "codigo": "de", "pais": "Alemao"}, "real")
    assert job.resumo_tempos() == ""


def test_lap_mede_subpassos_e_entra_no_resumo(monkeypatch):
    relogio = {"t": 0.0}
    monkeypatch.setattr(robo.time, "monotonic", lambda: relogio["t"])
    job = robo.Job({"id": "p", "titulo_pt": "X"},
                   {"titulo": "T", "descricao": "D", "codigo": "de", "pais": "Alemao"}, "real")

    relogio["t"] = 10.0
    job.marcar_etapa("coproducao", "...")   # reinicia o lap em t=10
    relogio["t"] = 13.0
    job.lap("select socio")                 # 3s
    relogio["t"] = 25.0
    job.lap("esperar 2fa")                  # 12s
    resumo = job.resumo_tempos()

    subs = {s["nome"]: s["segundos"] for s in job.subtempos}
    assert subs["select socio"] == 3.0
    assert subs["esperar 2fa"] == 12.0
    # os sub-passos aparecem no resumo, na ordem do fluxo
    assert "detalhe dos sub-passos" in resumo
    assert resumo.index("select socio") < resumo.index("esperar 2fa")


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
