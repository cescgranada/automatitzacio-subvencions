import requests
import os
import smtplib
import io
import json
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"

# 2. FONTS PÚBLIQUES, COOPERATIVES I INTERNACIONALS
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "DOGC (Empresa/Educació)"} for i in root.xpath("//item")]
    except: return []

def cercar_boe():
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        items = []
        for anunci in root.xpath("//item"):
            titol = anunci.find("titulo").text.lower()
            # Filtre per detectar bonificacions, economia social i concerts
            paraules_clau = ["subvención", "ayuda", "concierto", "bonificación", "cooperativa", "economía social"]
            if any(p in titol for p in paraules_clau):
                items.append({"titol": anunci.find("titulo").text, "link": "https://www.boe.es" + anunci.find("url_pdf").text, "font": "BOE"})
        return items
    except: return []

def cercar_bopb():
    # Crucial per a l'Ajuntament de Barcelona (Enfortim l'ESS i Districte)
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "BOPB (Barcelona/ESS)"} for i in root.xpath("//item")]
    except: return []

def cercar_europa():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "EUROPA (Erasmus+)"} for i in root.xpath("//item")]
    except: return []

# 3. GESTIÓ DE DOCUMENTS (WORD I DRIVE)
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{clau}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(dades.get(clau, 'No indicat')))
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype='application/pdf'):
    creds_json = os.getenv("GDRIVE_CREDENTIALS")
    if not creds_json: return
    try:
        creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut) if isinstance(contingut, bytes) else contingut, mimetype=mimetype, resumable=True)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except Exception as e: print(f"Error Drive: {e}")

# 4. PROCESSAMENT IA AMB PRIORITATS DE COOPERATIVA
def processar_ia(llista):
    if not llista: return "Cap novetat.", []
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    perfil = """
    Escola Nou Patufet (I3-4t ESO). Escola Cooperativa a Gràcia.
    ESTRATEGIA DE FILTRAT (Prioritat de 1 a 7):
    1. CONCERTS EDUCATIUS: Renovació/modificació amb Generalitat.
    2. ECONOMIA SOCIAL I COOPERATIVA: Ajuts per a cooperatives (Enfortim ESS, incorporació socis, millora governança).
    3. CONVENIS: Ajuntament/Districte per projectes de barri o ús d'espais.
    4. LICITACIONS: Serveis educatius i extraescolars.
    5. ERASMUS+: Internacionalització i formació de professorat.
    6. ALUMNAT: Vulnerabilitat, menjador, accessibilitat (Motxilles/NESE).
    7. LABORAL: Bonificacions per a nova contractació i formació.
    """
    
    prompt = f"Analitza: {json.dumps(llista)}. Context: {perfil}. Respon JSON pur (sense markdown) amb camps: titol, prioritat, organisme, import, termini, resum, accions, link_pdf. Si no és rellevant, respon []."
    
    res = model.generate_content(prompt)
    try:
        net = res.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except: return "Error d'anàlisi.", []

    interessants.sort(key=lambda x: x.get('prioritat', 9))

    for s in interessants:
        try:
            nom = s['titol'][:40].replace("/", "-")
            if s['link_pdf'].endswith('.pdf'):
                r = requests.get(s['link_pdf'], timeout=20)
                pujar_a_drive(r.content, f"ORIGINAL_PRIO{s['prioritat']}_{nom}.pdf")
            
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"FITXA_PRIO{s['prioritat']}_{nom}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
    return f"Trobades {len(interessants)} oportunitats.", interessants

# 5. MAIL I MAIN
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    if not all([u, p, r]): return
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"Gestió Nou Patufet {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

def main():
    print("Escanejant fons educatius i cooperatius...")
    dades = cercar_dogc() + cercar_europa() + cercar_boe() + cercar_bopb()
    resum, interessants = processar_ia(dades)
    
    if interessants:
        cos = "Resum d'oportunitats per a la Cooperativa:\n\n"
        for s in interessants:
            cos += f"[Prio {s['prioritat']}] {s['titol']} ({s['organisme']})\nImport: {s['import']}\n\n"
        cos += "Documents al Drive."
        enviar_mail(cos)
    else: enviar_mail("Avui no hi ha novetats rellevants.")

if __name__ == "__main__":
    main()
