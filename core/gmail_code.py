"""Lê o código 2FA da Hotmart direto do Gmail (IMAP + App Password).

Requisitos do lado do usuário (uma vez):
  1. Ativar IMAP no Gmail (Configurações > Encaminhamento e POP/IMAP).
  2. Ter a verificação em 2 etapas ligada e gerar uma "Senha de app"
     (App Password) — https://myaccount.google.com/apppasswords.
     A senha normal do Gmail NÃO funciona no IMAP.
"""
from __future__ import annotations

import email as _email
import imaplib
import re
import time
from email.utils import parsedate_to_datetime

IMAP_HOST = "imap.gmail.com"

# Palavras que costumam aparecer perto do código (pt/en)
_RE_CHAVE = re.compile(
    r"(?:c[oó]digo|chave|seguran[çc]a|verifica\w*|code|token)[^0-9]{0,60}?(\d{6})",
    re.IGNORECASE,
)
_RE_6 = re.compile(r"(?<!\d)(\d{6})(?!\d)")


class GmailError(Exception):
    pass


def extrair_codigo(texto: str | None) -> str | None:
    """Extrai um código de 6 dígitos do texto — prioriza o que está perto de
    palavras como 'código'/'chave'/'segurança'; senão, o primeiro 6-dígitos."""
    if not texto:
        return None
    m = _RE_CHAVE.search(texto)
    if m:
        return m.group(1)
    m = _RE_6.search(texto)
    return m.group(1) if m else None


def _corpo_texto(msg) -> str:
    """Junta o texto do e-mail (plain + html) e tira as tags grosseiramente."""
    partes: list[str] = []
    alvos = msg.walk() if msg.is_multipart() else [msg]
    for p in alvos:
        if p.get_content_type() in ("text/plain", "text/html"):
            try:
                bruto = p.get_payload(decode=True)
                if bruto:
                    partes.append(bruto.decode(p.get_content_charset() or "utf-8", "replace"))
            except Exception:
                continue
    texto = "\n".join(partes)
    return re.sub(r"<[^>]+>", " ", texto)  # remove tags html


def _fetch_imap(email_addr: str, senha: str, desde_ts: float) -> list[str]:
    """Retorna os corpos dos e-mails recentes da Hotmart (mais novos primeiro)."""
    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST)
        M.login(email_addr, senha)
    except imaplib.IMAP4.error as e:
        raise GmailError(
            "Login no Gmail falhou. Confira o e-mail e a SENHA DE APP (App Password) — "
            "a senha normal do Gmail não funciona no IMAP."
        ) from e
    except Exception as e:
        raise GmailError(f"Não consegui conectar no Gmail: {e}") from e

    try:
        M.select("INBOX")
        typ, data = M.search(None, '(FROM "hotmart")')
        ids = data[0].split() if data and data and data[0] else []
        corpos: list[str] = []
        for num in reversed(ids[-15:]):  # 15 mais recentes, do mais novo pro mais velho
            try:
                typ, msgdata = M.fetch(num, "(RFC822)")
                if not msgdata or not msgdata[0]:
                    continue
                msg = _email.message_from_bytes(msgdata[0][1])
                try:  # ignora e-mails antigos (fora da janela) — evita código velho
                    dt = parsedate_to_datetime(msg.get("Date"))
                    if dt and dt.timestamp() < desde_ts - 120:
                        continue
                except Exception:
                    pass
                corpos.append(_corpo_texto(msg))
            except Exception:
                continue
        return corpos
    finally:
        try:
            M.logout()
        except Exception:
            pass


def buscar_codigo(email_addr: str, senha: str, *, desde_ts: float | None = None,
                  timeout: float = 90, intervalo: float = 4, fetch=None) -> str | None:
    """Fica checando o Gmail até achar o código 2FA da Hotmart (ou dar timeout).

    desde_ts: só aceita e-mails a partir desse momento (evita pegar código velho).
    Retorna o código (str) ou None se não achar no tempo.
    """
    if not (email_addr or "").strip() or not (senha or "").strip():
        raise GmailError("Gmail não configurado (falta e-mail ou App Password).")
    fetch = fetch or _fetch_imap
    if desde_ts is None:
        desde_ts = time.time()
    fim = time.time() + timeout
    while True:
        corpos = fetch(email_addr, senha, desde_ts)
        for corpo in corpos:
            cod = extrair_codigo(corpo)
            if cod:
                return cod
        if time.time() >= fim:
            return None
        time.sleep(intervalo)
