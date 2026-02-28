import requests
from lxml import etree # Canviem la llibreria per una de més potent
from datetime import datetime

def cercar_dogc():
    print("Consultant DOGC...")
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        # Fem servir un parser que ignora errors de caràcters (recover=True)
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        root = etree.fromstring(res.content, parser=parser)
        
        items = []
        # Al DOGC el format és una mica diferent amb lxml
        for item in root.xpath("//item"):
            titol = item.find('title').text
            enllac = item.find('link').text
            items.append(f"DOGC: {titol}\nLink: {enllac}\n")
        return items
    except Exception as e:
        print(f"Error DOGC: {e}")
        return []

def cercar_boe():
    print("Consultant BOE...")
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return ["BOE: Avui encara no hi ha dades publicades."]
        
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        
        items = []
        # Busquem secció 3
        for seccio in root.xpath("//seccion[@num='3']"):
            for anunci in seccio.xpath(".//item"):
                titol = anunci.find("titulo").text
                paraules_clau = ["subvención", "ayuda", "convocatoria", "subvencions"]
                if any(p in titol.lower() for p in paraules_clau):
                    link = "https://www.boe.es" + anunci.find("url_pdf").text
                    items.append(f"BOE: {titol}\nLink: {link}\n")
        return items
    except Exception as e:
        print(f"Error BOE: {e}")
        return []

def main():
    subvencions = cercar_dogc() + cercar_boe()
    
    if not subvencions:
        resum_final = "No s'ha trobat cap subvenció rellevant avui."
    else:
        resum_final = f"--- RESUM DE SUBVENCIONS ({datetime.now().strftime('%d/%m/%Y')}) ---\n\n"
        resum_final += "\n".join(subvencions)
    
    print(resum_final)
    
    with open("ultim_resum.txt", "w", encoding="utf-8") as f:
        f.write(resum_final)

if __name__ == "__main__":
    main()
