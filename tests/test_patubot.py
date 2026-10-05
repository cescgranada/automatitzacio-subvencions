import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patubot import estat, fonts, ia, panell  # noqa: E402
from patubot.sortida import crea_fitxa_word, construeix_correu  # noqa: E402
from patubot.util import clau_titol, parse_data  # noqa: E402

AVUI = date(2026, 10, 4)


def raisc(**kw):
    base = {"entitat_oo_aa_o_departament_1": "Departament d'Educació", "administraci_": "Autonòmica",
            "regio_apli": "CATALUNYA", "tipus_de_beneficiaris": "Persones jurídiques que no desenvolupen activitat econòmica",
            "finalitat_publica": "Educació", "data_fi_termini_presentaci_sol_licitud": "2026-11-01T00:00:00.000"}
    base.update(kw)
    return base


# ---------------------------------------------------------------- fonts
def test_raisc_accepta_cas_ideal():
    assert fonts.admet_raisc(raisc(), AVUI)


def test_raisc_descarta_altres_municipis_pero_no_barcelona():
    assert not fonts.admet_raisc(raisc(administraci_="Local / Municipi", entitat_oo_aa_o_departament_1="Ajuntament de Girona"), AVUI)
    assert fonts.admet_raisc(raisc(administraci_="Local / Municipi", entitat_oo_aa_o_departament_1="Ajuntament de Barcelona"), AVUI)


def test_raisc_descarta_regio_persones_fisiques_agricultura_i_caducades():
    assert not fonts.admet_raisc(raisc(regio_apli="GIRONA; LLEIDA"), AVUI)
    assert not fonts.admet_raisc(raisc(tipus_de_beneficiaris="Persones físiques que no desenvolupen activitat econòmica"), AVUI)
    assert not fonts.admet_raisc(raisc(finalitat_publica="Agricultura, Pesca i Alimentació"), AVUI)
    assert not fonts.admet_raisc(raisc(data_fi_termini_presentaci_sol_licitud="2026-09-01T00:00:00.000"), AVUI)


def test_raisc_sense_termini_es_conserva():
    assert fonts.admet_raisc(raisc(data_fi_termini_presentaci_sol_licitud=None, data_fi_presentaci_sol="Obert"), AVUI)


def test_boe_extreu_nomes_convocatories_de_seccions_rellevants():
    j = {"data": {"sumario": {"diario": [{"seccion": [
        {"codigo": "1", "departamento": {"nombre": "X", "epigrafe": {"item": {"identificador": "A", "titulo": "Se convocan ayudas"}}}},
        {"codigo": "3", "departamento": [{"nombre": "MINISTERIO DE EDUCACIÓN", "epigrafe": [{"nombre": "e", "item": [
            {"identificador": "B", "titulo": "Resolución por la que se convocan ayudas para centros"},
            {"identificador": "C", "titulo": "Nombramiento de funcionario"}]}]}]},
    ]}]}}}
    res = fonts.items_boe_de_json(j)
    assert [r["id"] for r in res] == ["boe:B"]
    assert "EDUCACIÓN" in res[0]["context"]


def test_html_ignora_navegacio_i_duplicats():
    html = ('<a href="/crides/ajuts-coeducacio-2026">Convocatòria d\'ajuts per a projectes de coeducació 2026</a>'
            '<a href="/crides/ajuts-coeducacio-2026">Convocatòria d\'ajuts per a projectes de coeducació 2026</a>'
            '<a href="https://translate.google.com/translate_t">Tradueix aquesta pàgina automàticament</a>'
            '<a href="/x">Inici</a>')
    res = fonts.items_de_html(html, "Fundació X", "https://fx.cat/crides")
    assert len(res) == 1 and res[0]["link"] == "https://fx.cat/crides/ajuts-coeducacio-2026"


def test_dedup_titol_entre_fonts():
    assert clau_titol("Subvencions  per a l'EDUCACIÓ, 2026") == clau_titol("subvencions per a l'educacio 2026")


def test_parse_data():
    assert parse_data("16/10/2026") == date(2026, 10, 16)
    assert parse_data("2026-10-16T00:00:00.000") == date(2026, 10, 16)
    assert parse_data("Des de l'endemà") is None


# ---------------------------------------------------------------- estat
def test_historial_migra_format_antic(tmp_path):
    p = tmp_path / "h.json"
    p.write_text('{"https://x.cat/a": "2026-05-01"}', encoding="utf-8")
    h = estat.carrega_historial(str(p))
    assert h["https://x.cat/a"] == {"vist": "2026-05-01", "resultat": "descartada"}
    assert not estat.es_nou({"id": "web:https://x.cat/a", "link": "https://x.cat/a"}, h)


