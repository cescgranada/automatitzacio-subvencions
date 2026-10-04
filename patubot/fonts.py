"""Recollida de convocatòries. Cada font retorna una llista d'ítems:
{"id", "titol", "font", "link", "context", "termini_data"}.
Si una font falla, llança una excepció (el cridador la registra: mai en silenci)."""
import os
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config
from .util import clau_titol, norm, parse_data

SOCRATA = "https://analisi.transparenciacatalunya.cat/resource"
BOE_SUMARI = "https://www.boe.es/datosabiertos/api/boe/sumario/{}"
SCRAPINGBEE = "https://app.scrapingbee.com/api/v1/"


# ------------------------------------------------------------------ RAISC
def _termini_raisc(r: dict) -> date | None:
    return parse_data(r.get("data_fi_termini_presentaci_sol_licitud")) or parse_data(r.get("data_fi_presentaci_sol"))


def admet_raisc(r: dict, avui: date) -> bool:
    """Filtre determinista: només el que té sentit per a una escola de Barcelona."""
    entitat = norm(r.get("entitat_oo_aa_o_departament_1"))
    admin = norm(r.get("administraci_"))
    if "comarca" in admin:
        return False
    if ("municipi" in admin or "provincia" in admin) and "barcelona" not in entitat:
        return False

    regions = [x.strip() for x in (r.get("regio_apli") or "").split(";") if x.strip()]
    if regions and not any(x in ("CATALUNYA", "BARCELONA", "ESPANYA", "TOT EL MON") for x in regions):
        return False

    beneficiaris = norm(r.get("tipus_de_beneficiaris"))
    if beneficiaris and not any(b in beneficiaris for b in config.BENEFICIARIS_VALIDS):
        return False

    if any(f in norm(r.get("finalitat_publica")) for f in config.FINALITATS_EXCLOSES):
        return False

    fi = _termini_raisc(r)
    return not (fi and fi < avui)


def item_raisc(r: dict) -> dict:
    fi = _termini_raisc(r)
    titol = (r.get("t_tol_convocat_ria_catal") or r.get("t_tol_convocat_ria_castell") or "").strip()
    objecte = (r.get("objecte_de_la_convocat_ria") or "").strip()
    link = r.get("url_diari_oficial") or r.get("url_catala_bases_reg") or r.get("seu_electr_nica") or ""
    parts = [
        f"Entitat: {r.get('entitat_oo_aa_o_departament_1') or '?'}",
        f"Finalitat: {r.get('finalitat_publica') or '?'}",
        f"Beneficiaris: {r.get('tipus_de_beneficiaris') or '?'}",
        f"Import: {r.get('import_total_convocat_ria') or '?'} EUR",
        f"Termini: {fi.isoformat() if fi else (r.get('data_fi_presentaci_sol') or 'desconegut')}",
    ]
    if objecte and objecte[:60] != titol[:60]:
        parts.append(f"Objecte: {objecte[:300]}")
    return {
        "id": "raisc:" + (r.get("codi_raisc") or clau_titol(titol)),
        "titol": titol[:250],
        "font": "RAISC (Generalitat/locals)",
        "link": link,
        "context": " | ".join(parts),
        "termini_data": fi.isoformat() if fi else None,
    }


def fonts_raisc(sessio, avui: date) -> list[dict]:
    desde = (avui - timedelta(days=config.DIES_FINESTRA)).isoformat()
    r = sessio.get(f"{SOCRATA}/khxn-nv6a.json", timeout=90, params={
        "$where": f"data_diari_oficial >= '{desde}T00:00:00'",
        "$order": "data_diari_oficial DESC",
        "$limit": 5000,
    })
    r.raise_for_status()
    return [item_raisc(x) for x in r.json() if admet_raisc(x, avui)]


# ------------------------------------------------------------------ CIDO
def fonts_cido(sessio, avui: date) -> list[dict]:
    """Convocatòries amb termini obert d'entitats de Barcelona (Ajuntament, Diputació, AMB, consorcis)."""
    desde = (avui - timedelta(days=config.DIES_FINESTRA)).isoformat()
    r = sessio.get(f"{SOCRATA}/3gku-b36y.json", timeout=90, params={
        "$where": f"estat = 'Termini obert' AND data_pub >= '{desde}T00:00:00'",
        "$order": "data_pub DESC",
        "$limit": 2000,
    })
    r.raise_for_status()
    items = []
    for x in r.json():
        if "barcelona" not in norm(x.get("nom_ens")):
            continue
        link = (x.get("enlla") or {}).get("url", "")
        items.append({
            "id": "cido:" + link,
            "titol": (x.get("resum") or "")[:250],
            "font": "CIDO (Diputació de Barcelona)",
            "link": link,
            "context": f"Entitat: {x.get('nom_ens')} | Publicada: {(x.get('data_pub') or '')[:10]} | Termini obert",
            "termini_data": None,
        })
    return items


# ------------------------------------------------------------------ BOE
PARAULES_BOE = ("subvenci", "ayuda", "convoca", "bases reguladoras", "premio", "beca", "concurso")
SECCIONS_BOE = {"3", "5", "5A", "5B", "5C"}


