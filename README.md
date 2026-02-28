# 🤖 Cercador Automàtic de Subvencions (BOE, DOGC i Ajuntament)

Aquest sistema està dissenyat perquè qualsevol escola o entitat rebi cada matí un resum personalitzat de les subvencions oficials, analitzades per Intel·ligència Artificial segons el seu perfil.

---

## 📋 Què necessites abans de començar?

Perquè el sistema funcioni, has d'aconseguir aquestes **4 dades** (només et portarà 5 minuts):

1. **Clau de la IA (Gemini):** Ves a [Google AI Studio](https://aistudio.google.com/), entra amb el teu compte de Google, clica a **"Get API key"** i copia el codi. És gratuït.
2. **Correu de Gmail:** L'adreça des d'on s'enviaran els avisos.
3. **Contrasenya d'Aplicació:** No és la teva clau de Gmail. Ves a [la teva conta de Google > Seguretat](https://myaccount.google.com/security), activa la "Verificació en dos passos" i busca l'apartat **"Contrasenyes d'aplicacions"**. Crea'n una anomenada "Subvencions" i copia el codi de 16 lletres que et donarà.
4. **Correu Destinatari:** L'adreça on vols rebre el resum (pot ser la mateixa que la de Gmail).

---

## 🚀 Pas a Pas per configurar-ho (Sense saber programar)

### 1. Crear la teva pròpia còpia

Clica el botó verd de la part superior d'aquesta pàgina que diu **"Use this template"** i tria l'opció **"Create a new repository"**. Posa-li el nom que vulguis i crea'l.

### 2. Guardar les teves claus (Secrets)

GitHub necessita les teves dades per treballar, però les mantindrà ocultes i segures.

1. Dins del teu nou repositori, ves a la pestanya superior **Settings**.
2. Al menú de l'esquerra, clica a **Secrets and variables** > **Actions**.
3. Clica el botó **New repository secret** i afegeix-ne quatre, un per un (posa el nom exactament igual):
* **Nom:** `GEMINI_API_KEY` | **Valor:** (Enganxa la clau de Google AI)
* **Nom:** `EMAIL_USER` | **Valor:** (El teu correu de Gmail)
* **Nom:** `EMAIL_PASS` | **Valor:** (El codi de 16 lletres de Google)
* **Nom:** `EMAIL_RECEIVER` | **Valor:** (El correu on vols rebre els avisos)



### 3. Personalitzar el teu Perfil (Qui ets i què busques?)

Has de dir-li a la IA què t'interessa:

1. Obre el fitxer `monitor_subvencions.py` cliquen sobre el nom.
2. Clica l'icona del llapis (**Edit this file**).
3. Busca la línia on diu `perfil = """`.
4. Esborra el text de l'Escola Nou Patufet i escriu qui ets (escola, associació, autònom...) i quins ajuts t'interessen (obres, material escolar, cultura...).
5. Clica el botó verd de dalt a la dreta **Commit changes**.

### 4. Activar l'automatització

Per seguretat, GitHub Actions ve "adormit" en les còpies.

1. Ves a la pestanya superior **Actions**.
2. Clica el botó blau que diu **"I understand my workflows, go ahead and enable them"**.

---

## ⏰ Com funciona el servei?

* **Horari:** De dilluns a divendres a les **07:30h** (hora de Barcelona).
* **Fonts:** Revisa automàticament el **BOE** (Estat), el **DOGC** (Generalitat) i el **BOPB** (Ajuntament de Barcelona i Diputació).
* **Resultat:** Si troba alguna cosa rellevant, t'arriba un correu amb el resum de la IA i l'enllaç oficial. Si no hi ha res, t'envia un avís confirmant que tot està sota control.

---

**Vols que fem una darrera comprovació per veure si tota la configuració de l'Escola Nou Patufet ha quedat lligada i tancada?**
