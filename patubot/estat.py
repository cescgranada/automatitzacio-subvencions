"""Memòria del bot.

historial_subvencions.json : { id: {"vist": "YYYY-MM-DD", "resultat": "descartada|oportunitat"} }
   (el format antic { url: "YYYY-MM-DD" } es migra sol)
oportunitats.json          : llista d'oportunitats avisades, per poder fer recordatoris de termini.
"""
import json
import os
from datetime import date, timedelta

from . import config
from .util import parse_data


def _llegeix(path, per_defecte):
    if not os.path.exists(path):
        return per_defecte
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)  # si el JSON està trencat, que peti: millor que perdre l'historial en silenci


def _escriu(path, dades):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dades, f, ensure_ascii=False, indent=2, sort_keys=True)


# ---------------------------------------------------------------- historial
def carrega_historial(path=config.HISTORIAL_FILE) -> dict:
    h = _llegeix(path, {})
    if isinstance(h, list):
        h = {t: "1970-01-01" for t in h}
    return {k: (v if isinstance(v, dict) else {"vist": v, "resultat": "descartada"}) for k, v in h.items()}


def guarda_historial(h: dict, avui: date, path=config.HISTORIAL_FILE):
    limit = (avui - timedelta(days=365)).isoformat()
    _escriu(path, {k: v for k, v in h.items() if v.get("vist", "") >= limit})


def es_nou(item: dict, h: dict) -> bool:
    return item["id"] not in h and item["link"] not in h


def marca_vist(h: dict, item: dict, avui: date, resultat: str):
    h[item["id"]] = {"vist": avui.isoformat(), "resultat": resultat}


# ---------------------------------------------------------------- oportunitats
def carrega_oportunitats(path=config.OPORTUNITATS_FILE) -> list[dict]:
    return _llegeix(path, [])


def guarda_oportunitats(llista: list[dict], path=config.OPORTUNITATS_FILE):
    _escriu(path, llista)


def afegeix_oportunitats(llista: list[dict], noves: list[dict], avui: date) -> list[dict]:
    ids = {o["id"] for o in llista}
    for n in noves:
        if n["id"] not in ids:
            llista.append({k: n.get(k) for k in ("id", "titol", "organisme", "link", "termini", "termini_data", "encaix")}
                           | {"avisada": avui.isoformat(), "ultim_recordatori": None})
    return llista


def recordatoris(llista: list[dict], avui: date) -> list[dict]:
    """Oportunitats amb termini proper que no s'han recordat fa poc. Actualitza 'ultim_recordatori'."""
    toca = []
    for o in llista:
        fi = parse_data(o.get("termini_data"))
        if not fi or not (0 <= (fi - avui).days <= config.DIES_RECORDATORI):
            continue
        ult = parse_data(o.get("ultim_recordatori"))
        if ult and (avui - ult).days < config.DIES_ENTRE_RECORDATORIS:
            continue
        o["ultim_recordatori"] = avui.isoformat()
        toca.append(o)
    return sorted(toca, key=lambda o: o["termini_data"])


def neteja_oportunitats(llista: list[dict], avui: date) -> list[dict]:
    """Treu les que ja van caducar fa més d'una setmana."""
    def viva(o):
        fi = parse_data(o.get("termini_data"))
        return fi is None or (avui - fi).days <= 7
    return [o for o in llista if viva(o)]


# ---------------------------------------------------------------- propostes (alimenten el panell web)
def carrega_propostes(path=config.PROPOSTES_FILE) -> dict:
    return _llegeix(path, {})


def guarda_propostes(p: dict, path=config.PROPOSTES_FILE):
    _escriu(path, p)


def desa_proposta(p: dict, v: dict, es_oportunitat: bool, avui: date):
    """Guarda (o actualitza) una convocatòria avaluada amb tots els camps que mostra el panell."""
    antiga = p.get(v["id"], {})
    p[v["id"]] = {**v, "estat": "oportunitat" if es_oportunitat else "descartada",
                  "primera": antiga.get("primera", avui.isoformat()), "actualitzada": avui.isoformat()}


def carrega_eliminades(path=config.ELIMINADES_FILE) -> set:
    return set(_llegeix(path, []))


def sense_eliminades(p: dict, eliminades: set) -> dict:
    """Les propostes s'acumulen indefinidament: només desapareixen quan algú les elimina des del panell."""
    return {k: v for k, v in p.items() if k not in eliminades}
