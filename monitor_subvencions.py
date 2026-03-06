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

# 2. FONTS PÚBLIQUES (RSS/XML)
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "DOGC"} for i in root.xpath("//item")]
    except: return []

def cercar_europa():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "EUROPA"} for i in root.xpath("//item")]
    except: return []

def cercar_boe():
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        items = []
        for anunci in root.xpath("//seccion[@num='3']//item"):
            titol = anunci.find("titulo").text
            if any(p in titol.lower() for p in ["subvención", "ayuda", "beca", "convocatoria"]):
                items.append({"titol": titol, "link": "https://www.boe.es" + anunci.find("url_pdf").text, "font": "BOE"})
        return items
    except: return []

def cercar_bopb():
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        root = etree.fromstring(res.content, etree.XMLParser(recover=True))
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "BOPB (Barcelona)"} for i in root.xpath("//item")]
    except: return []

# 3. FONTS PRIVADES (WEB SCRAPING)
def cercar_privades():
    fonts = [
        {"nom": "Fundació la Caixa", "url": "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"},
        {"nom": "Fundació Bofill", "url": "https://fundaciobofill.cat/crides"},
        {"nom": "EduCaixa", "url": "https://educaixa.org/ca/convocatories"}
    ]
    resultats = []
    for f in fonts:
        try:
            res = requests.get(f['url'], timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            # Extraiem només el text net de la web per no saturar la IA
            text_net = ' '.join([p.get_text() for p in soup.find_all(['p', 'h2', 'h3'])])[:3000]
            resultats.append({"titol": f"Web: {f['nom']}", "link": f['url'], "font": "PRIVADA", "contingut_web": text_net})
        except: continue
    return resultats

# 4. GESTIÓ DE DOCUMENTS
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                if f'{{{{{clau}}}}}' in p.text:
                    p.text = p.text.replace(f'{{{{{clau}}}}}', str(dades.get(clau, 'No indicat')))
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype='application/pdf'):
    creds_json = os.getenv("GDRIVE_CREDENTIALS")
    if not creds_json: return
    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut) if isinstance(contingut, bytes) else contingut, mimetype=mimetype, resumable=True)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except Exception as e: print(f"Error Drive: {e}")

# 5. PROCESSAMENT IA
def processar_ia(llista):
    if not llista: return "Cap novetat.", []
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    perfil = """
    Escola Nou Patufet (I3-4t ESO). Gràcia, Bcn. Cooperativa.
    FILTRE EDAT: Només Infantil, Primària i ESO. Ignora Batxillerat i Universitat.
    INTERESSOS: Vulnerabilitat (Motxilles/Pla de Xoc), Innovació, STEAM, Menjador, Infraestructures i Economia Social.
    """
    
    prompt = f"Analitza: {json.dumps(llista)}. Perfil: {perfil}. Si és rellevant, genera un JSON pur (sense markdown) amb: titol, organisme, import, termini, resum, accions, link_pdf. Si no n'hi ha, respon []."
    
    res = model.generate_content(prompt)
    try:
        net = res.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except: return "Error d'anàlisi.", []

    for s in interessants:
        try:
            # Pujem PDF si és un link directe, o capturem la web
            nom_fitxer = s['titol'][:40].replace("/", "-")
            if s['link_pdf'].endswith('.pdf'):
                r = requests.get(s['link_pdf'], timeout=20)
                pujar_a_drive(r.content, f"ORIGINAL_{nom_fitxer}.pdf")
            
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"FITXA_{nom_fitxer}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
    return f"Trobades {len(interessants)} subvencions.", interessants

# 6. MAIL I MAIN
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    if not all([u, p, r]): return
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"Subvencions Nou Patufet {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p)
            server.sendmail(u, r, msg.as_string())
    except: pass

def main():
    print("Escanejant fonts públiques i privades...")
    dades = cercar_dogc() + cercar_europa() + cercar_boe() + cercar_bopb() + cercar_privades()
    resum, interessants = processar_ia(dades)
    
    if interessants:
        cos = "Noves oportunitats per a la Nou Patufet:\n\n"
        for s in interessants:
            cos += f"- {s['titol']} ({s['organisme']})\n  Import: {s['import']}\n\n"
        cos += "Documents al Drive."
        enviar_mail(cos)
    else:
        enviar_mail("Avui no hi ha novetats rellevants.")

if __name__ == "__main__":
    main()