def test_recordatoris_i_neteja():
    llista = [{"id": "1", "titol": "A", "termini_data": "2026-10-08", "ultim_recordatori": None, "link": "l"},
              {"id": "2", "titol": "B", "termini_data": "2026-12-01", "ultim_recordatori": None, "link": "l"},
              {"id": "3", "titol": "C", "termini_data": "2026-10-06", "ultim_recordatori": "2026-10-03", "link": "l"},
              {"id": "4", "titol": "D", "termini_data": "2026-09-01", "ultim_recordatori": None, "link": "l"}]
    assert [o["id"] for o in estat.recordatoris(llista, AVUI)] == ["1"]   # B lluny, C recordada fa poc, D caducada
    assert llista[0]["ultim_recordatori"] == "2026-10-04"
    assert [o["id"] for o in estat.neteja_oportunitats(llista, AVUI)] == ["1", "2", "3"]


# ---------------------------------------------------------------- ia
def valoracio(**kw):
    base = dict(titol="T", organisme="O", import_total="1", termini_text="", termini_data="2026-12-01",
                elegibilitat="Sí", motiu_elegibilitat="", encaix=8, resum="r", requisits="q", accions="a", adaptacio="")
    base.update(kw)
    return base


def test_es_oportunitat():
    assert ia.es_oportunitat(valoracio(), AVUI)
    assert not ia.es_oportunitat(valoracio(elegibilitat="No"), AVUI)
    assert not ia.es_oportunitat(valoracio(encaix=4), AVUI)
    assert not ia.es_oportunitat(valoracio(termini_data="2026-09-30"), AVUI)
    assert ia.es_oportunitat(valoracio(elegibilitat="Dubtós", termini_data=""), AVUI)


def test_candidats_respecten_minim_i_maxim(monkeypatch):
    items = [{"id": str(i), "termini_data": None} for i in range(40)]
    punt = {str(i): (9 if i < 30 else 2, "") for i in range(40)}
    assert len(ia.tria_candidats(items, punt)) == 25
    assert all(punt[c["id"]][0] >= 5 for c in ia.tria_candidats(items, punt))




# ---------------------------------------------------------------- sortida
def test_fitxa_word_omple_marcadors_trencats():
    from docx import Document
    d = crea_fitxa_word({**valoracio(), "link": "https://x.cat", "titol": "Ajuts coeducació"})
    text = "\n".join(p.text for p in Document(d).paragraphs)
    assert "Ajuts coeducació" in text and "{{" not in text and "https://x.cat" in text


def test_correu_assumpte_segons_cas():
    assert "oportunitat" in construeix_correu([valoracio(link="l")], [], [], "r", AVUI)[0]
    assert "recordatori" in construeix_correu([], [{"termini_data": "2026-10-08", "titol": "A", "link": "l"}], [], "r", AVUI)[0]
    assert "ATENCIÓ" in construeix_correu([], [], ["BOE: error"], "r", AVUI)[0]


# ---------------------------------------------------------------- propostes i panell
def test_propostes_conserven_primera_data_i_nomes_se_les_treu_si_s_eliminen():
    p = {}
    estat.desa_proposta(p, {**valoracio(), "id": "a", "link": "l"}, True, date(2026, 10, 1))
    estat.desa_proposta(p, {**valoracio(), "id": "a", "link": "l"}, False, AVUI)
    assert p["a"]["primera"] == "2026-10-01" and p["a"]["estat"] == "descartada" and p["a"]["actualitzada"] == "2026-10-04"
    p["b"] = {**valoracio(termini_data="2020-01-01"), "id": "b", "primera": "2020-01-01"}
    assert set(estat.sense_eliminades(p, set())) == {"a", "b"}      # una caducada fa anys NO desapareix sola
    assert set(estat.sense_eliminades(p, {"b"})) == {"a"}


def test_panell_incrusta_dades_sense_trencar_script():
    p = {"a": {**valoracio(), "id": "a", "link": "https://x.cat", "titol": "Mal </script><b>titol", "estat": "oportunitat"}}
    out = panell.genera_panell(p, AVUI)
    assert "</script><b>" not in out and r"<\/script>" in out
    assert out.count("</script>") == 1 and "2026-10-04" in out and "__DADES__" not in out


def test_panell_javascript_te_sintaxi_valida(tmp_path):
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        return  # sense Node no es pot comprovar (a GitHub Actions n'hi ha)
    out = panell.genera_panell({}, AVUI)
    js = re.search(r"<script>\n(.*)</script>", out, re.S).group(1)
    f = tmp_path / "panell.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
