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
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ I SEGURETAT
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# 2. FUNCIONS DE SUPORT (ROBUSTESA)
def peticio_amb_reintents(url, intents=3):
    for i in range(intents):
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200: return res
        except:
            time.sleep(5) # Espera 5 segons abans de reintentar
    return None

def carregar_historial():
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r") as f: return json.load(f)
    return []

def guardar_historial(llista_nova):
    historial = carregar_historial()
    # Mantenim només els últims 200 IDs per no fer el fitxer gegant
    historial_actualitzat = list(set(historial + llista_nova))[-200:]
    with open(HISTORIAL_FILE, "w") as f:
        json.dump(historial_actualitzat, f)

# 3. FONTS (AMB REINTENTS)
def cercar_fonts():
    fonts_urls = [
        ("DOGC", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("EUROPA", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}")
    ]
    
    privades = [
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories")
    ]
    
    totes_les_dades = []
    fonts_consultades = 0
    
    # Processar RSS/XML
    for nom, url in fonts_urls:
        res = peticio_amb_reintents(url)
        if res:
            fonts_consultades += 1
            try:
                root = etree.fromstring(res.content, etree.XMLParser(recover=True))
                # Lògica d'extracció segons si és BOE o RSS
                if nom == "BOE":
                    for item in root.xpath("//item"):
                        t = item.find("titulo").text
                        if any(p in t.lower() for p in ["subvención", "ayuda", "beca", "concierto", "cooperativa"]):
                            totes_les_dades.append({"titol": t, "link": "https://www.boe.es" + item.find("url_pdf").text, "font": nom})
                else:
                    for i in root.xpath("//item"):
                        totes_les_dades.append({"titol": i.find('title').text, "link": i.find('link').text, "font": nom})
            except: pass

    # Processar Webs Privades
    for nom, url in privades:
        res = peticio_amb_reintents(url)
        if res:
            fonts_consultades += 1
            soup = BeautifulSoup(res.text, 'html.parser')
            text = ' '.join([p.get_text() for p in soup.find_all(['p', 'h2'])])[:2000]
            totes_les_dades.append({"titol": f"Web: {nom}", "link": url, "font": "PRIVADA", "contingut": text})
            
    return totes_les_dades, fonts_consultades

# 4. PROCESSAMENT IA I DRIVE (AMB FILTRE DE DUPLICATS)
def processar_estrategic(dades):
    if not dades: return "No s'han trobat dades noves.", [], 0
    
    historial = carregar_historial()
    # Filtrem dades que ja hem vist (pel títol o link) per no enviar-les a la IA
    dades_noves = [d for d in dades if d['titol'] not in historial and d['link'] not in historial]
    
    if not dades_noves: return "Sense novetats respecte l'última vegada.", [], 0

    model = genai.GenerativeModel('gemini-1.5-flash')
    perfil = """Escola Nou Patufet (I3-4t ESO). Cooperativa a Gràcia. 
    ORDRE: 1.Concerts, 2.Cooperativisme (ESS), 3.Convenis Districte, 4.Licitacions, 5.Erasmus+, 6.Equitat/Alumnat, 7.Laboral."""
    
    prompt = f"Analitza: {json.dumps(dades_noves)}. Respon JSON pur [] si no hi ha res rellevant, o llista d'objectes amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    res = model.generate_content(prompt)
    try:
        interessants = json.loads(res.text.replace("```json", "").replace("```", "").strip())
    except: return "Error IA.", [], 0

    ids_processats = [d['titol'] for d in dades_noves] # Guardem tot el que hem analitzat avui
    
    for s in interessants:
        try:
            nom_net = s['titol'][:40].replace("/", "-")
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_net}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(dades_noves)

# [LES FUNCIONS crear_fitxa_word, pujar_a_drive I enviar_mail ES MANTENEN IGUAL]
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
    msg['Subject'] = f"🤖 Patu-bot Report: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

# 5. EXECUCIÓ PRINCIPAL
def main():
    print("Iniciant Patu-bot...")
    dades_brutes, n_fonts = cercar_fonts()
    resum_text, interessants, n_noves = processar_estrategic(dades_brutes)
    
    # Guardem l'historial del que hem vist avui per no repetir demà
    ids_vists = [d['titol'] for d in dades_brutes]
    guardar_historial(ids_vists)
    
    cos_mail = f"--- INFORME DIARI PATU-BOT ---\n\n"
    if interessants:
        cos_mail += f"S'han detectat {len(interessants)} oportunitats noves:\n"
        for s in interessants:
            cos_mail += f"- [PRIO {s['prioritat']}] {s['titol']}\n"
    else:
        cos_mail += "Avui no hi ha subvencions noves que encaixin amb el perfil.\n"
    
    cos_mail += f"\n--- DIAGNÒSTIC DEL SISTEMA ---\n"
    cos_mail += f"✅ Fonts consultades: {n_fonts} fonts oficials i privades.\n"
    cos_mail += f"✅ Publicacions analitzades avui: {len(dades_brutes)}.\n"
    cos_mail += f"✅ Novetats reals detectades: {n_noves}.\n"
    cos_mail += f"🕒 Propera revisió: Demà a les 07:30h.\n"
    
    enviar_mail(cos_mail)

if __name__ == "__main__":
    main()
