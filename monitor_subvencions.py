import requests
import os
import smtplib
import io
import json
import time
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime, timedelta
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# ============================================================
# 1. CONFIGURACIÓ
# ============================================================
API_KEY = os.getenv("GEMINI_API_KEY")
SCRAPINGBEE_API_KEY = os.getenv("SCRAPER_API_KEY")
client = genai.Client(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# Webs que necessiten JS per renderitzar el contingut
REQUEREIXEN_JS = {
    "Fundació Bofill",
    "EduCaixa",
    "Fundació Carulla (Cultura i Educació)",
}

# ============================================================
# 2. MEMÒRIA — ara guarda URL + data de primera detecció
#    Format: { "url_o_titol": "YYYY-MM-DD" }
#    No s'exclou res fins que han passat DIES_REEXPOSA dies
# ============================================================
DIES_REEXPOSA = 30  # Torna a mostrar una oportunitat si porta +30 dies sense aparèixer

def carregar_historial() -> dict:
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Compatibilitat amb el format antic (llista de títols)
            if isinstance(data, list):
                avui = datetime.now().strftime("%Y-%m-%d")
                return {t: avui for t in data}
            return data
        except:
            return {}
    return {}

def guardar_historial(entrades: list[dict]):
    """Actualitza l'historial amb les entrades noves (llista de dicts amb 'id')."""
    h = carregar_historial()
    avui = datetime.now().strftime("%Y-%m-%d")
    for e in entrades:
        clau = e.get("link") or e.get("titol", "")
        if clau and clau not in h:
            h[clau] = avui
    # Neteja entrades molt antigues (> 1 any) per no créixer indefinidament
    limit = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    h = {k: v for k, v in h.items() if v >= limit}
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)

def es_nova(entrada: dict) -> bool:
    """Retorna True si l'entrada no ha aparegut en els últims DIES_REEXPOSA dies."""
    h = carregar_historial()
    clau = entrada.get("link") or entrada.get("titol", "")
    if clau not in h:
        return True
    primera = datetime.strptime(h[clau], "%Y-%m-%d")
    return (datetime.now() - primera).days > DIES_REEXPOSA

# ============================================================
# 3. SCRAPING — sense filtre de paraules clau previ
#    Tot va a la IA. Render JS activat per les webs que cal.
# ============================================================
def scrape_url(nom: str, url: str, session: requests.Session) -> str | None:
    """Retorna el text HTML cru o None si falla."""
    necessita_js = nom in REQUEREIX_JS if False else nom in REQUEREIXEN_JS
    try:
        if SCRAPINGBEE_API_KEY:
            payload = {
                "api_key": SCRAPINGBEE_API_KEY,
                "url": url,
                "render_js": "true" if necessita_js else "false",
                "wait": "2000" if necessita_js else "0",
            }
            res = session.get("https://app.scrapingbee.com/api/v1/", params=payload, timeout=90)
        else:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; PatuBot/2.0)"}
            res = session.get(url, timeout=45, headers=headers)

        if res.status_code == 200:
            return res.text
        else:
            return None
    except:
        return None

def extreure_items_html(html: str, font: str, url_base: str) -> list[dict]:
    """
    Extreu TOTS els elements <a>, <h2>, <h3>, <h4> sense filtre previ.
    La IA ja decidirà què és rellevant.
    """
    items = []
    soup = BeautifulSoup(html, "html.parser")
    root_url = "https://" + url_base.split("/")[2]

    for el in soup.find_all(["a", "h2", "h3", "h4"]):
        txt = el.get_text(" ", strip=True)
        if len(txt) < 15:  # Filtre mínim: evita botons d'1 paraula
            continue
        link = el.get("href") if el.name == "a" else url_base
        if link:
            if link.startswith("//"):
                link = "https:" + link
            elif not link.startswith("http"):
                link = root_url + ("" if link.startswith("/") else "/") + link
        items.append({"titol": txt[:200], "link": link or url_base, "font": font})

    return items

def extreure_items_boe(content: bytes, font: str, url_base: str) -> list[dict]:
    """
    Parseja el XML del BOE filtrant per seccions rellevants (II i III)
    i per paraules clau dins del títol/descripció.
    """
    SECCIONS_BOE = {"2", "3"}  # Secció II (autoritats) i III (altres disposicions)
    PARAULES_BOE = [
        "subvenci", "convocatòria", "convocatoria", "ajut", "beca",
        "programa", "dotaci", "educaci", "cooperativ", "innovaci",
        "cultura", "social", "igualtat", "gènere", "género",
    ]
    items = []
    try:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(content, parser=parser)
        for item in root.xpath("//item") + root.xpath("//anuncio"):
            seccio = (item.findtext("seccion") or item.findtext("section") or "").strip()
            if seccio and seccio not in SECCIONS_BOE:
                continue
            titol = item.findtext("title") or item.findtext("titulo") or "Sense títol"
            link = item.findtext("link") or ""
            if not link and item.findtext("url_pdf"):
                link = "https://www.boe.es" + item.findtext("url_pdf")
            if not link:
                link = url_base
            # Filtre lleuger: almenys una paraula clau al títol
            titol_lower = titol.lower()
            if any(p in titol_lower for p in PARAULES_BOE):
                items.append({"titol": titol[:200], "link": link, "font": font})
    except:
        pass
    return items