def _camina_boe(node, seccio="", dept="", out=None):
    """Recorre el JSON del sumari (l'estructura alterna dict/llista) i recull els ítems."""
    out = [] if out is None else out
    if isinstance(node, list):
        for n in node:
            _camina_boe(n, seccio, dept, out)
    elif isinstance(node, dict):
        if "identificador" in node and "titulo" in node:
            out.append({"seccio": seccio, "dept": dept, **node})
            return out
        if "codigo" in node and "departamento" in node:
            seccio = str(node["codigo"])
        elif not dept and "nombre" in node and ("epigrafe" in node or "item" in node):
            dept = node["nombre"]
        for v in node.values():
            if isinstance(v, (dict, list)):
                _camina_boe(v, seccio, dept, out)
    return out


def _link_boe(it: dict) -> str:
    url = it.get("url_html")
    if not url and isinstance(it.get("url_pdf"), dict):
        url = it["url_pdf"].get("texto")
    return url or f"https://www.boe.es/diario_boe/txt.php?id={it['identificador']}"


def items_boe_de_json(j: dict) -> list[dict]:
    items = []
    for it in _camina_boe(j.get("data", {}).get("sumario", {})):
        titol = it.get("titulo", "")
        if it["seccio"] not in SECCIONS_BOE:
            continue
        if not any(p in norm(titol) for p in PARAULES_BOE):
            continue
        items.append({
            "id": "boe:" + it["identificador"],
            "titol": titol[:250],
            "font": "BOE (Estat)",
            "link": _link_boe(it),
            "context": f"Organisme: {it.get('dept')}",
            "termini_data": None,
        })
    return items


def fonts_boe(sessio, avui: date) -> list[dict]:
    items, dies_ok = [], 0
    for d in range(config.DIES_BOE):
        dia = avui - timedelta(days=d)
        r = sessio.get(BOE_SUMARI.format(dia.strftime("%Y%m%d")), headers={"Accept": "application/json"}, timeout=60)
        if r.status_code == 404:  # no hi ha BOE aquell dia
            continue
        r.raise_for_status()
        dies_ok += 1
        items.extend(items_boe_de_json(r.json()))
    if dies_ok == 0:
        raise RuntimeError("cap sumari del BOE disponible")
    return items


# ------------------------------------------------------------------ Webs sense API
def descarrega(sessio, url: str, js: bool = False, timeout: int = 45) -> str:
    """Intenta directe; si falla (403, timeout...) i hi ha clau de ScrapingBee, hi reintenta."""
    try:
        r = sessio.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.text
        err = f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        err = str(e)
    clau = os.getenv("SCRAPER_API_KEY")
    if not clau:
        raise RuntimeError(f"{err} (sense SCRAPER_API_KEY per reintentar)")
    r = sessio.get(SCRAPINGBEE, timeout=90, params={
        "api_key": clau, "url": url, "render_js": "true" if js else "false", "wait": "2000" if js else "0",
    })
    if r.status_code != 200:
        raise RuntimeError(f"{err}; ScrapingBee HTTP {r.status_code}")
    return r.text


def items_de_html(html: str, font: str, url_base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    vistos, items = set(), []
    for el in soup.find_all(["a", "h2", "h3"]):
        txt = el.get_text(" ", strip=True)
        if len(txt) < 25:
            continue
        link = urljoin(url_base, el.get("href", "")) if el.name == "a" else url_base
        if not link.startswith("http") or any(m in link.lower() for m in config.LINKS_IGNORATS):
            continue
        ident = link if el.name == "a" else f"{url_base}#{clau_titol(txt)}"
        if ident in vistos:
            continue
        vistos.add(ident)
        items.append({"id": "web:" + ident, "titol": txt[:250], "font": font, "link": link,
                      "context": f"Font: {font}", "termini_data": None})
    return items


def fonts_web(sessio, nom: str, url: str, js: bool) -> list[dict]:
    return items_de_html(descarrega(sessio, url, js), nom, url)


# ------------------------------------------------------------------ Orquestració
def recull_tot(sessio, avui: date) -> tuple[list[dict], list[str], list[str]]:
    """Retorna (ítems deduplicats, fonts OK, fonts amb error i motiu)."""
    tasques = [("RAISC", lambda: fonts_raisc(sessio, avui)),
               ("CIDO", lambda: fonts_cido(sessio, avui)),
               ("BOE", lambda: fonts_boe(sessio, avui))]
    tasques += [(n, (lambda n=n, u=u, j=j: fonts_web(sessio, n, u, j))) for n, u, j in config.FONTS_WEB]

    items, ok, errors = [], [], []
    for nom, fn in tasques:
        try:
            r = fn()
            ok.append(f"{nom} ({len(r)})")
            items.extend(r)
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {nom}: {e}")
            errors.append(f"{nom}: {e}")

    vistos, unics = set(), []
    for it in items:
        k = it["id"] if it["id"].startswith(("web:", "boe:")) else (clau_titol(it["titol"]) or it["id"])
        if k not in vistos:
            vistos.add(k)
            unics.append(it)
    return unics, ok, errors
