# Sofia installeren — stap voor stap

Deze handleiding gaat ervan uit dat je **nog nooit** iets met programmeren hebt gedaan.
Doe de stappen **in volgorde**. Sla niets over. Na elke stap staat wat je moet zien.

⏱️ Totale tijd: ongeveer 45 minuten.

---

## Wat heb je nodig?

- ✅ Een **computer** met Windows of een Mac (geen tablet, geen telefoon).
- ✅ **Telegram** op je telefoon (heb je al).
- ✅ Een **betaalkaart** (creditcard of debitcard) voor OpenAI. Je betaalt vooraf, bijvoorbeeld $10.
- ✅ Een **kladblok** om tijdelijk twee codes in te bewaren:
  - Windows: het programma *Kladblok* (Start → typ *Kladblok*).
  - Mac: het programma *Notities*.

> 🔒 **Belangrijk:** je krijgt straks twee geheime codes: een **Telegram-token** en een **OpenAI-sleutel**.
> Die zijn als een wachtwoord. Geef ze aan **niemand**, ook niet in een chat.
> Je telefoonnummer hoef je **nergens** in te vullen.

---

## Overzicht

| Deel | Wat | Tijd |
|---|---|---|
| A | Telegram op je computer zetten | 5 min |
| B | Een bot maken bij BotFather → **code 1** (token) | 5 min |
| C | Een OpenAI-account met tegoed → **code 2** (sleutel) | 15 min |
| D | Python installeren | 5 min |
| E | Sofia downloaden | 5 min |
| F | Sofia starten en de vragen beantwoorden | 10 min |
| G | Met Sofia praten | — |
| H | De volgende keren | — |

---

## Deel A — Telegram op je computer

Je moet straks een lange code kopiëren. Dat gaat het makkelijkst als Telegram ook op je computer open staat.

1. Ga op je computer naar **https://web.telegram.org**
2. Kies **Log in by phone number** (inloggen met telefoonnummer).
3. Vul je telefoonnummer in.
4. Telegram stuurt een code naar je **telefoon** (in de Telegram-app). Typ die code over op de computer.

✔️ **Je ziet:** je eigen Telegram-chats op je computerscherm.

---

## Deel B — Een bot maken (code 1)

1. Klik in Telegram (op je computer) linksboven op het **zoekvak**.
2. Typ: **BotFather**
3. Klik op **BotFather** met het **blauwe vinkje** ✔️. (Niet een andere — er zijn nepversies.)
4. Klik onderaan op **START**.
5. Typ: **/newbot** en druk op **Enter**.
6. BotFather vraagt een naam. Typ: **Sofia** en druk op **Enter**.
7. BotFather vraagt een gebruikersnaam. Die moet **uniek** zijn en eindigen op **bot**.
   Gebruik alleen gewone letters (zonder accenten), cijfers en het liggende streepje **_**.
   Bijvoorbeeld: **sofia_bram_2026_bot**
   - Zegt BotFather *"Sorry, this username is already taken"*? Dan bestaat die al. Probeer andere cijfers.
8. BotFather stuurt een bericht met **Done! Congratulations**. Daarin staat een lange code na
   *"Use this token to access the HTTP API:"*. Die ziet eruit zoals:
   `7123456789:AAH4kPz...` (cijfers, een dubbele punt, en dan heel veel letters).
9. **Kopieer die code:** klik erop (vaak wordt hij dan al gekopieerd), of selecteer hem met de muis en druk
   **Ctrl+C** (Mac: **Cmd+C**).
10. Plak hem in je **Kladblok / Notities** (**Ctrl+V**, Mac: **Cmd+V**). Zet erboven: *Telegram-token*.

✔️ **Je hebt nu:** code 1 in je kladblok.

**Extra veiligheid (1 minuut):**

11. Typ in BotFather: **/setjoingroups** → klik op je nieuwe bot → klik **Disable**.
    Nu kan niemand je bot aan een groep toevoegen.

---

## Deel C — OpenAI-account met tegoed (code 2)

> ⚠️ Dit is **niet** hetzelfde als ChatGPT. Ook als je ChatGPT Plus betaalt, moet je dit apart doen.
> Je betaalt hier vooraf een bedrag (tegoed). Sofia verbruikt daar een klein beetje van per bericht.

