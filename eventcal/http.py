from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

UA = "philly-events-digest/1.0 (+https://github.com/maxsg/philly-events)"


def get(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r


def html_to_text(html: str, base_url: str = "") -> str:
    """Readable text with links kept inline as [text](href) so a model can cite URLs."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav", "form"]):
        t.decompose()
    for a in soup.find_all("a", href=True):
        href = requests.compat.urljoin(base_url, a["href"])
        label = a.get_text(" ", strip=True)
        if label and href.startswith("http"):
            a.replace_with(f"[{label}]({href})")
    text = soup.get_text("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    out, blank = [], False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()