def cercar_fonts() -> tuple[list[dict], list[str], list[str]]:
    session = requests.Session()
    totes = []
    ok = []
    fails = []

    fonts_config = [
        ("CIDO (DOGC, BOPB i Europa)",          "https://cido.diba.cat/subvencions"),
        ("BOE Estat",                             f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}"),
        ("Tauler Generalitat",                    "https://tauler.seu.cat/inici.do?idens=1"),
        ("Fundació la Caixa",                     "https://fundacionlacaixa.org/ca/convocatories-socials"),
        ("Fundació Bofill",                       "https://fundaciobofill.cat/crides"),
        ("EduCaixa",                              "https://educaixa.org/ca/convocatories"),
        ("Fundació Carulla (Cultura i Educació)", "https://fundaciocarulla.cat/"),
        ("Fundació Banc Sabadell (Cultura/Innovació)", "https://www.fundacionbancosabadell.com/convocatorias/"),
        ("Ajuntament BCN (subvencions)",          "https://ajuntament.barcelona.cat/ca/informacio-administrativa/subvencions"),
        ("Coòpolis (Economia Social BCN)",        "https://www.bcn.ateneucooperatiu.cat/noticies/"),
    ]

    for nom, url in fonts_config:
        html = scrape_url(nom, url, session)
        if html is None:
            fails.append(f"{nom} (Error/Timeout)")
            continue

        ok.append(nom)
        if "boe.es" in url:
            items = extreure_items_boe(html.encode() if isinstance(html, str) else html, nom, url)
        else:
            items = extreure_items_html(html, nom, url)

        totes.extend(items)

    return totes, ok, fails

# ============================================================
# 4. IA AMB GEMINI PRO — rep tot, decideix tot
# ============================================================
PERFIL_ESCOLA = """
Escola Nou Patufet (I3-4t ESO). Cooperativa de treball situada a Gràcia, Barcelona.
Centre compromès amb el feminisme, la coeducació i l'Economia Social i Solidària (ESS).

ESTRATÈGIA DE CERCA (Sigues proactiu i creatiu):
1. Directes: subvencions explícitament per a escoles, centres educatius, cooperatives de treball o entitats sense ànim de lucre.
2. Adaptables: convocatòries de cultura, gènere, barri, sostenibilitat o innovació on l'escola pugui presentar un projecte propi (ex: taller d'arts, xarxa cooperativa de barri, pla d'igualtat, projecte de transició ecològica, activitat extraescolar).
3. Temàtiques clau d'alt interès: feminisme i coeducació, llengua catalana, intercooperació i ESS, arts escèniques i cultura, sostenibilitat i ecologia, inclusió i diversitat funcional, innovació pedagògica.

CRITERI D'EXCLUSIÓ (Sigues rigorós):
Ignora completament: agricultura/ramaderia, recerca universitària, infraestructures viàries, ajuts exclusivament per a grans empreses mercantils (SA/SL), beques individuals per a alumnes (menjador/transport/material), esport d'elit, subvencions d'àmbit municipal d'altres ciutats que no siguin Barcelona o d'abast no aplicable a Catalunya.

IMPORTANT: Si una convocatòria NO és específicament per a escoles però la Nou Patufet hi pot encaixar (ex: "Premis a la creativitat ciutadana"), selecciona-la i explica al resum com s'hi podria adaptar.
"""

