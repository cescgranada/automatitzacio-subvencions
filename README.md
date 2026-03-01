🤖 Cercador i Gestor Automàtic de Subvencions
Aquest sistema és un "administratiu virtual" per a escoles i entitats. Cada matí revisa els diaris oficials (BOE, DOGC, BOPB), filtra les subvencions amb IA i, si en troba una de rellevant:

Et descarrega el PDF original.

Omple una fitxa de Word amb el resum, l'import i els terminis.

Ho guarda tot a la teva carpeta de Google Drive.

📋 Requisits previs
Necessitaràs tenir a mà:

Google AI API Key: Aconsegueix-la gratis a Google AI Studio.

Correu de Gmail i "Contrasenya d'aplicació": Per enviar els avisos.

Credencials de Google Cloud (JSON): Perquè el robot pugui escriure al teu Drive.

ID d'una carpeta de Drive: On es guardaran els documents.

🚀 Com configurar-ho (Pas a pas)
1. Crear el teu repositori
Clica el botó verd "Use this template" > "Create a new repository".

2. Configurar la teva Plantilla de Word
Al teu repositori veuràs un fitxer anomenat plantilla_subvencio.docx.

Pots descarregar-lo, posar-hi el teu logo i dissenyar-lo com vulguis, sempre que mantinguis aquestes etiquetes: {{titol}}, {{organisme}}, {{import}}, {{termini}}, {{resum}} i {{accions}}.

3. Afegir les teves claus (Secrets)
Ves a Settings > Secrets and variables > Actions i afegeix aquests 5 secrets:

GEMINI_API_KEY: La teva clau de la IA.

EMAIL_USER: El teu correu de Gmail.

EMAIL_PASS: El codi de 16 lletres de Google.

EMAIL_RECEIVER: On vols rebre els avisos.

GDRIVE_CREDENTIALS: El contingut sencer del fitxer JSON de Google Cloud.

4. Personalitzar el perfil i la carpeta
Edita el fitxer monitor_subvencions.py:

Canvia la variable GDRIVE_FOLDER_ID pel codi de la teva carpeta de Drive.

Canvia la variable perfil (dins la funció de la IA) per descriure la teva escola i què busques (ex: motxilles econòmiques, menjadors, etc.).

5. Activar el robot
Ves a la pestanya Actions i clica el botó blau per activar els permisos ("Enable Actions").

⏰ Què passarà a partir d'ara?
Cada matí a les 07:30h, el robot treballarà per tu. Si troba una subvenció rellevant, rebràs un correu i tindràs la documentació a punt a la teva carpeta de Drive. Si no hi ha res d'interès, no s'omplirà la carpeta de brossa.

Consell d'expert: Recorda compartir la teva carpeta de Drive amb el correu de la "Service Account" de Google Cloud amb permís d'Editor, si no el robot no podrà guardar-hi els fitxers!
