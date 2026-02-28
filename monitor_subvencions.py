import requests
import xml.etree.ElementTree as ET
from datetime import datetime

def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    res = requests.get(url)
    root = ET.fromstring(res.content)
    items = []
    for item in root.findall(".//item")[:5]: # Agafem els 5 últims per provar
        items.append(f"DOGC: {item.find('title').text} - {item.find('link').text}")
    return items

def cercar_boe():
    # Simplificat: RSS de la secció de subvencions del BOE
    url = "https://www.boe.es/diario_boe/xml.php?id=BOE-S-20240522" # Hauria de ser la data d'avui
    # Aquí aniria la lògica de l'XML del BOE explicada abans
    return ["BOE: Prova de connexió activa"]

def enviar_notificacio(text):
    # Aquí pots configurar l'enviament de mail o Telegram
    print("ENVIANT RESUM:\n", text)

if __name__ == "__main__":
    resultats = cercar_dogc() + cercar_boe()
    if resultats:
        enviar_notificacio("\n".join(resultats))
