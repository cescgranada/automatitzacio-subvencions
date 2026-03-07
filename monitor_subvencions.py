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

# 2. CERCA DE FONTS AMB CAMUFLATGE D'ALT NIVELL
def cercar_fonts():
    # Creem una sessió per mantenir galetes (cookies)
    session = requests.Session()
    
    # Simulem un navegador real de Windows per evitar el 403
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ca,es;q=0.9,en;q=0.8',
        'Referer': 'https://www.google.com/',
        'DNT': '1'
    }
    
    # URLs amb versions de reserva (backups)
    fonts = [
        ("DOGC Subvencions", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("DOGC Europa", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB Barcelona", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}"),
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories")
    ]
    
    totes = []; ok = []; fails = []

    for nom, url in fonts:
        try:
            # Espera aleatòria per no semblar un bot (entre 4 i 8 segons)
            time.sleep(random.uniform(4, 8))
            
            # Intentem la petició
            res = session.get(url, timeout=30, headers=headers)
            
            if res.status_code == 200:
                ok.append(nom)
                if "xml" in url or "rss" in url or "boe" in url.lower():
                    # Parser tolerant per a XMLs mal formats
                    parser = etree.XMLParser(recover=True, encoding='utf-8')
                    root = etree.fromstring(res.content, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:15]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                else:
                    # Scraping HTML per a fundacions privades
                    soup = BeautifulSoup(res.text, 'html.parser')
                    paragrafs = [p.get_text().strip() for p in soup.find_all(['p', 'h2', 'h3']) if len(p.get_text()) > 30]
                    totes.append({"titol": f"Web: {nom}", "link": url, "font": "PÀGINA_WEB", "contingut": ' '.join(paragrafs[:8])})
            else:
                fails.append(f"{nom} ({res.status_code})")
        except Exception as e:
            fails.append(f"{nom} (Error Connexió)")
            
    return totes, ok, fails

# [Les funcions de memòria, IA, Drive i Mail es mantenen igual que en l'última versió]
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

def processar_ia(dades):
    if not dades: return "No hi ha dades.", [], 0
    historial = carregar_historial()
    noves = [d for d in dades if d['titol'] not in historial]
    if not noves: return "Cap novetat.", [], 0

    perfil = "Escola Nou Patufet (I3-4t ESO). Cooperativa. Prioritats: 1.Concerts, 2.Cooperativa (ESS), 3.Convenis, 4.Licitacions, 5.Erasmus, 6.Equitat, 7.Laboral."
    prompt = f"Analitza aquestes dades: {json.dumps(noves)}. Context: {perfil}. Respon JSON pur [] amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        interessants = json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except: return "Error IA.", [], len(noves)

    for s in interessants:
        try:
            nom_f = s['titol'][:45].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf: pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_f}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

def crear_fitxa_word(d):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for k in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                if f'{{{{{k}}}}}' in p.text: p.text = p.text.replace(f'{{{{{k}}}}}', str(d.get(k, '-')))
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
    msg['Subject'] = f"🚀 Patu-bot Report: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(u, p); s.sendmail(u, r, msg.as_string())
    except: pass

def main():
    dades, ok, fails = cercar_fonts()
    resum, interessants, n_analitzades = processar_ia(dades)
    guardar_historial([d['titol'] for d in dades])
    
    informe = f"--- INFORME DIARI PATU-BOT ---\n\n✅ OK ({len(ok)}): {', '.join(ok)}\n"
    if fails: informe += f"⚠️ ERROR ({len(fails)}): {', '.join(fails)}\n"
    informe += f"\nOportunitats: {len(interessants)}\nAnalitzades: {n_analitzades}\n\nSalutacions!"
    enviar_mail(informe)

if __name__ == "__main__": main()