1. Ga naar **https://platform.openai.com**
2. Klik op **Sign up** (aanmelden) of **Log in** als je al een account hebt.
   Je mag hetzelfde account gebruiken als voor ChatGPT.
3. Klik rechtsboven op het **tandwiel** ⚙️ (**Settings**).
4. Klik links op **Billing**.
5. Klik op **Add payment details** → kies **Individual** (privépersoon) → vul je kaart in.
6. Vul een bedrag in om te storten: **$10** is genoeg om te beginnen. Zet **automatic recharge**
   (automatisch bijvullen) **uit**. Bevestig.
7. Klik links op **API keys** (soms onder *Your profile* of *Organization*).
8. Klik op **+ Create new secret key**.
9. Naam: typ **Sofia**. Laat de rest zoals het is. Klik **Create secret key**.
10. Je ziet een lange code die begint met **sk-**. Klik op **Copy**.
    ⚠️ Je ziet deze code maar **één keer**!
11. Plak hem in je **Kladblok / Notities**. Zet erboven: *OpenAI-sleutel*.

✔️ **Je hebt nu:** code 1 én code 2 in je kladblok.

---

## Deel D — Python installeren

Python is het programma waarmee Sofia draait. Je hoeft er zelf niets mee te doen.

### Op Windows

1. Ga naar **https://www.python.org/downloads/**
2. Klik op de grote gele knop **Download Python 3.1x** (het getal maakt niet uit).
3. Open het gedownloade bestand (onderaan in je browser, of in de map **Downloads**).
4. ⚠️ Zet onderaan een vinkje bij **Add python.exe to PATH**.
5. Klik op **Install Now**.
6. Vraagt Windows *"Wilt u toestaan dat deze app wijzigingen aanbrengt?"* → klik **Ja**.
7. Wacht tot je **Setup was successful** ziet. Klik **Close**.

### Op een Mac

1. Ga naar **https://www.python.org/downloads/**
2. Klik op de grote gele knop **Download Python 3.1x**.
3. Open het gedownloade bestand (in **Downloads**).
4. Klik steeds op **Ga door** / **Continue**, dan **Akkoord** / **Agree**, dan **Installeer** / **Install**.
5. Typ je Mac-wachtwoord als daarom gevraagd wordt.
6. Wacht tot de installatie klaar is. Klik **Sluit** / **Close**.
   Er gaat misschien een map open met bestanden. Die kun je gewoon dichtdoen.

✔️ **Klaar.** Je hoeft Python niet zelf te openen.

---

## Deel E — Sofia downloaden

1. Klik op deze link (op je computer):
   **https://github.com/BTFBoer/SofiaBotasma/archive/refs/heads/claude/sofia-companion.zip**
2. Er wordt een **ZIP-bestand** gedownload. Dat is een ingepakte map.

### Uitpakken op Windows

3. Open de map **Downloads**.
4. Klik met de **rechtermuisknop** op het ZIP-bestand → **Alles uitpakken...** → **Uitpakken**.
5. Er opent een nieuwe map. Klik de mappen open **tot je een bestand ziet dat START-WINDOWS heet**.
   (Soms zit er een map in een map met dezelfde naam. Dat is normaal.)
6. Onthoud deze map. Dit is **de Sofia-map**.

### Uitpakken op een Mac

3. Open de map **Downloads** (in Finder).
4. Dubbelklik op het ZIP-bestand. Er verschijnt een map.
5. Open die map. Je ziet onder andere een bestand **start.sh**. Dit is **de Sofia-map**.

### Je privé-bestanden (aanbevolen)

In het gesprek met Claude heb je twee bestanden gekregen:
**persona.private.yaml** en **user_profile.private.yaml**. Daarin staat jouw persoonlijke afstemming.
Ze staan expres **niet** online.

7. Open op je computer **https://claude.ai** en ga naar het gesprek over Sofia.
8. Download beide bestanden (klik erop → downloaden).
9. Verplaats ze naar de map **persona** die **in de Sofia-map** zit.
10. Controleer de namen. Ze moeten **precies** zo heten — zonder *(1)* erachter:
    - `persona.private.yaml`
    - `user_profile.private.yaml`

> Sla je dit over? Dan werkt Sofia ook, maar zonder jouw persoonlijke afstemming.
> Je kunt ze later alsnog in de map zetten en Sofia opnieuw starten.

