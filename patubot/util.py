import re
import unicodedata
from datetime import date, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "Mozilla/5.0 (compatible; PatuBot/3.0; +https://github.com/cescgranada/automatitzacio-subvencions)"


def norm(txt: str) -> str:
    """Minúscules sense accents, per comparar textos."""
    txt = unicodedata.normalize("NFD", txt or "")
    return "".join(c for c in txt if unicodedata.category(c) != "Mn").lower()


def clau_titol(txt: str) -> str:
    """Clau per detectar la mateixa convocatòria publicada a dues fonts."""
    return re.sub(r"[^a-z0-9]+", "", norm(txt))[:90]


def parse_data(txt) -> date | None:
    """Accepta 'dd/mm/yyyy', ISO ('2026-10-16T00:00:00.000') o 'yyyy-mm-dd'."""
    if not txt:
        return None
    txt = str(txt).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt[:10], fmt).date()
        except ValueError:
            continue
    return None


def nova_sessio() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s
