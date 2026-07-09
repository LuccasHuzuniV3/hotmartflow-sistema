"""Sobe o FastAPI e abre o HotmartFlow numa janela Chrome em app mode."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import uvicorn

RAIZ = Path(__file__).resolve().parent.parent
os.chdir(RAIZ)
sys.path.insert(0, str(RAIZ))

LOG_PATH = RAIZ / "data" / "launcher.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


class _Tee:
    """Escreve em multiplos streams (terminal + arquivo de log)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False


try:
    log_file = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, log_file) if sys.__stdout__ else log_file
    sys.stderr = _Tee(sys.__stderr__, log_file) if sys.__stderr__ else log_file
except Exception:
    pass

print(f"=== HotmartFlow launcher ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===")


def porta_livre(preferida: int = 7811) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferida))
        s.close()
        return preferida
    except OSError:
        s.close()
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.bind(("127.0.0.1", 0))
        porta = s2.getsockname()[1]
        s2.close()
        return porta


def encontrar_browser() -> tuple[str, str] | None:
    candidatos = [
        ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ("Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ("Chrome", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
        ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ("Edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for nome, caminho in candidatos:
        if os.path.exists(caminho):
            return nome, caminho
    return None


def fechar_chrome_do_profile(perfil: Path):
    """Fecha janelas antigas do app (senao o Chrome reusa a janela com pagina velha)."""
    if os.name != "nt":
        return
    perfil_str = str(perfil).replace("\\", "/").lower()
    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' OR Name='msedge.exe'\" | "
        "Where-Object { $_.CommandLine -and "
        f"  $_.CommandLine.Replace('\\\\','/').ToLower().Contains('{perfil_str}') "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(1.0)
    except Exception as e:
        print(f"[chrome] nao consegui fechar janela antiga: {e}")


def limpar_cache_chrome(perfil: Path):
    """Apaga o cache de paginas do perfil — garante que a UI nova sempre carrega."""
    import shutil
    pastas = [
        perfil / "Default" / "Cache",
        perfil / "Default" / "Code Cache",
        perfil / "Default" / "GPUCache",
        perfil / "Default" / "Service Worker" / "CacheStorage",
        perfil / "Default" / "Service Worker" / "ScriptCache",
        perfil / "ShaderCache",
    ]
    for p in pastas:
        if p.is_dir():
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass


def abrir_em_app_mode(url: str):
    browser = encontrar_browser()
    if browser is None:
        print("Chrome/Edge nao encontrado - abrindo no browser padrao.")
        webbrowser.open(url)
        return
    _, caminho = browser
    perfil = RAIZ / "data" / "browser_profile"
    perfil.mkdir(parents=True, exist_ok=True)
    fechar_chrome_do_profile(perfil)
    limpar_cache_chrome(perfil)
    args = [
        caminho,
        f"--app={url}",
        f"--user-data-dir={perfil}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-component-update",
        "--disable-default-apps",
    ]
    subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)


def aguardar_servidor(url: str, timeout: float = 10.0) -> bool:
    import urllib.request
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    try:
        porta = porta_livre()
        url = f"http://127.0.0.1:{porta}/"
        print(f"HotmartFlow iniciando em {url}")

        def thread_abrir():
            try:
                if aguardar_servidor(url):
                    print("Servidor pronto, abrindo browser...")
                    abrir_em_app_mode(url)
                else:
                    print("Servidor demorou demais - abra manualmente:", url)
            except Exception:
                print("ERRO ao abrir browser:")
                traceback.print_exc()

        threading.Thread(target=thread_abrir, daemon=True).start()
        from app.server import app
        uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
    except Exception:
        print("ERRO FATAL no launcher:")
        traceback.print_exc()
        time.sleep(3)
        raise


if __name__ == "__main__":
    main()