---

## Deel F — Sofia starten (de eerste keer)

Zorg dat je **kladblok met de twee codes** open staat, en **Telegram** ook.

### Op Windows

1. Ga naar **de Sofia-map**.
2. **Dubbelklik** op **START-WINDOWS**.
3. Zie je een blauw scherm *"Windows heeft uw pc beschermd"*?
   Klik op **Meer informatie** → klik op **Toch uitvoeren**.
4. Er opent een **zwart venster**. Wacht. De eerste keer worden onderdelen geïnstalleerd.
   Dat kan **een paar minuten** duren. Niets aanraken.

### Op een Mac

1. Druk op **Cmd + spatiebalk**, typ **Terminal** en druk op **Enter**. Er opent een venster.
2. Typ: **bash** gevolgd door **één spatie**. (Druk nog niet op Enter!)
3. Sleep het bestand **start.sh** uit de Sofia-map (in Finder) **naar het Terminal-venster** en laat los.
   Je ziet nu iets als: `bash /Users/jouwnaam/Downloads/.../start.sh`
4. Druk op **Enter**.
5. Vraagt je Mac om toegang tot een map (bijvoorbeeld *Downloads*)? Klik **OK** / **Sta toe**.
6. Wacht. De eerste keer worden onderdelen geïnstalleerd. Dat kan **een paar minuten** duren.

### De vragen beantwoorden (Windows en Mac hetzelfde)

Het venster stelt je nu **3 vragen**. Na elke vraag controleert het meteen of het klopt.

**Plakken in het venster:**
- Windows: klik met de **rechtermuisknop** in het zwarte venster (of druk **Ctrl+V**).
- Mac: druk **Cmd+V**.
- Druk daarna op **Enter**.

**Vraag 1 — `Token:`**
- Kopieer **code 1** (Telegram-token) uit je kladblok. Plak hem. Druk op **Enter**.
- ✔️ Je ziet: **✓ Gevonden: je bot heet @...**

**Vraag 2 — Wie ben jij?**
- Het venster zegt: *"Open Telegram, ga naar je bot"* en toont een link.
- Ga in Telegram naar je bot (zoek de gebruikersnaam uit Deel B, stap 7).
- Klik op **START**.
- Kijk terug naar het venster. Je ziet: *"Bericht ontvangen van (jouw naam) (@jouwgebruikersnaam). Ben jij dit?"*
- Typ **j** en druk op **Enter**.
- ✔️ Je ziet: **✓ Jouw Telegram-nummer (ID) is ...**

**Vraag 3 — `Sleutel:`**
- Kopieer **code 2** (OpenAI-sleutel, begint met *sk-*) uit je kladblok. Plak hem. Druk op **Enter**.
- Het venster test nu even welk model werkt. Dat kan **een halve minuut** duren.
- ✔️ Je ziet: **✓ OpenAI werkt.**

**Daarna:**
- ✔️ Je ziet: **✓ Instellingen opgeslagen** en **Klaar!**
- Sofia start vanzelf. Je ziet een regel met **Sofia is online**.

> 🗑️ Je kunt de twee codes nu uit je kladblok **verwijderen**. Ze zijn opgeslagen.

---

## Deel G — Met Sofia praten

1. Ga in Telegram naar je bot.
2. Typ **/start** en stuur het.
3. Je krijgt eerst een korte regel met ⚙️ (dat is uitleg, niet Sofia).
4. Daarna stuurt **Sofia** je zelf een eerste berichtje.
5. Praat gewoon met haar, zoals je met iemand appt.

**Handige commando's** (typ ze in de chat; Sofia ziet ze niet):

| Typ | Wat gebeurt er |
|---|---|
| /memory | Laat zien wat ze over je onthouden heeft |
| /forget *woord* | Iets laten vergeten, bijvoorbeeld: /forget werk |
| /proactive on | Sofia mag af en toe zélf een bericht sturen (staat standaard uit) |
| /proactive off | Weer uit |
| /privacy | Waar je gegevens staan |
| /export | Alles downloaden als bestand |
| /reset | Alles wissen en opnieuw beginnen (vraagt eerst bevestiging) |
| /about | Wat Sofia is |

