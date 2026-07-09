"""Robo de publicacao na Hotmart (Fase B).

Arquitetura:
  - Job: maquina de estados de UMA publicacao (1 produto x 1 idioma), com as
    pausas humanas embutidas (codigo 2FA da coproducao e confirmacao final).
  - So existe 1 job ativo por vez (1 navegador, 1 operador).
  - 3 modos:
      "real"     -> faz o cadastro completo na Hotmart (para antes de Finalizar,
                    que so acontece com confirmacao humana pela UI).
      "ensaio"   -> abre a Hotmart, preenche a 1a tela e PARA sem avancar nada.
                    Serve pra calibrar seletores sem risco.
      "simulado" -> nao abre navegador; percorre as etapas com delays. Serve
                    pra testar a UI e treinar o operador.

Regras de seguranca (decisoes de projeto — nao relaxar):
  - NUNCA clica "Finalizar Cadastro" sem job.aguardar_confirmacao() liberado.
  - Codigo 2FA da coproducao e SEMPRE humano (digitado na UI do app).
  - Antes de convidar coprodutor, checa se ja existe convite Pendente.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from core import produtos
from core import hotmart_map as hm

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PERFIL = RAIZ / "data" / "hotmart_profile"
PASTA_PUBLICACOES = RAIZ / "data" / "publicacoes"
PORTA_CDP = 9222  # porta de controle do Chrome do robo (conecta na janela ja aberta)

ESTADOS_ATIVOS = ("iniciando", "rodando", "aguardando_2fa", "aguardando_confirmacao")
MODOS = ("real", "ensaio", "simulado")

# Delay entre etapas do modo simulado (env pra acelerar nos testes)
_DELAY_SIMULADO = float(os.environ.get("HOTMARTFLOW_SIM_DELAY", "0.8"))


class RoboError(Exception):
    pass


class CanceladoError(Exception):
    pass


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
class Job:
    def __init__(self, produto: dict, item: dict, modo: str):
        self.produto_id = produto["id"]
        self.titulo = item["titulo"] or produto["titulo_pt"]
        self.codigo_idioma = item["codigo"]
        self.pais = item["pais"]
        self.modo = modo
        self.estado = "iniciando"
        self.etapa = ""
        self.mensagens: list[dict] = []
        self.iniciado_em = datetime.now().isoformat(timespec="seconds")
        self._codigo_2fa: str | None = None
        self._evento_codigo = threading.Event()
        self._evento_confirmacao = threading.Event()
        self._cancelado = False

    # ---- log / snapshot -------------------------------------------------
    def log(self, texto: str, nivel: str = "info") -> None:
        self.mensagens.append({
            "hora": datetime.now().strftime("%H:%M:%S"),
            "texto": texto,
            "nivel": nivel,
        })

    def snapshot(self) -> dict:
        return {
            "produto_id": self.produto_id,
            "titulo": self.titulo,
            "codigo_idioma": self.codigo_idioma,
            "pais": self.pais,
            "modo": self.modo,
            "estado": self.estado,
            "etapa": self.etapa,
            "mensagens": self.mensagens[-40:],
            "iniciado_em": self.iniciado_em,
        }

    # ---- pausas humanas --------------------------------------------------
    def aguardar_codigo(self, timeout: float = 900.0) -> str:
        """Pausa ate o operador colar o codigo 2FA na UI do app."""
        self.estado = "aguardando_2fa"
        self.log("Aguardando código de verificação (chegou no Gmail) — cole na tela.", "pausa")
        if not self._evento_codigo.wait(timeout):
            raise RoboError("Tempo esgotado esperando o código de verificação.")
        self._evento_codigo.clear()
        self._checar_cancelamento()
        self.estado = "rodando"
        return self._codigo_2fa or ""

    def aguardar_confirmacao(self, timeout: float = 900.0) -> None:
        """Pausa ate o operador confirmar a finalizacao na UI do app."""
        self.estado = "aguardando_confirmacao"
        self.log("Tudo pronto. Confirme na tela pra finalizar o cadastro.", "pausa")
        if not self._evento_confirmacao.wait(timeout):
            raise RoboError("Tempo esgotado esperando a confirmação final.")
        self._evento_confirmacao.clear()
        self._checar_cancelamento()
        self.estado = "rodando"

    # ---- controles chamados pela API --------------------------------------
    def entregar_codigo(self, codigo: str) -> None:
        if self.estado != "aguardando_2fa":
            raise RoboError("O robô não está esperando código agora.")
        self._codigo_2fa = (codigo or "").strip()
        self._evento_codigo.set()

    def confirmar(self) -> None:
        if self.estado != "aguardando_confirmacao":
            raise RoboError("O robô não está esperando confirmação agora.")
        self._evento_confirmacao.set()

    def cancelar(self) -> None:
        self._cancelado = True
        self.log("Cancelamento solicitado pelo operador.", "aviso")
        # destrava qualquer pausa em andamento
        self._evento_codigo.set()
        self._evento_confirmacao.set()

    def _checar_cancelamento(self) -> None:
        if self._cancelado:
            raise CanceladoError()

    def marcar_etapa(self, etapa: str, texto: str) -> None:
        self._checar_cancelamento()
        self.etapa = etapa
        self.log(texto)


# ---------------------------------------------------------------------------
# Registro global (1 job por vez — 1 navegador, 1 operador)
# ---------------------------------------------------------------------------
_TRAVA = threading.Lock()
_JOB: Job | None = None


def job_atual() -> Job | None:
    return _JOB


def iniciar(produto_id: str, codigo_idioma: str, modo: str) -> Job:
    global _JOB
    if modo not in MODOS:
        raise RoboError(f"Modo inválido: '{modo}' (use real, ensaio ou simulado)")

    with _TRAVA:
        if _JOB is not None and _JOB.estado in ESTADOS_ATIVOS:
            raise RoboError(
                "Já existe uma publicação em andamento. "
                "Aguarde terminar (ou cancele) antes de iniciar outra."
            )

        produto = produtos.obter(produto_id)
        item = next((i for i in produto["idiomas"] if i["codigo"] == codigo_idioma), None)
        if item is None:
            raise RoboError(f"Idioma '{codigo_idioma}' não existe nesse produto.")
        _validar_item(produto, item, modo)

        job = Job(produto, item, modo)
        _JOB = job

    produtos.atualizar_item(produto_id, codigo_idioma, {"status": "publicando", "erro": ""})
    threading.Thread(target=_rodar, args=(job, produto, item), daemon=True).start()
    return job


def _validar_item(produto: dict, item: dict, modo: str) -> None:
    if item["status"] == "publicado":
        raise RoboError(f"{item['pais']}: já está publicado.")
    if item["status"] != "revisado":
        raise RoboError(
            f"{item['pais']}: precisa estar 'revisado' pra publicar (está '{item['status']}')."
        )
    if not (item["titulo"] or "").strip() or not (item["descricao"] or "").strip():
        raise RoboError(f"{item['pais']}: título/descrição vazios.")
    if modo == "simulado":
        return  # simulado nao toca em arquivo nenhum
    if not item.get("pdf") or not Path(item["pdf"]).is_file():
        raise RoboError(f"{item['pais']}: PDF não encontrado em {item.get('pdf')!r}.")
    if modo == "real" and (not item.get("capa") or not Path(item["capa"]).is_file()):
        raise RoboError(f"{item['pais']}: capa não encontrada — obrigatória pra publicar de verdade.")
    for anexo in item.get("anexos", []):
        if not anexo.get("pdf") or not Path(anexo["pdf"]).is_file():
            raise RoboError(f"{item['pais']}: anexo '{anexo.get('nome')}' sem PDF em {anexo.get('pdf')!r}.")


def _rodar(job: Job, produto: dict, item: dict) -> None:
    try:
        if job.modo == "simulado":
            _executar_simulado(job)
        else:
            _executar_navegador(job, produto, item)
        job.estado = "concluido"
        if job.modo == "real":
            produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "publicado"})
            job.log("Publicado com sucesso ✔", "ok")
        else:
            produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "revisado"})
            job.log(f"Modo {job.modo} concluído — nada foi enviado de verdade.", "ok")
    except CanceladoError:
        job.estado = "cancelado"
        produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "revisado"})
        job.log("Publicação cancelada. Nada foi finalizado.", "aviso")
    except Exception as e:  # RoboError, Playwright, IO... — tudo vira erro legivel
        job.estado = "erro"
        msg = str(e)[:400]
        job.log(f"ERRO: {msg}", "erro")
        try:
            produtos.atualizar_item(job.produto_id, job.codigo_idioma,
                                    {"status": "erro", "erro": msg})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Executor SIMULADO (sem navegador — testa UI e treina operador)
# ---------------------------------------------------------------------------
def _executar_simulado(job: Job) -> None:
    passos = [
        ("abrir", "Abrindo a Hotmart (simulado)..."),
        ("criar_produto", "Criando produto tipo eBook (simulado)..."),
        ("informacoes_basicas", "Preenchendo nome, descrição, idioma, país, capa e categoria (simulado)..."),
        ("preco", "Definindo moeda e preço (simulado)..."),
        ("conteudo", "Subindo o PDF (simulado)..."),
    ]
    job.estado = "rodando"
    for etapa, texto in passos:
        job.marcar_etapa(etapa, texto)
        time.sleep(_DELAY_SIMULADO)

    job.marcar_etapa("coproducao", "Convidando coprodutor (simulado)...")
    codigo = job.aguardar_codigo()
    job.log(f"Código recebido ({codigo[:2]}****) — convite enviado (simulado).")
    time.sleep(_DELAY_SIMULADO)

    job.marcar_etapa("finalizar", "Todas as etapas verdes (simulado).")
    job.aguardar_confirmacao()
    job.log("Finalizar Cadastro clicado (simulado).")
    time.sleep(_DELAY_SIMULADO)


# ---------------------------------------------------------------------------
# Executor de NAVEGADOR (real e ensaio) — Playwright + mapa de seletores
# ---------------------------------------------------------------------------
class Tela:
    """Wrapper fino do Playwright: acha elementos pelo MAPA e tira screenshots."""

    def __init__(self, page, job: Job, pasta_shots: Path):
        self.page = page
        self.job = job
        self.pasta = pasta_shots
        self._n = 0

    def shot(self, nome: str) -> None:
        self._n += 1
        try:
            self.page.screenshot(path=str(self.pasta / f"{self._n:02d}_{nome}.png"),
                                 full_page=False)
        except Exception:
            pass  # screenshot nunca derruba o fluxo

    def _localizar(self, chave: str):
        import re
        candidatos = hm.MAPA[chave]
        for c in candidatos:
            try:
                if c["tipo"] == "role":
                    loc = self.page.get_by_role(c["role"], name=re.compile(c["nome"], re.I))
                elif c["tipo"] == "texto":
                    loc = self.page.get_by_text(re.compile(c["texto"], re.I))
                elif c["tipo"] == "label":
                    loc = self.page.get_by_label(re.compile(c["texto"], re.I))
                elif c["tipo"] == "placeholder":
                    loc = self.page.get_by_placeholder(re.compile(c["texto"], re.I))
                else:
                    loc = self.page.locator(c["css"])
                loc.first.wait_for(state="visible", timeout=4000)
                return loc.first
            except Exception:
                continue
        self.shot(f"erro_{chave}")
        raise RoboError(
            f"Não achei '{chave}' na tela da Hotmart. "
            f"Print salvo em data/publicacoes. Corrija o seletor em core/hotmart_map.py."
        )

    def clicar(self, chave: str) -> None:
        self._localizar(chave).click()

    def preencher(self, chave: str, valor: str) -> None:
        campo = self._localizar(chave)
        campo.click()
        campo.fill(valor)

    def escolher_opcao(self, chave_campo: str, texto_opcao: str) -> None:
        """Dropdowns da Hotmart: clica no campo, digita e escolhe a opcao."""
        import re
        campo = self._localizar(chave_campo)
        campo.click()
        try:
            campo.fill(texto_opcao)
        except Exception:
            pass  # alguns dropdowns nao aceitam digitacao
        opcao = self.page.get_by_text(re.compile(re.escape(texto_opcao), re.I))
        opcao.first.wait_for(state="visible", timeout=8000)
        opcao.first.click()

    def upload(self, chave: str, arquivos: str | list[str]) -> None:
        if isinstance(arquivos, str):
            arquivos = [arquivos]
        self.page.locator(hm.MAPA[chave][0]["css"]).first.set_input_files(arquivos)

    def existe_texto(self, texto: str, timeout: float = 3000) -> bool:
        import re
        try:
            self.page.get_by_text(re.compile(re.escape(texto), re.I)).first.wait_for(
                state="visible", timeout=timeout)
            return True
        except Exception:
            return False


URL_CDP = f"http://127.0.0.1:{PORTA_CDP}"


def _chrome_exe() -> str | None:
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return None


def _cdp_ativo() -> bool:
    """A janela de controle do Chrome ja esta no ar (porta de depuracao respondendo)?"""
    import urllib.request
    try:
        with urllib.request.urlopen(URL_CDP + "/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _matar_chrome_do_perfil() -> None:
    """Fecha um Chrome antigo que esteja usando o perfil do robo SEM a porta de
    depuracao (senao o novo launch vira 'singleton' sem porta e o connect falha)."""
    if os.name != "nt":
        return
    perfil_str = str(PASTA_PERFIL).replace("\\", "/").lower()
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' OR Name='msedge.exe'\" | "
        "Where-Object { $_.CommandLine -and "
        f"  $_.CommandLine.Replace('\\\\','/').ToLower().Contains('{perfil_str}') "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(1.0)
    except Exception:
        pass


def garantir_chrome(url: str | None = None) -> None:
    """Garante que existe UMA janela do Chrome do robo aberta com a porta de
    controle (perfil proprio data/hotmart_profile). Se ja estiver aberta, reusa.
    O login feito nessa janela vale pra todas as publicacoes (mesma janela)."""
    if _cdp_ativo():
        return
    exe = _chrome_exe()
    if not exe:
        raise RoboError("Não encontrei o Chrome/Edge instalado.")
    _matar_chrome_do_perfil()
    PASTA_PERFIL.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={PORTA_CDP}",
        f"--user-data-dir={PASTA_PERFIL}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--profile-directory=Default",
    ]
    if url:
        args.append(url)
    subprocess.Popen(args, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    # espera a porta de controle subir (ate ~15s)
    for _ in range(30):
        if _cdp_ativo():
            return
        time.sleep(0.5)
    raise RoboError("O Chrome do robô não subiu a tempo. Tente de novo.")


def _conectar(p):
    """Conecta na janela do Chrome ja aberta (CDP) e devolve (browser, page)."""
    if not _cdp_ativo():
        raise RoboError(
            "A janela do robô não está aberta. Clique em 'Abrir Hotmart (login)', "
            "faça o login e DEIXE a janela aberta — o robô usa ela pra publicar."
        )
    browser = p.chromium.connect_over_cdp(URL_CDP)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return browser, page


def _executar_navegador(job: Job, produto: dict, item: dict) -> None:
    from playwright.sync_api import sync_playwright

    from core import config as cfg
    s = cfg.carregar_settings()
    ensaio = job.modo == "ensaio"

    pasta_shots = PASTA_PUBLICACOES / job.produto_id / job.codigo_idioma
    pasta_shots.mkdir(parents=True, exist_ok=True)

    job.estado = "rodando"
    with sync_playwright() as p:
        browser, page = _conectar(p)  # conecta na janela ja aberta e logada
        try:
            page.set_default_timeout(20000)
            tela = Tela(page, job, pasta_shots)

            # ---- 1. abrir direto o formulario de eBook novo + checar login ----
            job.marcar_etapa("abrir", "Abrindo o formulário de eBook novo na Hotmart...")
            page.goto(hm.URL_CRIAR_EBOOK, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            # rede de seguranca: se caiu no login (com dados ja preenchidos), entra sozinho
            if any(m in page.url for m in hm.MARCADORES_LOGIN):
                job.log("Caiu na tela de login — tentando entrar (dados já preenchidos)...", "aviso")
                try:
                    tela.clicar("btn_entrar_login")
                    page.wait_for_timeout(4000)
                    page.goto(hm.URL_CRIAR_EBOOK, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                except RoboError:
                    pass
            if any(m in page.url for m in hm.MARCADORES_LOGIN):
                tela.shot("erro_login")
                raise RoboError(
                    "Ainda está na tela de login. Vá na janela do robô (já aberta), "
                    "faça o login na Hotmart e clique publicar de novo."
                )
            tela.shot("inicio")

            # ---- 2. informacoes basicas (ja estamos nela) ------------------
            job.marcar_etapa("informacoes_basicas", "Preenchendo informações básicas...")
            tela.preencher("campo_nome", item["titulo"])
            tela.preencher("campo_descricao", item["descricao"])
            tela.escolher_opcao("campo_idioma", hm.IDIOMA_HOTMART[item["codigo"]])
            tela.escolher_opcao("campo_pais", hm.PAIS_HOTMART[item["codigo"]])
            # imagens: capa do produto + imagens dos anexos (bonus/extras) juntas
            imagens = []
            if item.get("capa") and Path(item["capa"]).is_file():
                imagens.append(item["capa"])
            for anexo in item.get("anexos", []):
                if anexo.get("capa") and Path(anexo["capa"]).is_file():
                    imagens.append(anexo["capa"])
            if imagens:
                tela.upload("input_capa", imagens)
                job.log(f"{len(imagens)} imagem(ns) enviada(s) nas informações básicas.")
                page.wait_for_timeout(2000)
            tela.escolher_opcao("campo_categoria", s["hotmart"]["categoria"])
            tela.shot("basico_preenchido")

            if ensaio:
                job.log("ENSAIO: primeira tela preenchida. Parando aqui sem clicar em nada "
                        "que avance — confira os prints em data/publicacoes.", "ok")
                return

            tela.clicar("btn_avancar_basico")
            page.wait_for_timeout(2500)

            # ---- 4. preco ---------------------------------------------------
            job.marcar_etapa("preco", f"Definindo preço: USD {item['preco']:.2f}...")
            tela.escolher_opcao("campo_moeda", "Dólar")
            valor = f"{item['preco']:.2f}".replace(".", ",")
            tela.preencher("campo_valor", valor)
            tela.shot("preco")
            tela.clicar("btn_salvar_continuar")
            page.wait_for_timeout(2500)

            # ---- 5. conteudo (PDF principal + anexos) ------------------------
            anexos_pdf = [a["pdf"] for a in item.get("anexos", [])
                          if a.get("pdf") and Path(a["pdf"]).is_file()]
            pdfs = [item["pdf"]] + anexos_pdf
            job.marcar_etapa("conteudo",
                             f"Subindo {len(pdfs)} PDF(s): principal"
                             + (f" + {len(anexos_pdf)} anexo(s)" if anexos_pdf else "") + "...")
            tela.clicar("menu_conteudo")
            page.wait_for_timeout(1500)
            tela.upload("input_pdf", pdfs)
            nome_pdf = Path(item["pdf"]).name
            job.log(f"Upload iniciado — aguardando '{nome_pdf}' concluir...")
            if not tela.existe_texto(nome_pdf, timeout=300_000):
                raise RoboError("Upload do PDF não concluiu em 5 minutos.")
            tela.shot("pdf_enviado")

            # ---- 6. coproducao ----------------------------------------------
            coprod = s["coproducao"]
            if (coprod.get("email") or "").strip():
                job.marcar_etapa("coproducao", f"Coprodução: {coprod['email']} ({coprod['percentual']}%)...")
                tela.clicar("menu_coproducao")
                page.wait_for_timeout(2000)
                if tela.existe_texto(coprod["email"]) and tela.existe_texto("Pendente"):
                    job.log("Já existe convite Pendente pra esse coprodutor — pulando (evita duplicar).", "aviso")
                else:
                    tela.clicar("btn_convidar_coprodutor")
                    page.wait_for_timeout(1500)
                    tela.preencher("campo_email_coprodutor", coprod["email"])
                    tela.clicar("opcao_socio_produtor")
                    tela.preencher("campo_percentual", str(coprod["percentual"]))
                    tela.clicar("check_termos")
                    tela.shot("coproducao_preenchida")
                    tela.clicar("btn_enviar_convite")
                    codigo = job.aguardar_codigo()
                    tela.preencher("campo_codigo_2fa", codigo)
                    tela.clicar("btn_enviar_codigo")
                    page.wait_for_timeout(3000)
                    tela.shot("coproducao_enviada")
                    if tela.existe_texto("erro", timeout=2000):
                        job.log("A Hotmart acusou erro na verificação do convite — o convite pode ter "
                                "entrado como Pendente mesmo assim (confira depois). Seguindo em frente.", "aviso")
            else:
                job.log("Sem coprodutor configurado — etapa pulada.")

            # ---- 7. finalizar (pausa humana obrigatoria) ---------------------
            job.marcar_etapa("finalizar", "Voltando ao Painel do produto...")
            tela.clicar("menu_painel")
            page.wait_for_timeout(2000)
            tela.shot("painel_final")
            job.aguardar_confirmacao()
            tela.clicar("btn_finalizar_cadastro")
            if not tela.existe_texto("Enviado para aprovação", timeout=15000):
                job.log("Não vi a mensagem 'Enviado para aprovação' — confira o print final.", "aviso")
            tela.shot("finalizado")
        finally:
            # NAO fecha a janela — ela fica aberta e logada pra proxima publicacao.
            # O Chrome foi aberto por nos (subprocess), fora do Playwright; ao sair
            # do 'with sync_playwright' so o controle CDP e desconectado.
            pass


# ---------------------------------------------------------------------------
# Janela de login (primeira configuracao do perfil)
# ---------------------------------------------------------------------------
def abrir_login() -> None:
    """Abre (ou reusa) a janela do Chrome do robo na Hotmart pro operador logar.
    A janela FICA ABERTA — o robo se conecta nela na hora de publicar, entao o
    login vale pra todas as publicacoes (mesma janela, sem relogar)."""
    global _JOB
    with _TRAVA:
        if _JOB is not None and _JOB.estado in ESTADOS_ATIVOS:
            raise RoboError("Tem uma publicação em andamento — feche antes de abrir o login.")
    garantir_chrome(hm.URL_APP)
