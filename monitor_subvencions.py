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
from google import genai  # Nova llibreria del 2026
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) # Nova forma de connectar
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# [Les funcions de cerca i reintents es mantenen igual...]
def peticio_amb_reintents(url, intents=3):
    for i in range(intents):
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200: return res
        except:
            time.sleep(5)
    return None

def carregar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def guardar_historial(llista_nova):
    historial = carregar_historial()
    historial_actualitzat = list(set(historial + llista_nova))[-200:]
    with open(HISTORIAL_FILE, "w") as f:
        json.dump(historial_actualitzat, f)

def cercar_fonts():
    # ... mateixa lògica de cerca que abans ...
    fonts_urls = [
        ("DOGC", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("EUROPA", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}")
    ]
    privades = [
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides")
    ]
    totes = []; consultades = 0
    for nom, url in fonts_urls:
        res = peticio_amb_reintents(url)
        if res:
            consultades += 1
            try:
                root = etree.fromstring(res.content, etree.XMLParser(recover=True))
                for i in root.xpath("//item")[:15]: # Limitem per no saturar
                    totes.append({"titol": i.find('title').text, "link": i.find('link').text, "font": nom})
            except: pass
    for nom, url in privades:
        res = peticio_amb_reintents(url)
        if res:
            consultades += 1
            soup = BeautifulSoup(res.text, 'html.parser')
            text = ' '.join([p.get_text() for p in soup.find_all(['p'])[:5]])
            totes.append({"titol": f"Web: {nom}", "link": url, "font": "PRIVADA", "contingut": text})
    return totes, consultades

# 4. PROCESSAMENT IA (ACTUALITZAT A API v1)
def processar_estrategic(dades):
    if not dades: return "Sense dades.", [], 0
    historial = carregar_historial()
    dades_noves = [d for d in dades if d['titol'] not in historial and d['link'] not in historial]
    
    if not dades_noves: return "Cap novetat.", [], 0

    perfil = "Escola Nou Patufet (I3-4t ESO). Cooperativa a Gràcia. Prioritat: 1.Concerts, 2.Cooperativisme, 3.Convenis, 4.Licitacions, 5.Erasmus, 6.Equitat, 7.Laboral."
    prompt = f"Analitza: {json.dumps(dades_noves)}. Context: {perfil}. Respon JSON pur [] o llista d'objectes amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        # Ús de la nova SDK de Gemini
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except Exception as e:
        print(f"Error IA: {e}")
        return "Error IA.", [], 0

    for s in interessants:
        try:
            nom = s['titol'][:40].replace("/", "-")
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(dades_noves)

# ... (Les funcions de Drive, Word i Mail es mantenen com en l'última versió operativa) ...
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                if f'{{{{{clau}}}}}' in p.text:
                    p.text = p.text.replace(f'{{{{{clau}}}}}', str(dades.get(clau, 'No indicat')))
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype):
    try:
        creds = service_account.Credentials.from_service_account_info(json.loads(os.getenv("GDRIVE_CREDENTIALS")))
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut) if isinstance(contingut, bytes) else contingut, mimetype=mimetype)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except: pass

def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🤖 Report Patu-bot: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

def main():
    print("Iniciant Patu-bot (v2026)...")
    dades, n_fonts = cercar_fonts()
    resum, interessants, n_noves = processar_estrategic(dades)
    guardar_historial([d['titol'] for d in dades])
    
    cos = f"Informe Patu-bot\n\nFonts: {n_fonts}\nNovetats: {n_noves}\nOportunitats: {len(interessants)}"
    enviar_mail(cos)

if __name__ == "__main__":
    main()
