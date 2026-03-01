🤖 Patu-Bot: Gestor Intel·ligent de Subvencions per a Escoles
Aquest sistema és un administratiu virtual d'alt rendiment per a l'Escola Nou Patufet. El robot revisa diàriament els diaris oficials, selecciona oportunitats mitjançant Intel·ligència Artificial i genera tota la documentació prèvia per a la direcció del centre.

🌟 Funcions Principals
Monitoratge 360°: Escaneja el BOE (Estat), DOGC (Generalitat), BOPB (Ajuntament de Barcelona/Diputació) i portals de fons europeus (Erasmus+, Next Generation).

Filtrat per IA (Gemini 1.5 Flash): Selecciona només les subvencions que encaixen amb el perfil de l'escola (vulnerabilitat, motxilles econòmiques, infraestructures, etc.).

Generació de Fitxes: Omple automàticament una plantilla de Word (plantilla_subvencio.docx) amb les dades clau.

Arxiu al Drive: Guarda el PDF original i la fitxa de Word a la teva carpeta de Google Drive sense intervenció humana.

Alertes per Correu: Envia un resum executiu cada matí a les 07:30h.

📋 Requisits per a la instal·lació
Si vols utilitzar aquesta plantilla al teu compte de GitHub, necessitaràs:

Google AI API Key: Gratis a Google AI Studio.

Gmail i "Contrasenya d'aplicació": Per l'enviament de correus.

Credencials de Google Cloud (JSON): Per la connexió amb Google Drive.

ID de Carpeta de Drive: On es desaran els documents.

🚀 Guia ràpida de configuració
1. Preparar el Repositori
Clica el botó verd "Use this template" > "Create a new repository".

2. Configurar els Secrets de GitHub
Ves a Settings > Secrets and variables > Actions i afegeix aquests 5 secrets:

GEMINI_API_KEY: La teva clau de la IA.

EMAIL_USER: El teu correu de Gmail.

EMAIL_PASS: El codi de 16 lletres de Google.

EMAIL_RECEIVER: El correu on vols rebre els avisos.

GDRIVE_CREDENTIALS: El contingut sencer del fitxer JSON de Google Cloud.

3. Personalitzar el teu Perfil
Edita el fitxer monitor_subvencions.py:

Busca la variable GDRIVE_FOLDER_ID i posa l'ID de la teva carpeta de Drive.

Busca la variable perfil i descriu la teva entitat (què busqueu i on sou).

4. Personalitzar la Plantilla
Descarrega el fitxer plantilla_subvencio.docx, adapta'l amb el teu logo i puja'l de nou. Assegura't de mantenir les etiquetes: {{titol}}, {{organisme}}, {{import}}, {{termini}}, {{resum}} i {{accions}}.

5. Activar el Cron (El rellotge)
Ves a la pestanya Actions i clica el botó blau "Enable Actions".

⏰ Com funciona el calendari?
El robot s'activa de dilluns a divendres a les 07:30h (CET).

Si hi ha subvencions: Rebràs el resum i tindràs els fitxers al Drive.

Si no hi ha res: Rebràs un correu confirmant que tot s'ha revisat però no hi ha novetats.
