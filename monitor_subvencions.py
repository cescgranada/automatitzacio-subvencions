"""Patu-Bot v3 — cerca diària d'oportunitats de finançament per a l'Escola Nou Patufet.

Flux: fonts oficials (RAISC, CIDO, BOE) + webs de fundacions → només ítems nous
→ triatge amb IA → lectura de la pàgina real dels millors → avís només si l'encaix és alt
→ fitxa Word a Drive + correu + recordatoris de termini.
Si alguna cosa important falla, el procés acaba amb error (GitHub t'avisa) en lloc de callar.
"""
import json
import os
import sys
from datetime import date

from patubot import config, estat, fonts, ia, sortida
from patubot.util import nova_sessio


def fonts_en_crisi(ok: list[str], errors: list[str]) -> bool:
    """Una pàgina de fundació caiguda no és greu; les APIs oficials o la meitat de fonts caigudes, sí."""
    noms_ok = " ".join(ok)
    api_oficial_ok = "RAISC" in noms_ok or "CIDO" in noms_ok
    return (not api_oficial_ok) or len(errors) > (len(ok) + len(errors)) / 2


def main() -> int:
    avui = date.today()
    print(f"Patu-Bot v3 — {avui.isoformat()}")
    sessio = nova_sessio()

    items, ok, errors = fonts.recull_tot(sessio, avui)
    print(f"  Fonts OK: {len(ok)} | amb error: {len(errors)} | ítems: {len(items)}")
    crisi = fonts_en_crisi(ok, errors)

    historial = estat.carrega_historial()
    seguiment = estat.carrega_oportunitats()
    nous = [it for it in items if estat.es_nou(it, historial)]
    print(f"  Ítems nous per analitzar: {len(nous)}")

    oportunitats, avaluats, candidats = [], set(), []
    if nous and not crisi:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        puntuacions, processats = ia.triatge(client, nous)
        candidats = ia.tria_candidats(nous, puntuacions)
        ids_candidats = {c["id"] for c in candidats}
        # Només marquem com a "vist" el que la IA ha avaluat de debò: si falla, ho tornarem a provar demà.
        sobrants = {it["id"] for it in nous if puntuacions.get(it["id"], (0,))[0] >= config.MIN_PUNTUACIO_TRIATGE} - ids_candidats
        for it in nous:
            if it["id"] in processats and it["id"] not in ids_candidats and it["id"] not in sobrants:
                estat.marca_vist(historial, it, avui, "descartada")
        if not processats:
            errors.append("IA: Gemini no ha pogut processar cap lot (mira el log d'Actions)")
            crisi = True
        print(f"  Candidats a anàlisi profunda: {len(candidats)}")
        oportunitats, avaluats = ia.analitza_candidats(client, sessio, candidats, avui)
        ids_op = {o["id"] for o in oportunitats}
        for it in candidats:
            if it["id"] in avaluats:
                estat.marca_vist(historial, it, avui, "oportunitat" if it["id"] in ids_op else "descartada")
    elif crisi:
        print("  [ATENCIÓ] fonts en crisi: no es marca res com a vist.")

    # --- fitxes Word + Drive
    errors_sortida = []
    for v in oportunitats:
        try:
            sortida.pujar_a_drive(sortida.crea_fitxa_word(v), sortida.nom_fitxer(v, avui))
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] Drive '{v['titol'][:50]}': {e}")
            errors_sortida.append(f"Drive: {v['titol'][:50]} ({e})")

    # --- seguiment i recordatoris
    nous_ids = {o["id"] for o in oportunitats}
    seguiment = estat.neteja_oportunitats(estat.afegeix_oportunitats(seguiment, oportunitats, avui), avui)
    recorda = [o for o in estat.recordatoris(seguiment, avui) if o["id"] not in nous_ids]

    # --- estat persistent
    estat.guarda_historial(historial, avui)
    estat.guarda_oportunitats(seguiment)
    resum = (f"Fonts OK {len(ok)} · amb error {len(errors)} · ítems nous {len(nous)} · "
             f"candidats {len(candidats)} · oportunitats {len(oportunitats)}")
    with open(config.ESTAT_FILE, "w", encoding="utf-8") as f:
        json.dump({"data": avui.isoformat(), "resum": resum, "errors": errors + errors_sortida}, f, ensure_ascii=False, indent=2)

    # --- correu: només si hi ha alguna cosa a dir (o dilluns, com a prova de vida)
    tot_errors = errors + errors_sortida
    cal_correu = bool(oportunitats or recorda or tot_errors or avui.weekday() == 0 or os.getenv("ENVIA_SEMPRE"))
    if cal_correu:
        try:
            sortida.enviar_correu(*sortida.construeix_correu(oportunitats, recorda, tot_errors, resum, avui))
            print("  Correu enviat.")
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] correu: {e}")
            return 1

    print(f"  {resum}")
    if crisi:
        print("  [ERROR] execució amb errors greus — la marco com a fallida perquè se't avisi.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
