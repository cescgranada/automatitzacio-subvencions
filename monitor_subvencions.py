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

# 1. CONFIGURACIÓ INICIAL
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
    historial = carregar_historial()
    # Mantenim els últims 300 títols per no repetir avisos
    historial_actualitzat = list(set(historial + llista_nova))[-300:]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(historial_actualitzat, f)

# 3. CERCA DE FONTS (AMB USER-AGENT PER EVITAR BLOQUEJOS)
def cercar_fonts():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    
    # Diaris Oficials (RSS/XML)
    fonts_oficials = [
        ("DOGC Subvencions", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("DOGC Europa", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB Barcelona", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}")
    ]
    
    # Webs de Fundacions (Scraping)
    privades = [
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories")
    ]
    
    totes_les_dades = []
    ok_list = []
    fail_list = []

    # Escaneig de Diaris
    for nom, url in fonts_oficials:
        try:
            res = requests.get(url, timeout=20, headers=headers)
            if res.status_code == 200:
                ok_list.append(nom)
                root = etree.fromstring(res.content, etree.XMLParser(recover=True))
                # El BOE té una estructura XML diferent als RSS comuns
                items = root.xpath("//item")
                for i in items[:25]:
                    titol = i.find('title').text if i.find('title') is not None else (i.find('titulo').text if i.find('titulo') is not None else "Sense títol")
                    link = i.find('link').text if i.find('link') is not None else (("https://www.boe.es" + i.find('url_pdf').text) if i.find('url_pdf') is not None else url)
                    totes_les_dades.append({"titol": titol, "link": link, "font": nom})
            else:
                fail_list.append(f"{nom} ({res.status_code})")
        except: fail_list.append(nom)

    # Escaneig de Fundacions
    for nom, url in privades:
        try:
            res = requests.get(url, timeout=20, headers=headers)
            if res.status_code == 200:
                ok_list.append(nom)
                soup = BeautifulSoup(res.text, 'html.parser')
                text_breu = ' '.join([p.get_text() for p in soup.find_all(['p', 'h2'])[:10]])
                totes_les_dades.append({"titol": f"Web: {nom}", "link": url, "font": "PRIVADA", "contingut": text_breu})
            else: fail_list.append(f"{nom} ({res.status_code})")
        except: fail_list.append(nom)
            
    return totes_les_dades, ok_list, fail_list

# 4. GESTIÓ DOCUMENTAL
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{clau}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(dades.get(clau, 'Pendent de concretar')))
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype):
    try:
        creds_info = json.loads(os.getenv("GDRIVE_CREDENTIALS"))
        creds = service_account.Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut) if isinstance(contingut, bytes) else contingut, mimetype=mimetype)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except Exception as e: print(f"Error Drive: {e}")

# 5. PROCESSAMENT ESTRATÈGIC (IA)
def processar_ia(dades):
    if not dades: return "Sense dades.", [], 0
    
    historial = carregar_historial()
    # Filtrem el que ja hem vist anteriorment
    noves = [d for d in dades if d['titol'] not in historial and d['link'] not in historial]
    
    if not noves: return "Cap novetat real.", [], 0

    perfil = """Escola Nou Patufet (I3-4t ESO). Cooperativa a Gràcia. 
    Prioritats: 1.Concerts, 2.Cooperativisme (ESS), 3.Convenis Districte, 4.Licitacions, 5.Erasmus+, 6.Equitat/Suport Alumnat, 7.Bonificacions Laborals."""
    
    prompt = f"Analitza aquestes {len(noves)} publicacions: {json.dumps(noves)}. Context: {perfil}. Respon JSON pur [] o llista d'objectes amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except: return "Error IA.", [], 0

    for s in interessants:
        try:
            nom_fitxer = s['titol'][:45].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_fitxer}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

# 6. ENVIAMENT D'ALERTES
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🚀 Patu-bot Informe: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

# 7. FUNCIÓ PRINCIPAL (MAIN)
def main():
    print("Iniciant Patu-bot v2026...")
    dades_brutes, ok_list, fail_list = cercar_fonts()
    resum_text, interessants, n_reals = processar_ia(dades_brutes)
    
    # Guardem tot el que hem vist avui a l'historial per no repetir-ho
    guardar_historial([d['titol'] for d in dades_brutes])
    
    cos = f"--- INFORME DIARI PATU-BOT ---\n\n"
    cos += f"✅ Fonts llegides correctament ({len(ok_list)}): {', '.join(ok_list)}\n"
    if fail_list:
        cos += f"⚠️ Fonts amb problemes ({len(fail_list)}): {', '.join(fail_list)}\n"
    
    cos += f"\n---------------------------------\n"
    if interessants:
        cos += f"S'han detectat {len(interessants)} oportunitats estratègiques:\n"
        for s in interessants:
            cos += f"- [PRIO {s.get('prioritat', '?')}] {s['titol']} ({s.get('organisme', 'Desconegut')})\n"
        cos += "\nLes fitxes detallades ja són al Google Drive."
    else:
        cos += "Avui no hi ha cap subvenció o conveni nou que s'ajusti al perfil."

    cos += f"\n---------------------------------\n"
    cos += f"Dades analitzades avui: {len(dades_brutes)}\n"
    cos += f"Estat del sistema: Operatiu i Saludable.\n"
    
    enviar_mail(cos)
    print("Procés finalitzat amb èxit.")

if __name__ == "__main__":
    main()
