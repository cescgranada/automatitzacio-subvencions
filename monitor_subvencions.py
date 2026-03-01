import requests
import os
import smtplib
import io
import json
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

# 2. FUNCIONS DE CERCA (BOE, DOGC, BOPB)
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "DOGC"} for i in root.xpath("//item")]
    except: return []

def cercar_boe():
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        items = []
        for anunci in root.xpath("//seccion[@num='3']//item"):
            titol = anunci.find("titulo").text
            if any(p in titol.lower() for p in ["subvención", "ayuda", "convocatoria", "subvencions"]):
                link = "https://www.boe.es" + anunci.find("url_pdf").text
                items.append({"titol": titol, "link": link, "font": "BOE"})
        return items
    except: return []

def cercar_bopb():
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "BOPB"} for i in root.xpath("//item")]
    except: return []

# 3. FUNCIÓ PER OMPLIR LA PLANTILLA DE WORD
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            if '{{titol}}' in p.text: p.text = p.text.replace('{{titol}}', dades.get('titol', ''))
            if '{{organisme}}' in p.text: p.text = p.text.replace('{{organisme}}', dades.get('organisme', ''))
            if '{{import}}' in p.text: p.text = p.text.replace('{{import}}', dades.get('import', ''))
            if '{{termini}}' in p.text: p.text = p.text.replace('{{termini}}', dades.get('termini', ''))
            if '{{resum}}' in p.text: p.text = p.text.replace('{{resum}}', dades.get('resum', ''))
            if '{{accions}}' in p.text: p.text = p.text.replace('{{accions}}', dades.get('accions', ''))
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error creant Word: {e}")
        return None

# 4. PUJAR A DRIVE
def pujar_a_drive(contingut_binari, nom_arxiu, mimetype='application/pdf'):
    creds_json = os.getenv("GDRIVE_CREDENTIALS")
    if not creds_json: return
    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        service = build('drive', 'v3', credentials=creds)
        
        fh = io.BytesIO(contingut_binari) if isinstance(contingut_binari, bytes) else contingut_binari
        file_metadata = {'name': nom_arxiu, 'parents': [GDRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(fh, mimetype=mimetype, resumable=True)
        service.files().create(body=file_metadata, media_body=media).execute()
    except Exception as e: print(f"Error Drive: {e}")

# 5. IA I PROCESSAMENT
def processar_amb_ia(llista):
    if not llista: return "Avui no hi ha novetats.", []
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    perfil = "Escola cooperativa a Gràcia. Busquem: motxilles econòmiques, pla de xoc, vulnerabilitat, infraestructures i digitalització."
    
    prompt = f"""
    Analitza: {json.dumps(llista)}
    Perfil: {perfil}
    Si una subvenció és rellevant, genera un objecte JSON per a cadascuna amb aquestes claus:
    "titol", "organisme", "import", "termini", "resum", "accions", "link_pdf".
    Respon NOMÉS amb el llistat JSON de les rellevants.
    """
    
    res = model.generate_content(prompt)
    try:
        # Netegem la resposta de la IA per si posa markdown
        net = res.text.replace("```json", "").replace("```", "").strip()
        subvencions_interessants = json.loads(net)
    except: return res.text, []

    for s in subvencions_interessants:
        # 1. Guardem PDF original
        pdf_res = requests.get(s['link_pdf'])
        pujar_a_drive(pdf_res.content, f"Original_{s['titol'][:30]}.pdf")
        
        # 2. Creem i guardem Fitxa Word
        word_buf = crear_fitxa_word(s)
        if word_buf:
            pujar_a_drive(word_buf, f"FITXA_{s['titol'][:30]}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    return "S'han trobat i arxivat subvencions rellevants. Revisa el Drive.", subvencions_interessants

# 6. MAIL I MAIN
def enviar_correu(text):
    sender = os.getenv("EMAIL_USER")
    passw = os.getenv("EMAIL_PASS")
    dest = os.getenv("EMAIL_RECEIVER")
    if not all([sender, passw, dest]): return
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"Subvencions Nou Patufet - {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, passw)
            server.sendmail(sender, dest, msg.as_string())
    except: pass

def main():
    dades = cercar_dogc() + cercar_boe() + cercar_bopb()
    resum_text, interessants = processar_amb_ia(dades)
    enviar_correu(resum_text)

if __name__ == "__main__":
    main()
