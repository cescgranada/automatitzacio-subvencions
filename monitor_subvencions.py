import requests
import os
import smtplib
import io
import json
import time
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ
API_KEY = os.getenv("GEMINI_API_KEY")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
client = genai.Client(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# 2. MEMÒRIA
def carregar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def guardar_historial(llista_nova):
    h = carregar_historial()
    actualitzat = list(set(h + llista_nova))[-500:]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f: json.dump(actualitzat, f)

# 3. CERCA DE FONTS AMB SCRAPER API (PROXY RESIDENCIAL)
def cercar_fonts():
    session = requests.Session()
    totes = []; ok = []; fails = []
    
    fonts_config = [
        ("DOGC Subvencions", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("DOGC Europa", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB Barcelona", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}"),
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories")
    ]

    for nom, url in fonts_config:
        try:
            if SCRAPER_API_KEY:
                # Fem la petició a través del proxy de ScraperAPI per saltar bloquejos
                payload = {'api_key': SCRAPER_API_KEY, 'url': url}
                res = session.get('http://api.scraperapi.com', params=payload, timeout=60)
            else:
                # Si no hi ha clau, intentem connexió directa normal
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = session.get(url, timeout=35, headers=headers)

            if res.status_code == 200:
                ok.append(nom)
                
                # Processem la resposta segons si és XML (DOGC/BOE/BOPB) o Web (Fundacions)
                if "xml" in url or "rss" in url or "boe" in url:
                    parser = etree.XMLParser(recover=True)
                    root = etree.fromstring(res.content, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:15]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                else:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    for element in soup.find_all(['a', 'h2', 'h3']):
                        txt = element.get_text().strip()
                        if len(txt) > 30 and any(k in txt.lower() for k in ['ajut', 'subvenció', 'beca', 'convocatòria', 'resolució']):
                            link = element.get('href') if element.name == 'a' else url
                            if link and not link.startswith('http'): 
                                link = url + link
                            totes.append({"titol": txt, "link": link, "font": nom})
            else:
                fails.append(f"{nom} ({res.status_code})")
                
        except Exception as e:
            fails.append(f"{nom} (Timeout/Error)")
            
    return totes, ok, fails

# 4. IA AVANÇADA AMB GEMINI PRO
def processar_ia(dades):
    if not dades: return "No dades.", [], 0
    historial = carregar_historial()
    
    noves = [d for d in dades if d['titol'] not in historial]
    if not noves: return "Cap novetat.", [], 0

    perfil = "Escola Nou Patufet (I3-4t ESO). Cooperativa. Prioritats: 1.Concerts educatius, 2.Economia Social i Solidària (ESS), 3.Convenis Ajuntament, 4.Licitacions, 5.Erasmus+, 6.Equitat/Inclusió, 7.Laboral/Contractació."
    prompt = f"Ets un expert en gestió escolar. Analitza aquestes dades: {json.dumps(noves)}. Context de l'escola: {perfil}. Respon JSON pur [] (sense cap text addicional ni format markdown) amb llista d'objectes: titol, prioritat (1 a 7), organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except Exception as e:
        print(f"Error IA: {e}")
        return "Error IA.", [], len(noves)

    for s in interessants:
        try:
            nom_f = str(s.get('titol', 'Subvencio'))[:40].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf: 
                pujar_a_drive(w_buf, f"PRIO{s.get('prioritat', 'X')}_{nom_f}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

# 5. GENERACIÓ DOCUMENTS I DRIVE
def crear_fitxa_word(d):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for k in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{k}}}}}"
                if placeholder in p.text: p.text = p.text.replace(placeholder, str(d.get(k, '-')))
        b = io.BytesIO(); doc.save(b); b.seek(0); return b
    except: return None

def pujar_a_drive(c, n, m):
    try:
        creds = service_account.Credentials.from_service_account_info(json.loads(os.getenv("GDRIVE_CREDENTIALS")))
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(c.read()) if hasattr(c, 'read') else io.BytesIO(c), mimetype=m)
        service.files().create(body={'name': n, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except: pass

def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🚀 Patu-bot Informe PRO: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(u, p); s.sendmail(u, r, msg.as_string())
    except: pass

# 6. FUNCIÓ PRINCIPAL
def main():
    print("Iniciant Patu-bot v2026 PRO (amb ScraperAPI)...")
    dades, ok, fails = cercar_fonts()
    resum_ia, interessants, n_analitzades = processar_ia(dades)
    guardar_historial([d['titol'] for d in dades])
    
    informe = f"--- INFORME DIARI PATU-BOT (PRO) ---\n\n"
    informe += f"✅ OK ({len(ok)}): {', '.join(ok)}\n"
    if fails: informe += f"⚠️ ERROR ({len(fails)}): {', '.join(fails)}\n"
    informe += f"\nOportunitats detectades: {len(interessants)}\nPublicacions noves analitzades: {n_analitzades}\n\nSalutacions!"
    
    enviar_mail(informe)
    print("Procés finalitzat correctament.")

if __name__ == "__main__": main()