**Testen of ze onthoudt:**
- Vertel haar iets wat over een tijdje gebeurt, bijvoorbeeld een plan met een datum.
- Typ daarna **/memory**. Je ziet het in de lijst staan.

---

## Deel H — De volgende keren

- **Zolang het zwarte venster (Windows) of het Terminal-venster (Mac) open is, is Sofia online.**
- Venster dicht = Sofia offline. Je computer uit = Sofia offline.
- Zolang Sofia draait, gaat je computer niet vanzelf slapen. (Laptop dichtklappen kan hem nog wel laten slapen.)
- Berichten die je stuurt terwijl Sofia offline is, beantwoordt ze zodra je haar weer start
  (Telegram bewaart ze maximaal 24 uur).

**Sofia weer starten:**
- **Windows:** dubbelklik op **START-WINDOWS** in de Sofia-map.
- **Mac:** open **Terminal**, typ **bash** + spatie, sleep **start.sh** erin, druk **Enter**.

**Sofia stoppen:**
- Sluit het venster met het kruisje. Of druk **Ctrl+C** in het venster.
- Vraagt Windows *"Batchtaak beëindigen (J/N)?"* → typ **J** en druk **Enter**.

> 💡 Start Sofia **maar op één computer tegelijk**. Twee keer tegelijk werkt niet.

---

## Lukt het niet?

| Wat zie je? | Wat moet je doen? |
|---|---|
| *"Python 3.12 of nieuwer is niet gevonden"* | Doe **Deel D** opnieuw. Start daarna je computer opnieuw op en probeer het nog eens. |
| *"Dat lijkt geen token"* | Kopieer code 1 opnieuw, **helemaal**, uit BotFather. |
| *"Telegram kent dit token niet"* | Typ in BotFather **/token**, kies je bot, en gebruik de nieuwe code. |
| *"Je OpenAI-account heeft geen tegoed"* | Doe **Deel C, stap 3 t/m 6**. Wacht 5 minuten. Probeer opnieuw. |
| *"OpenAI kent deze sleutel niet"* | Maak een nieuwe sleutel (**Deel C, stap 7 t/m 11**). |
| *"Geen enkel geschikt model werkte"* | Controleer je tegoed. Kijk op platform.openai.com bij **Settings → Organization** of er een knop **Verify** staat; doe die verificatie. |
| Sofia antwoordt steeds *"wait, something glitched on my side"* | Stop Sofia. Doe daarna **Instellingen opnieuw doen** (hieronder). |
| Sofia antwoordt helemaal niet | Staat het venster nog open? Staat er rode tekst in? Maak een **screenshot** en vraag om hulp. |
| Je wilt alles opnieuw instellen | Doe **Instellingen opnieuw doen** (hieronder). |

### Instellingen opnieuw doen

Hiermee krijg je de 3 vragen opnieuw (bijvoorbeeld met een nieuwe code).
Je gesprekken en Sofia's geheugen blijven gewoon bewaard.

- **Windows:** stop Sofia (venster dicht). Dubbelklik op **INSTELLEN-WINDOWS** in de Sofia-map.
  Bij *"Er zijn al instellingen. Opnieuw instellen?"* typ je **j** en **Enter**.
- **Mac:** stop Sofia (venster dicht). Open **Terminal**, typ **bash** + spatie, sleep **start.sh** erin,
  typ dan nog **een spatie en --setup** erachter, druk **Enter**. Bij de vraag typ je **j** en **Enter**.

**Hulp vragen:** maak een screenshot van het venster en stuur die naar Claude.
⚠️ Let op dat je token en sleutel **niet** op de screenshot staan.

---

## Als je code 1 of code 2 per ongeluk gedeeld hebt

- **Telegram-token:** typ in BotFather **/revoke**, kies je bot. Je krijgt een nieuw token.
  Doe daarna **Instellingen opnieuw doen** en vul het nieuwe token in.
- **OpenAI-sleutel:** ga naar platform.openai.com → **API keys** → klik op het prullenbakje bij de sleutel.
  Maak een nieuwe en doe **Instellingen opnieuw doen**.

---

## Later: Sofia 24 uur per dag online

Wil je dat Sofia ook online is als je computer uit staat? Dan moet ze op een kleine server
"in de cloud" draaien (ongeveer €5 per maand). Dat is een volgende stap. Vraag het als je zover bent.