def processar_ia(dades: list[dict]) -> tuple[str, list[dict], int]:
    if not dades:
        return "No dades.", [], 0

    # Filtre per historial — respecta DIES_REEXPOSA
    noves = [d for d in dades if es_nova(d)]
    n_analitzades = len(noves)

    if not noves:
        return "Cap novetat.", [], 0

    # Deduplicar per link
    vistes = set()
    noves_uniques = []
    for d in noves:
        clau = d.get("link") or d.get("titol")
        if clau not in vistes:
            vistes.add(clau)
            noves_uniques.append(d)

    prompt = f"""
Ets un captador de fons professional per a entitats socials i cooperatives.

Analitza la llista de publicacions següent i selecciona TOTES les que siguin potencialment interessants per a l'escola descrita al perfil. No descartes res que tingui un mínim de possibilitat d'encaix — és millor un fals positiu que perdre una oportunitat real.

PERFIL DE L'ENTITAT:
{PERFIL_ESCOLA}

PUBLICACIONS A ANALITZAR:
{json.dumps(noves_uniques, ensure_ascii=False)}

Respon EXCLUSIVAMENT amb un JSON pur (sense markdown, sense ```json, sense text addicional):
[
  {{
    "titol": "...",
    "prioritat": 1-9,
    "organisme": "...",
    "import": "... o Desconegut",
    "termini": "... o Pendent de publicació",
    "resum": "2-3 frases: de què tracta i per què encaixa amb la Nou Patufet",
    "accions": "Primer pas concret que hauria de fer l'escola",
    "link_pdf": "url directe o url de la convocatòria",
    "adaptacio": "Si no és directament per a escoles, com s'hi podria adaptar. Buit si és directa."
  }}
]

Si no hi ha cap oportunitat rellevant, retorna [].
"""

    try:
        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        net = response.text.replace("```json", "").replace("```", "").strip()
        # Gemini de vegades afegeix text abans del JSON
        inici = net.find("[")
        if inici > 0:
            net = net[inici:]
        interessants = json.loads(net)
    except Exception as e:
        print(f"Error IA: {e}")
        return "Error IA.", [], n_analitzades

    # Genera fitxes Word i puja a Drive
    for s in interessants:
        try:
            nom_f = str(s.get("titol", "Subvencio"))[:40].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(
                    w_buf,
                    f"PRIO{s.get('prioritat', 'X')}_{nom_f}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        except:
            continue

    return f"Trobades {len(interessants)} oportunitats.", interessants, n_analitzades

# ============================================================
# 5. DOCUMENTS I DRIVE
# ============================================================
def crear_fitxa_word(d: dict):
    try:
        doc = Document("plantilla_subvencio.docx")
        for p in doc.paragraphs:
            for k in ["titol", "organisme", "import", "termini", "resum", "accions", "adaptacio"]:
                placeholder = f"{{{{{k}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(d.get(k, "-")))
        b = io.BytesIO()
        doc.save(b)
        b.seek(0)
        return b
    except:
        return None

def pujar_a_drive(contingut, nom: str, mimetype: str):
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(os.getenv("GDRIVE_CREDENTIALS"))
        )
        service = build("drive", "v3", credentials=creds)
        buf = io.BytesIO(contingut.read()) if hasattr(contingut, "read") else io.BytesIO(contingut)
        media = MediaIoBaseUpload(buf, mimetype=mimetype)
        service.files().create(
            body={"name": nom, "parents": [GDRIVE_FOLDER_ID]},
            media_body=media,
        ).execute()
    except:
        pass

def enviar_mail(text: str, interessants: list[dict]):
    u = os.getenv("EMAIL_USER")
    p = os.getenv("EMAIL_PASS")
    r = os.getenv("EMAIL_RECEIVER")

    # Construeix un cos de correu llegible si hi ha oportunitats
    if interessants:
        linies = []
        for s in sorted(interessants, key=lambda x: x.get("prioritat", 9)):
            prio = s.get("prioritat", "?")
            titol = s.get("titol", "-")
            termini = s.get("termini", "-")
            resum = s.get("resum", "-")
            accions = s.get("accions", "-")
            adapt = s.get("adaptacio", "")
            link = s.get("link_pdf", "-")
            bloc = (
                f"[PRIORITAT {prio}] {titol}\n"
                f"Termini: {termini}\n"
                f"Resum: {resum}\n"
                f"Primer pas: {accions}\n"
            )
            if adapt:
                bloc += f"Com adaptar-ho: {adapt}\n"
            bloc += f"Enllaç: {link}\n"
            linies.append(bloc)
        cos_oportunitats = "\n" + ("-" * 60 + "\n").join(linies)
    else:
        cos_oportunitats = "\nCap oportunitat nova avui.\n"

    cos_complet = text + cos_oportunitats

    msg = MIMEText(cos_complet, "plain", "utf-8")
    msg["Subject"] = (
        f"🚀 Patu-bot: {len(interessants)} oportunitat(s) — {datetime.now().strftime('%d/%m/%Y')}"
        if interessants
        else f"Patu-bot: cap novetat — {datetime.now().strftime('%d/%m/%Y')}"
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(u, p)
            s.sendmail(u, r, msg.as_string())
    except Exception as e:
        print(f"Error enviant correu: {e}")

# ============================================================
# 6. MAIN
# ============================================================
def main():
    print(f"Iniciant Patu-bot v2 — {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    dades, ok, fails = cercar_fonts()
    print(f"  Fonts OK: {len(ok)} | Errors: {len(fails)} | Items trobats: {len(dades)}")

    resum_ia, interessants, n_analitzades = processar_ia(dades)
    print(f"  {resum_ia} ({n_analitzades} analitzats)")

    guardar_historial(dades)

    informe = (
        f"--- INFORME DIARI PATU-BOT v2 ---\n\n"
        f"OK ({len(ok)}): {', '.join(ok)}\n"
    )
    if fails:
        informe += f"ERROR ({len(fails)}): {', '.join(fails)}\n"
    informe += (
        f"\nOportunitats detectades: {len(interessants)}\n"
        f"Publicacions noves analitzades: {n_analitzades}\n"
    )

    enviar_mail(informe, interessants)
    print("  Correu enviat. Fet.")

if __name__ == "__main__":
    main()
