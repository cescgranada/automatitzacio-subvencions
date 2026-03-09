import requests
import os
import smtplib
import io
import json
import time
import random
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

# 3. CERCA DE FONTS (ROBUSTESA EXTREMA)
def cercar_fonts():
    session = requests.Session()
    totes = []; ok = []; fails = []
    
    fonts_config = [
        ("DOGC Subvencions", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss", "https://dogc.gencat.cat/ca/ajuts-i-subvencions/"),
        ("DOGC Europa", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss", "https://dogc.gencat.cat/ca/internacional/subvencions-internacionals/"),
        ("BOPB Barcelona", "https://bop.diba.cat/rss.asp?seccio=4.2", "https://bop.diba.cat/"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}", None),
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes", None),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides", None),
        ("EduCaixa", "https://educaixa.org/ca/convocatories", None)
    ]

    for nom, url, backup in fonts_config:
        success = False
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': 'https://www.google.cat/'
        }

        try:
            time.sleep(random.uniform(4, 7))
            res = session.get(url, timeout=35, headers=headers)
            
            # Pla B: Si l'RSS falla (403/404/500) i tenim un backup web, ho provem
            if res.status_code != 200 and backup:
                time.sleep(3) # Pausa abans del reintent
                headers['Referer'] = 'https://web.gencat.cat/'
                res = session.get(backup, timeout=35, headers=headers)
                nom = f"{nom} (Web)"

            if res.status_code == 200:
                ok.append(nom)
                content_type = res.headers.get('Content-Type', '').lower()
                
                if "xml" in content_type or "rss" in url or "boe" in url:
                    parser = etree.XMLParser(recover=True)
                    root = etree.fromstring(res.content, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:15]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                else:
                    # Scraping si s'ha fet servir el Pla B
                    soup = BeautifulSoup(res.text, 'html.parser')
                    for element in soup.find_all(['a', 'h2', 'h3']):
                        txt = element.get_text().strip()
                        if len(txt) > 30 and any(k in txt.lower() for k in ['ajut', 'subvenció', 'beca', 'convocatòria', 'resolució']):
                            link = element.get('href') if element.name == 'a' else url
                            if link and not link.startswith('http'): 
                                link = url + link
                            totes.append({"titol": txt, "link": link, "font": nom})
                success = True

        except Exception as e:
            pass
        
        if not success: fails.append(nom)
            
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
        # AQUÍ FEM EL SALT AL MODEL PRO
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

def main():
    print("Iniciant Patu-bot v2026 PRO...")
    dades, ok, fails = cercar_fonts()
    resum_ia, interessants, n_analitzades = processar_ia(dades)
    guardar_historial([d['titol'] for d in dades])
    
    informe = f"--- INFORME DIARI PATU-BOT (PRO) ---\n\n✅ OK ({len(ok)}): {', '.join(ok)}\n"
    if fails: informe += f"⚠️ ERROR ({len(fails)}): {', '.join(fails)}\n"
    informe += f"\nOportunitats detectades: {len(interessants)}\nPublicacions noves analitzades: {n_analitzades}\n\nSalutacions!"
    enviar_mail(informe)

if __name__ == "__main__": main()
