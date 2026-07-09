"""Cliente do agy / Antigravity CLI via subprocess — portado do EbookFlow.

O agy usa a conta Google (AI Ultra) — sem custo por chamada, igual ao fluxo
que ja funciona no EbookFlow. Mantém as mesmas protecoes aprendidas la:

  - Modo WSL (HOTMARTFLOW_USE_WSL=1): contorna o bug do agy.exe Windows que
    escreve direto no console e ignora redirect de stdout.
  - Mata a ARVORE inteira de processos em timeout (node.exe spawna filhos;
    orfaos acumulam ate estourar EMFILE).
  - Detecta quota esgotada e aborta SEM retry (retry so empilha zumbi).
  - Retry no maximo 1x e SO em timeout.
  - Fallback pro binario `gemini` legado se o agy nao existir.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.llm import LLMError


def _usar_wsl() -> bool:
    if os.name != "nt":
        return False
    return os.environ.get("HOTMARTFLOW_USE_WSL", "").strip().lower() in ("1", "true", "yes")


def _achar_wsl_exe() -> Optional[str]:
    p = shutil.which("wsl.exe") or shutil.which("wsl")
    if p:
        return p
    candidato = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "wsl.exe"
    if candidato.is_file():
        return str(candidato)
    return None


# Cache do path absoluto do agy dentro do WSL (wsl.exe -- nao carrega .bashrc,
# entao $HOME/.local/bin nao esta no PATH — descobrimos via login shell 1x).
_AGY_WSL_PATH: Optional[str] = None


def _achar_agy_no_wsl(wsl_exe: str) -> str:
    global _AGY_WSL_PATH
    if _AGY_WSL_PATH:
        return _AGY_WSL_PATH

    try:
        proc = subprocess.run(
            [wsl_exe, "--", "bash", "-lc", "which agy"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        for linha in (proc.stdout or "").splitlines():
            linha = linha.strip()
            if linha.startswith("/") and "agy" in linha:
                _AGY_WSL_PATH = linha
                return linha
    except Exception:
        pass

    for tentativa in ("$HOME/.local/bin/agy", "/usr/local/bin/agy", "/usr/bin/agy"):
        try:
            proc = subprocess.run(
                [wsl_exe, "--", "bash", "-lc", f"test -x {tentativa} && echo {tentativa}"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            saida = (proc.stdout or "").strip()
            if proc.returncode == 0 and saida:
                if "$HOME" in saida:
                    home_proc = subprocess.run(
                        [wsl_exe, "--", "bash", "-lc", "echo $HOME"],
                        capture_output=True, text=True, timeout=5,
                        encoding="utf-8", errors="replace",
                    )
                    home = (home_proc.stdout or "").strip()
                    if home:
                        saida = saida.replace("$HOME", home)
                _AGY_WSL_PATH = saida
                return saida
        except Exception:
            continue

    raise LLMError(
        "Nao achei 'agy' dentro do WSL. Confirme com: wsl -- bash -lc \"which agy\" "
        "no PowerShell. Se nao retornar nada, instale: "
        "curl -fsSL https://antigravity.google/cli/install.sh | bash"
    )


def _achar_cli() -> Optional[str]:
    """Acha o binario: WSL (se ativado) > agy nativo > gemini legado."""
    if _usar_wsl():
        return _achar_wsl_exe()
    for nome in ("agy.cmd", "agy.exe", "agy"):
        p = shutil.which(nome)
        if p:
            return p
    candidatos_agy = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "agy.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "agy",
        Path.home() / "AppData" / "Roaming" / "npm" / "agy.cmd",
        Path.home() / ".npm-global" / "bin" / "agy",
    ]
    for c in candidatos_agy:
        if c.is_file():
            return str(c)
    for nome in ("gemini.cmd", "gemini"):
        p = shutil.which(nome)
        if p:
            return p
    candidatos_gem = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "gemini.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "gemini",
    ]
    for c in candidatos_gem:
        if c.is_file():
            return str(c)
    return None


def _eh_agy(bin_path: str) -> bool:
    return Path(bin_path).stem.lower() == "agy"


def _matar_arvore(proc: subprocess.Popen) -> None:
    """Mata processo + TODA a arvore de filhos (node.exe orfao vira zumbi)."""
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=10, shell=False,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except (ProcessLookupError, PermissionError):
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    for stream in (getattr(proc, "stdin", None), getattr(proc, "stdout", None),
                   getattr(proc, "stderr", None)):
        try:
            if stream is not None and not stream.closed:
                stream.close()
        except Exception:
            pass


def _eh_erro_quota(stderr_text: str) -> bool:
    t = stderr_text.lower()
    return any(s in t for s in (
        "exhausted your capacity", "exhausted capacity", "quota will reset",
        "resource_exhausted", "rate limit", "rate_limit", "429", "quota exceeded",
    ))


def _eh_erro_emfile(stderr_text: str) -> bool:
    t = stderr_text.lower()
    return "emfile" in t or "too many open files" in t


def _invocar(prompt: str, model: str, timeout: float = 120.0, _tentativa: int = 1) -> str:
    bin_path = _achar_cli()
    if not bin_path:
        raise LLMError(
            "Nenhum CLI compativel encontrado (procurei: agy, gemini). "
            "Instale com: npm install -g antigravity"
        )

    env = {**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"}
    usar_wsl = _usar_wsl()
    if usar_wsl:
        agy_abs = _achar_agy_no_wsl(bin_path)
        cmd = [bin_path, "--", agy_abs, "--dangerously-skip-permissions"]
        if model:
            cmd.extend(["--model", model])
    elif _eh_agy(bin_path):
        cmd = [bin_path, "-p", "--print-timeout", "10m", "--dangerously-skip-permissions"]
        if model:
            cmd.extend(["--model", model])
    else:
        cmd = [bin_path, "-m", model or "gemini-2.5-flash",
               "--output-format", "json", "--skip-trust"]

    popen_kwargs = {
        "stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
        "env": env, "encoding": "utf-8", "errors": "replace", "shell": False,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    prompt_stdin = prompt if prompt.endswith("\n") else prompt + "\n"

    proc = None
    stdout = ""
    stderr = ""
    rc = -1
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            stdout, stderr = proc.communicate(input=prompt_stdin, timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            _matar_arvore(proc)
            proc = None
            if _tentativa < 2:
                return _invocar(prompt, model, timeout=timeout * 1.3, _tentativa=_tentativa + 1)
            raise LLMError(
                f"agy demorou mais que {timeout:.0f}s mesmo apos retry. "
                "Provavel quota esgotada. Tente relogar o agy (agy auth) ou aguarde o reset."
            )
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Erro invocando o agy: {e}") from e
    finally:
        if proc is not None and proc.poll() is None:
            _matar_arvore(proc)

    if rc != 0:
        stderr_text = (stderr or "").strip()[:1000]
        if _eh_erro_quota(stderr_text):
            raise LLMError(
                "Quota do agy/Gemini esgotada. Solucoes: (a) relogar com outra conta, "
                "(b) esperar o reset diario. "
                f"Detalhe: {stderr_text[:200]}"
            )
        if _eh_erro_emfile(stderr_text):
            raise LLMError(
                "Erro EMFILE (processos node.exe zumbis acumulados). "
                "Rode 'taskkill /F /IM node.exe' no PowerShell ou reinicie o PC. "
                f"Detalhe: {stderr_text[:200]}"
            )
        if "auth" in stderr_text.lower() or "login" in stderr_text.lower():
            raise LLMError(
                "O agy precisa autenticar. Roda 'agy' no terminal (ou dentro do WSL) "
                "uma vez pra fazer login com a conta Google."
            )
        raise LLMError(f"agy falhou (exit {rc}): {stderr_text}")

    stdout = stdout or ""
    if usar_wsl or _eh_agy(bin_path):
        resp = stdout.strip()
        if not resp:
            raise LLMError(
                f"agy retornou resposta vazia (exit={rc}). "
                f"Stderr: {(stderr or '').strip()[:300]!r}. "
                "DICA: se passou --model, confirme o nome com 'agy models'."
            )
        return resp

    # caminho legado (gemini-cli antigo, JSON wrapper)
    json_match = re.search(r"\{[\s\S]*\}\s*$", stdout)
    if not json_match:
        raise LLMError(f"Resposta sem JSON: {stdout[:300]}")
    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON do gemini-cli invalido: {e}\n{stdout[:300]}")
    resp = (data.get("response") or "").strip()
    if not resp:
        raise LLMError(f"Resposta vazia. Raw: {json.dumps(data)[:300]}")
    return resp


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def gerar(system: str, prompt: str, model: str) -> str:
    """Gera texto via agy. CLI nao tem system separado — concatena na frente."""
    completo = f"{system}\n\n{prompt}" if system else prompt
    return _invocar(completo, model or "")


def diagnostico() -> dict:
    """Verifica se o CLI esta disponivel (so descoberta de binario — rapido)."""
    if _usar_wsl():
        wsl = _achar_wsl_exe()
        if not wsl:
            return {"disponivel": False, "tipo": "",
                    "detalhe": "Modo WSL ativado mas wsl.exe nao encontrado"}
        return {"disponivel": True, "tipo": "agy (WSL)", "detalhe": wsl}
    bin_path = _achar_cli()
    if not bin_path:
        return {"disponivel": False, "tipo": "",
                "detalhe": "agy nao encontrado — instale: npm install -g antigravity"}
    tipo = "agy" if _eh_agy(bin_path) else "gemini-cli (legado)"
    return {"disponivel": True, "tipo": tipo, "detalhe": bin_path}
