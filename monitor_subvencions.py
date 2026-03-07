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

# 2. GESTIÓ DE MEMÒRIA (DUPLICATS)
def carregar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def guardar_historial(llista_nova):
    h = carregar_historial()
    # Mantenim els últims 500 títols per evitar duplicats a llarg termini
    actualitzat = list(set(h + llista_nova))[-500:]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(actualitzat, f)

# 3. CERCA DE FONTS AMB CAMUFLATGE ULTRA-ROBUST
def cercar_fonts():
    session = requests.Session()
    
    # Headers molt més convincents per evitar el 403 (Forbidden)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ca,es;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': 'https://www.google.com/',
        'DNT': '1'
    }
    
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
            # Pausa aleatòria incremental per no semblar un bot (entre 5 i 10 segons)
            time.sleep(random.uniform(5, 10))
            
            # Intentem la petició amb el camuflatge
            res = session.get(url, timeout=45, headers=headers, allow_redirects=True)
            
            if res.status_code == 200:
                ok.append(nom)
                if "xml" in url or "rss" in url or "boe" in url.lower():
                    # Parser tolerant per a XMLs/RSS amb recuperació d'errors
                    parser = etree.XMLParser(recover=True, encoding='utf-8')
                    root = etree.fromstring(res.content, parser=parser)
                    
                    # Busquem items tant en format RSS com en format BOE
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:20]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                else:
                    # Scraping HTML millorat per a fundacions privades
                    soup = BeautifulSoup(res.text, 'html.parser')
                    # Busquem textos més llargs que identifiquin convocatòries
                    paragrafs = [p.get_text().strip() for p in soup.find_all(['p', 'h2', 'h3', 'a']) if len(p.get_text()) > 40]
                    totes.append({"titol": f"Web: {nom}", "link": url, "font": "PÀGINA_WEB", "contingut": ' '.join(paragrafs[:10])})
            else:
                # Si falla, ho registrem però no aturem el script
                fails.append(f"{nom} ({res.status_code})")
                
        except Exception as e:
            fails.append(f"{nom} (Error Connexió)")
            
    return totes, ok, fails

# 4. PROCESSAMENT IA (GEMINI 1.5 FLASH)
def processar_ia(dades):
    if not dades: return "No hi ha dades.", [], 0
    historial = carregar_historial()
    
    # Filtrem només les novetats reals basant-nos en el títol
    noves = [d for d in dades if d['titol'] not in historial]
    if not noves: return "Cap novetat.", [], 0

    perfil = "Escola Nou Patufet (I3-4t ESO). Cooperativa. Prioritats: 1.Concerts, 2.Cooperativa (ESS), 3.Convenis, 4.Licitacions, 5.Erasmus, 6.Equitat, 7.Laboral."
    prompt = f"Analitza aquestes dades: {json.dumps(noves)}. Context: {perfil}. Respon JSON pur [] amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        # Netegem possibles respostes de la IA amb blocs de codi
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except: 
        return "Error en l'anàlisi de la IA.", [], len(noves)

    for s in interessants:
        try:
            nom_f = s['titol'][:45].replace("/", "-").replace(":", "").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf: 
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_f}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

# 5. GENERACIÓ DE WORD I DRIVE
def crear_fitxa_word(d):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for k in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{k}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(d.get(k, 'No especificat')))
        b = io.BytesIO(); doc.save(b); b.seek(0)
        return b
    except: return None

def pujar_a_drive(c, n, m):
    try:
        creds_json = json.loads(os.getenv("GDRIVE_CREDENTIALS"))
        creds = service_account.Credentials.from_service_account_info(creds_json)
        service = build('drive', 'v3', credentials=creds)
        # Corregit: assegurar que el buffer es llegeix bé
        media = MediaIoBaseUpload(io.BytesIO(c.read()) if hasattr(c, 'read') else io.BytesIO(c), mimetype=m)
        service.files().create(body={'name': n, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except Exception as e:
        print(f"Error Drive: {e}")

# 6. MAIL
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🚀 Patu-bot Informe: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(u, p); s.sendmail(u, r, msg.as_string())
    except: pass

# 7. MAIN
def main():
    print("Iniciant Patu-bot Ultra-Robust...")
    dades, ok, fails = cercar_fonts()
    resum_ia, interessants, n_reals = processar_ia(dades)
    
    # Actualitzem historial amb el que hem vist avui
    guardar_historial([d['titol'] for d in dades])
    
    informe = f"--- INFORME DIARI PATU-BOT ---\n\n"
    informe += f"✅ OK ({len(ok)}): {', '.join(ok)}\n"
    if fails: 
        informe += f"⚠️ ERROR ({len(fails)}): {', '.join(fails)}\n"
    
    informe += f"\n---------------------------------\n"
    if interessants:
        informe += f"S'han trobat {len(interessants)} oportunitats noves per a l'escola.\n"
        for s in interessants:
            informe += f"- [PRIO {s.get('prioritat', '?')}] {s['titol']} ({s.get('organisme', '-')})\n"
        informe += "\nLes fitxes s'han desat al Google Drive."
    else:
        informe += "Avui no hi ha novetats estratègiques."

    informe += f"\n---------------------------------\n"
    informe += f"Fonts analitzades avui: {len(dades)}\n"
    informe += f"Estat del sistema: Operatiu.\n"
    
    enviar_mail(informe)
    print("Procés finalitzat.")

if __name__ == "__main__": 
    main()
