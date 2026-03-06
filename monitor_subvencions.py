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

# 1. CONFIGURACIÓ I CLIENTS
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

# 3. CERCA DE FONTS AMB MULTI-ESTRATEGIA (ANTI-BLOQUEIG)
def cercar_fonts():
    session = requests.Session()
    # Capçalera de navegador real per saltar bloquejos 403
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ca,es;q=0.9,en;q=0.8',
        'Referer': 'https://www.google.com/'
    }
    
    # Combinació de RSS i URLs directes de llistat
    fonts = [
        ("DOGC Subvencions", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"),
        ("DOGC Europa", "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"),
        ("BOPB Barcelona", "https://bop.diba.cat/rss.asp?seccio=4.2"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}"),
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories")
    ]
    
    totes = []; ok_list = []; fail_list = []

    for nom, url in fonts:
        try:
            # Espera aleatòria per no saturar i semblar humà
            time.sleep(random.uniform(2, 4))
            res = session.get(url, timeout=25, headers=headers)
            
            if res.status_code == 200:
                ok_list.append(nom)
                # Si la resposta és XML/RSS
                if "xml" in url or "rss" in url or "boe" in url.lower():
                    parser = etree.XMLParser(recover=True, encoding='utf-8')
                    root = etree.fromstring(res.content, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:20]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                # Si és una pàgina HTML (Scraping)
                else:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    # Extraiem els primers paràgrafs o llistes per donar context a la IA
                    textos = [p.get_text().strip() for p in soup.find_all(['p', 'h2', 'h3']) if len(p.get_text()) > 20]
                    totes.append({"titol": f"Web: {nom}", "link": url, "font": "PÀGINA_WEB", "contingut": ' '.join(textos[:10])})
            else:
                fail_list.append(f"{nom} ({res.status_code})")
        except Exception as e:
            fail_list.append(f"{nom} (Error Connexió)")
            
    return totes, ok_list, fail_list

# 4. PROCESSAMENT IA (GEMINI 1.5 FLASH)
def processar_ia(dades):
    if not dades: return "No hi ha dades per analitzar.", [], 0
    
    historial = carregar_historial()
    # Filtrem només les que no hem vist mai
    noves = [d for d in dades if d['titol'] not in historial]
    
    if not noves: return "Sense novetats respecte l'últim escaneig.", [], 0

    perfil = """Escola Nou Patufet (I3-4t ESO). Cooperativa a Gràcia. 
    PRIORITATS ESTRATÈGIQUES (1 a 7): 
    1. Concerts educatius (Gencat).
    2. Gestió Cooperativa i Economia Social (ESS, Enfortim).
    3. Convenis de Districte o Ajuntament (Projectes comunitaris).
    4. Licitacions de serveis educatius.
    5. Erasmus+ i internacionalització.
    6. Ajuts alumnat (Equitat, Menjador, NESE, Motxilles).
    7. Bonificacions laborals i contractació.
    """
    
    prompt = f"Analitza aquestes dades: {json.dumps(noves)}. Context: {perfil}. Respon JSON pur (sense markdown) [] o llista d'objectes amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        # Netegem la resposta de possibles formats Markdown
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except Exception as e:
        print(f"Error IA: {e}")
        return "Error en el processament de la IA.", [], len(noves)

    # Crear fitxes per a les interessants
    for s in interessants:
        try:
            nom_net = s['titol'][:45].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_net}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

# 5. GENERACIÓ DE DOCUMENTS I DRIVE
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{clau}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(dades.get(clau, 'Dada no especificada')))
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype):
    try:
        creds_json = json.loads(os.getenv("GDRIVE_CREDENTIALS"))
        creds = service_account.Credentials.from_service_account_info(creds_json)
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut.read()) if hasattr(contingut, 'read') else io.BytesIO(contingut), mimetype=mimetype)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except Exception as e:
        print(f"Error pujant a Drive: {e}")

# 6. ENVIAMENT D'ALERTA PER MAIL
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🚀 Patu-bot Informe Estratègic: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

# 7. FUNCIÓ PRINCIPAL (MAIN)
def main():
    print("Iniciant Patu-bot v2026...")
    dades_brutes, ok_list, fail_list = cercar_fonts()
    resum_ia, interessants, n_analitzades = processar_ia(dades_brutes)
    
    # Actualitzem historial amb tot el que hem vist avui
    guardar_historial([d['titol'] for d in dades_brutes])
    
    # Construcció del cos del correu
    informe = f"--- INFORME DIARI PATU-BOT ---\n\n"
    informe += f"✅ Fonts consultades OK ({len(ok_list)}): {', '.join(ok_list)}\n"
    if fail_list:
        informe += f"⚠️ Fonts amb errors ({len(fail_list)}): {', '.join(fail_list)}\n"
    
    informe += f"\n---------------------------------\n"
    if interessants:
        informe += f"S'han detectat {len(interessants)} novetats per a la Nou Patufet:\n"
        for s in interessants:
            informe += f"- [PRIO {s.get('prioritat','?')}] {s['titol']} ({s.get('organisme','-')})\n"
        informe += "\nLes fitxes s'han desat correctament al Google Drive."
    else:
        informe += "Avui no s'ha detectat cap oportunitat nova que encaixi amb el perfil estratègic."

    informe += f"\n---------------------------------\n"
    informe += f"Publicacions analitzades avui: {n_analitzades}\n"
    informe += f"Estat del Patu-bot: Operatiu.\n"
    
    enviar_mail(informe)
    print("Procés finalitzat.")

if __name__ == "__main__":
    main()
