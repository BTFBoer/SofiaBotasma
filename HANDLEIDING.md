# Sofia installeren — stap voor stap

Deze handleiding is voor iemand die **nog nooit** iets met programmeren heeft gedaan.

- Doe de stappen **in volgorde**. Sla niets over.
- Na veel stappen staat **✔️ Je ziet:**. Zo weet je dat het goed ging.
- Duurt iets lang? Dat staat er dan bij. Niets aanraken, gewoon wachten.

⏱️ Totale tijd: ongeveer **een uur**.

---

## Wat heb je nodig?

- Een **computer** met **Windows** of een **Mac**. Een tablet of telefoon werkt niet.
- **Telegram** op je telefoon.
- Een **betaalkaart** (creditcard of debitcard). Daarmee koop je vooraf tegoed bij OpenAI, bijvoorbeeld $10.
- Een **notitie** om twee codes even in te bewaren.
  - Windows: het programma **Kladblok**.
  - Mac: het programma **Notities**.
  - In deze handleiding heet dat steeds **je notitie**.

---

## Woorden die je tegenkomt

| Woord | Betekenis |
|---|---|
| **Enter** | De grote toets rechts op je toetsenbord, met een pijltje ↵. |
| **Kopiëren** | Je computer onthoudt een stukje tekst. Windows: **Ctrl+C**. Mac: **Cmd+C**. |
| **Plakken** | Die tekst ergens neerzetten. Windows: **Ctrl+V**. Mac: **Cmd+V**. |
| **Ga naar** een website | Klik bovenin je internetprogramma (Chrome, Edge of Safari) op de adresbalk. Typ het adres. Druk op **Enter**. Je kunt in deze handleiding ook gewoon op de blauwe links klikken. |
| **Map** | Een plek op je computer waar bestanden in zitten. Je ziet een geel (Windows) of blauw (Mac) mapje. |
| **Venster** | Een rechthoek op je scherm waarin een programma draait. |
| **ZIP-bestand** | Een ingepakte map. Je pakt hem eerst uit. Op Windows heeft het pictogram een ritssluiting. |
| **Terminal** | Alleen op een Mac: een programma waarin je tekst typt in plaats van klikt. |
| **Bot** | Een automatisch Telegram-account. Sofia wordt zo'n bot. |
| **Telegram-token** | Een lange geheime code van Telegram. Daarmee gebruikt Sofia jouw bot. |
| **OpenAI-sleutel** | Een lange geheime code van OpenAI. Daarmee kan Sofia nadenken en antwoorden. |
| **Screenshot** | Een foto van je scherm. Windows: druk tegelijk op **Windows-toets + Shift + S**. Mac: druk tegelijk op **Cmd + Shift + 4** en sleep over het venster. |

---

## Veiligheid

> 🔒 Je **Telegram-token** en je **OpenAI-sleutel** zijn net als wachtwoorden.
> Geef ze aan **niemand**. Ook niet in een chat, ook niet aan Sofia, ook niet aan Claude.
>
> 📱 Je telefoonnummer vul je alleen in bij **Telegram** (Deel A) en, als die erom vraagt, bij **OpenAI** (Deel C).

---

## Overzicht

| Deel | Wat | Tijd |
|---|---|---|
| A | Telegram op je computer openen | 5 min |
| B | Je bot maken → je **Telegram-token** | 10 min |
| C | Een OpenAI-account met tegoed → je **OpenAI-sleutel** | 15 min |
| D | Python 3.14 installeren | 5 min |
| E | Sofia downloaden | 5 min |
| F | Sofia de eerste keer starten en 3 vragen beantwoorden | 15 min |
| G | Met Sofia praten | — |
| H | De volgende keren | — |

---

## Deel A — Telegram op je computer

Je moet straks een lange code kopiëren. Dat gaat het makkelijkst als Telegram ook op je computer open staat.

1. Ga op je computer naar **https://web.telegram.org**
2. Klik op **Log in by phone Number** (inloggen met telefoonnummer).
3. Kies als land **Netherlands (+31)**. Meestal staat dat er al.
4. Typ je telefoonnummer **zonder de eerste 0**. Dus niet *06 …* maar *6 …*. Klik op **Next**.
5. Telegram stuurt een code naar je **telefoon**, als bericht in de Telegram-app. Typ die code over op de computer.
6. Vraagt Telegram om een **wachtwoord** (*Password*)? Dat is je eigen Telegram-wachtwoord, als je dat ooit hebt ingesteld. Typ het in.

✔️ **Je ziet:** je eigen Telegram-gesprekken op je computerscherm.

---

## Deel B — Je bot maken (je Telegram-token)

1. Klik in Telegram (op je computer) linksboven op het **zoekvak**.
2. Typ: **BotFather**
3. Klik op **BotFather** met het **blauwe vinkje** ✔️. Niet op een andere: er zijn nepversies.
4. Klik onderaan op **START**.
5. Typ: **/newbot** en druk op **Enter**.
6. BotFather antwoordt in het Engels: *"Alright, a new bot. How are we going to call it?"*
   Dat betekent: hoe heet je bot? Typ: **Sofia** en druk op **Enter**.
7. BotFather vraagt nu een gebruikersnaam (*"Now let's choose a username for your bot"*).
   - De naam moet eindigen op **bot**.
   - Gebruik alleen letters zonder accent, cijfers en het **lage streepje _**.
     Het lage streepje typ je zo: houd **Shift** ingedrukt en druk op de toets **-**.
   - Een gewoon streepje **-** of een spatie mag **niet**.
   - Bijvoorbeeld: **sofia_bram_2026_bot**. Druk op **Enter**.
   - Zegt BotFather *"Sorry, this username is already taken"*? Die naam is al van iemand anders. Verander de cijfers en probeer opnieuw.
   - Zegt BotFather *"Sorry, this username is invalid"*? Er staat een teken in dat niet mag. Probeer opnieuw.
8. BotFather stuurt een bericht dat begint met **Done! Congratulations**.
   Daarin staat een lange code na *"Use this token to access the HTTP API:"*.
   Die ziet eruit zoals: `7123456789:AAH4kPz...` (cijfers, een dubbele punt, en heel veel letters).
9. Open je notitie:
   - Windows: klik op **Start**, typ **Kladblok** en druk op **Enter**.
   - Mac: druk op **Cmd + spatiebalk**, typ **Notities** en druk op **Enter**. Klik op het **pennetje** voor een nieuwe notitie.
10. Typ in je notitie: **Telegram-token:** en druk op **Enter**.
11. Ga terug naar Telegram. Klik **één keer** op de lange code. Je ziet heel even dat hij gekopieerd is (*copied*).
12. Ga terug naar je notitie. Plak: **Ctrl+V** (Mac: **Cmd+V**).
13. Typ ook de gebruikersnaam van je bot in je notitie, bijvoorbeeld *sofia_bram_2026_bot*.

✔️ **Je ziet:** in je notitie staat je Telegram-token en de naam van je bot.

**Extra veiligheid (1 minuut):**

14. Ga terug naar BotFather. Typ: **/setjoingroups** en druk op **Enter**.
15. Klik op de naam van je nieuwe bot.
16. Klik op **Disable** (uitzetten).

✔️ **Je ziet:** *"Success! The new status is: DISABLED."* Nu kan niemand je bot aan een groep toevoegen.

---

## Deel C — OpenAI (je OpenAI-sleutel)

> ⚠️ Dit is **niet** hetzelfde als ChatGPT. Ook als je ChatGPT Plus betaalt, moet je dit apart doen.
> Je koopt hier vooraf tegoed. Sofia gebruikt per bericht een heel klein beetje daarvan.

1. Ga naar **https://platform.openai.com**
2. Klik op **Sign up** (aanmelden). Heb je al een account bij OpenAI of ChatGPT? Klik dan op **Log in**. Dat account mag je gebruiken.
3. Krijg je welkomstschermen? Doe dan dit:
   - **Welcome to OpenAI Platform**: typ bij *Organization name* je voornaam. Kies bij *What best describes you?* wat het beste past. Klik **Create organization**.
   - **Invite your team**: klik **I'll invite my team later**.
   - **Make your first API call**: klik **I'll do this later**. (De sleutel maak je straks.)
4. Ga naar **https://platform.openai.com/settings/organization/billing/overview**
   (Dit is de pagina om te betalen. Of: klik rechtsboven op het tandwiel ⚙️ **Settings**, en dan links op **Billing**.)
5. Klik op **Add payment details**.
6. Kies **Individual** (privépersoon).
7. Vul je kaartgegevens in. Klik op de knop om verder te gaan.
8. Je ziet nu een scherm om tegoed te kopen. Laat het bedrag op **$10** staan. (Minimaal $5 mag ook.)
9. ⚠️ Op dat scherm staat een schakelaar **Use auto-reload** (automatisch bijkopen). Die staat **AAN**.
   Klik erop, zodat hij **UIT** staat (grijs). Anders schrijft OpenAI later vanzelf opnieuw geld af.
10. Klik op de knop om te betalen en bevestig.

✔️ **Je ziet:** bij **Credit balance** staat **$10.00** (of het bedrag dat je koos).

11. Ga naar **https://platform.openai.com/api-keys**
12. Klik op **+ Create new secret key**.
13. Typ bij de naam: **Sofia**. Laat de rest zoals het is. Klik op **Create secret key**.
14. Vraagt OpenAI om je telefoonnummer (*Verify your phone number*)? Dat is normaal bij je eerste sleutel.
    Kies **Netherlands (+31)**. Typ je nummer **zonder de eerste 0**. Kies **SMS** (of WhatsApp).
    Typ de code die je krijgt over. Klik op verifiëren.
15. Je ziet nu een lange code die begint met **sk-**. ⚠️ Je ziet deze code maar **één keer**!
16. Typ in je notitie: **OpenAI-sleutel:** en druk op **Enter**.
17. Ga terug naar OpenAI. Klik op **Copy** naast de code.
18. Ga terug naar je notitie. Plak: **Ctrl+V** (Mac: **Cmd+V**).
19. Klik in OpenAI op **Done**.

✔️ **Je ziet:** in je notitie staan nu je Telegram-token én je OpenAI-sleutel.

---

## Deel D — Python 3.14 installeren

Python is het programma waarmee Sofia draait. Je hoeft er zelf niets mee te doen.

> ⚠️ Gebruik **precies de link hieronder**. Klik op de website van Python **niet** op de grote gele knop.
> Die geeft een nieuwere versie (3.15) of een ander programma, en daarmee werkt Sofia nog **niet**.

### Op Windows

1. Klik op deze link: **https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.exe**
   Er wordt een bestand gedownload: *python-3.14.7-amd64*.
2. Open dat bestand:
   - Klik rechtsboven in je internetprogramma op het **pijltje ⬇** en klik op het bestand.
   - Of: open de **Verkenner** (het gele mapje onderaan je scherm), klik links op **Downloads** en dubbelklik op het bestand.
3. Er opent een venster *Install Python 3.14.7*. ⚠️ Zet **onderaan** een vinkje bij **Add python.exe to PATH**.
4. Klik op **Install Now**.
5. Vraagt Windows *"Wilt u toestaan dat deze app wijzigingen aanbrengt op uw apparaat?"* → klik **Ja**.
6. Wacht tot je **Setup was successful** ziet. Klik op **Close**.

### Op een Mac

1. Klik op deze link: **https://www.python.org/ftp/python/3.14.7/python-3.14.7-macos11.pkg**
   Vraagt Safari *"Wil je downloads op www.python.org toestaan?"* → klik **Sta toe**.
2. Open **Finder** (het blauw-witte gezichtje onderaan je scherm). Klik links op **Downloads**.
   Dubbelklik op **python-3.14.7-macos11.pkg**.
3. Klik steeds op **Ga door**, dan **Akkoord**, dan **Installeer**.
4. Typ je Mac-wachtwoord als daarom gevraagd wordt.
5. Wacht tot de installatie klaar is. Klik **Sluit**.
   Vraagt hij of het installatiebestand naar de prullenmand mag? Klik **Verplaats naar prullenmand**.
   Er gaat misschien een map open met bestanden. Die mag je gewoon dichtdoen.

✔️ **Klaar.** Je hoeft Python niet zelf te openen.

---

## Deel E — Sofia downloaden

### Stap 1: Sofia zelf

1. Klik op deze link: **https://github.com/BTFBoer/SofiaBotasma/archive/refs/heads/claude/sofia-companion.zip**
   Er wordt een **ZIP-bestand** gedownload. Download het maar **één keer**.

**Op Windows:**

2. Open de **Verkenner** (het gele mapje onderaan je scherm). Klik links op **Downloads**.
   ✔️ Je ziet een bestand **SofiaBotasma-claude-sofia-companion** met een **ritssluiting** op het pictogram.
3. Klik er met de **rechtermuisknop** op. Klik op **Alles uitpakken...** en daarna op **Uitpakken**.
4. Er opent een nieuwe map. Daarin zit nóg een map met dezelfde naam. Dubbelklik op die map.
   ✔️ Je ziet onder andere een bestand **START-WINDOWS** en een map **persona**. Dit is **de Sofia-map**.
5. Gooi het ZIP-bestand weg, zodat je het niet verwart met de map: ga naar **Downloads**, klik met de **rechtermuisknop** op het pictogram **met de ritssluiting** en klik op het **prullenbakje**.

**Op een Mac:**

2. Open **Finder**. Klik links op **Downloads**.
3. Kijk wat je ziet:
   - Een **map** met de naam **SofiaBotasma-claude-sofia-companion**? Dan heeft je Mac hem al uitgepakt. Ga naar stap 4.
   - Een **ZIP-bestand** met die naam? Dubbelklik erop. Er verschijnt een map.
4. Dubbelklik op de map **SofiaBotasma-claude-sofia-companion**.
   ✔️ Je ziet onder andere een bestand **start.sh** en een map **persona**. Dit is **de Sofia-map**.

> 📁 **De Sofia-map vind je later zo terug:**
> Windows: **Verkenner → Downloads → SofiaBotasma-claude-sofia-companion → SofiaBotasma-claude-sofia-companion**
> Mac: **Finder → Downloads → SofiaBotasma-claude-sofia-companion**
>
> ⚠️ **Gooi de Sofia-map nooit weg.** Daarin staat ook Sofia's geheugen.

### Stap 2: je privé-bestanden (aanbevolen)

In het gesprek met Claude heb je twee bestanden gekregen: **persona.private.yaml** en **user_profile.private.yaml**.
Daarin staat jouw persoonlijke afstemming. Ze staan expres **niet** online.

6. Ga op je computer naar **https://claude.ai** en open het gesprek over Sofia.
7. Klik op het eerste bestand en kies **downloaden**. Doe hetzelfde met het tweede bestand.
8. Laat ze gewoon in **Downloads** staan. Sofia zet ze bij het starten zelf op de goede plek,
   ook als er bijvoorbeeld *(1)* in de naam staat.

> Sla je dit over? Dan werkt Sofia ook, maar zonder jouw persoonlijke afstemming.
> Je kunt ze later alsnog downloaden en Sofia opnieuw starten.

---

## Deel F — Sofia de eerste keer starten

Zorg dat **je notitie** open staat, en **Telegram** ook.

### Op Windows

1. Ga naar **de Sofia-map** (zie Deel E).
2. **Dubbelklik** op **START-WINDOWS**.
3. Zie je een blauw scherm *"Windows heeft uw pc beschermd"*?
   Klik op **Meer informatie** en daarna op **Toch uitvoeren**. (Dit gebeurt maar één keer.)
   Zie je *"Bestand openen - beveiligingswaarschuwing"*? Klik op **Uitvoeren**.
4. Er opent een **zwart venster**.
   ✔️ Je ziet: *Onderdelen installeren. De eerste keer kan dit 5 minuten duren.*
5. Wacht. Er gebeurt dan een tijd niets op het scherm. Dat is normaal.
6. ⚠️ **Klik niet met de linkermuisknop in het zwarte venster.** Zo'n klik kan het venster op pauze zetten.
   Heb je toch geklikt en staat alles stil? Druk één keer op **Esc** (linksboven op je toetsenbord).

### Op een Mac

1. Druk op **Cmd + spatiebalk**. Typ **Terminal** en druk op **Enter**. Er opent een venster.
2. Typ: **bash** en daarna **één spatie**. Druk nog **niet** op Enter.
3. Zet het **Terminal-venster** en het **Finder-venster met de Sofia-map** naast elkaar, zodat je ze allebei ziet.
   (Sleep een venster aan de bovenrand opzij.)
4. Sleep het bestand **start.sh** uit de Sofia-map naar het Terminal-venster en laat los.
   ✔️ Je ziet nu iets als: `bash /Users/jouwnaam/Downloads/SofiaBotasma-claude-sofia-companion/start.sh`
5. Klik één keer in het Terminal-venster en druk op **Enter**.
6. Zie je de vraag *"Terminal" wil toegang tot bestanden in je map Downloads*?
   Klik op **Sta toe** (soms heet de knop **OK**). ⚠️ Klik **niet** op *Sta niet toe*.
7. ✔️ Je ziet: *Onderdelen installeren. De eerste keer kan dit 5 minuten duren.*
   Wacht. Er gebeurt dan een tijd niets op het scherm. Dat is normaal.

### De 3 vragen (Windows en Mac hetzelfde)

✔️ Je ziet eerst: **Sofia — eerste keer instellen** en daaronder **Ik stel je 3 vragen.**

**Plakken in het venster:**
- Windows: klik met de **rechter**muisknop in het zwarte venster. Dan wordt het geplakt.
- Mac: druk op **Cmd+V**.
- Druk daarna op **Enter**.

**Vraag 1 van 3 — Je Telegram-token** (onderaan staat: `Token:`)

1. Ga naar je notitie. Kopieer je Telegram-token.
   (Zet de muis vlak vóór de eerste cijfers. Houd de linkermuisknop ingedrukt. Sleep tot het einde van de code. Druk **Ctrl+C**, Mac: **Cmd+C**.)
2. Ga terug naar het venster. Plak. Druk op **Enter**.
3. Het venster wordt even leeg. Dat is goed: zo is je code niet meer te zien.

✔️ Je ziet: **✓ Gevonden: je bot heet @...**

**Vraag 2 van 3 — Wie ben jij?**

1. Het venster schrijft: *Zoek in Telegram je bot: @...*
2. Ga naar Telegram. Typ in het zoekvak de naam van je bot (die staat in je notitie). Klik op je bot.
3. Klik onderaan op **START**. Zie je geen START-knop? Typ dan **hallo** en druk op **Enter**.
4. In Telegram gebeurt nu nog niets. Dat is normaal.
5. Kijk terug naar het venster. Je ziet: *Bericht ontvangen van (jouw naam) (@jouw Telegram-naam).*
   En daaronder: *Ben jij dit? (typ j of n, daarna Enter):*
6. Typ **j** en druk op **Enter**.

✔️ Je ziet: **✓ Jouw Telegram-nummer (ID) is ...**

**Vraag 3 van 3 — Je OpenAI-sleutel** (onderaan staat: `Sleutel:`)

1. Ga naar je notitie. Kopieer je OpenAI-sleutel (begint met **sk-**), net zoals bij vraag 1.
2. Ga terug naar het venster. Plak. Druk op **Enter**.
3. Het venster wordt weer even leeg. Dat is goed.
4. Het venster test nu welke **AI-versie** (een *model*) jouw account mag gebruiken. Dat duurt meestal een halve minuut.
5. Misschien zie je eerst regels zoals *- gpt-...: werkt niet met jouw account. Geen probleem, ik probeer de volgende...*
   Dat is normaal.

✔️ Je ziet: **✓ Sofia gebruikt: gpt-...** en daarna **✓ OpenAI werkt.**

**Daarna gaat het vanzelf:**

- ✔️ Je ziet: **✓ Instellingen opgeslagen** en **✓ Je privé-bestanden staan op hun plek.**
  - Zegt het venster dat de privé-bestanden ontbreken? Dan opent het de map **persona**. Zet de twee bestanden daarin, of druk gewoon op **Enter** om zonder verder te gaan.
- ✔️ Je ziet: **Klaar! Sofia start nu.** en **LAAT DIT VENSTER OPEN STAAN.**
- Daarna komen een paar regels in het **Engels**, met de datum en tijd ervoor. Dat is normaal.
- In een van die regels staat **Sofia is online**. Dan werkt alles.
- Daarna doet het venster niets meer. Dat is goed: Sofia wacht op jouw bericht. **Laat het venster open.**

> 🗑️ Sofia werkt nu. Je mag je notitie met de twee codes weggooien.
> Windows: klik in Kladblok, druk **Ctrl+A** en dan **Delete**, sluit Kladblok en kies **Niet opslaan**.
> Mac: klik met de rechtermuisknop op de notitie en kies **Verwijder**.
> Heb je ze later nog eens nodig? Dan maak je gewoon nieuwe (zie *Een code per ongeluk gedeeld*).

---

## Deel G — Met Sofia praten

1. Ga in Telegram naar je bot.
2. Typ **/start** en druk op **Enter**.
3. Je krijgt eerst een korte regel met ⚙️ in het **Engels**. Dat is uitleg, niet Sofia.
4. Wacht even. Bovenin staat misschien *typing...* (aan het typen).
   Daarna stuurt **Sofia** je zelf een eerste berichtje.
   Komt er na een minuut niets? Stuur dan zelf: **hoi**.
5. Praat gewoon met haar, zoals je met iemand appt.

**Handige commando's.** Typ ze in de chat. Sofia ziet ze niet. De antwoorden zijn in het Engels.

| Typ | Wat gebeurt er |
|---|---|
| /memory | Laat zien wat ze over je onthouden heeft |
| /forget *woord* | Iets laten vergeten. Bijvoorbeeld: /forget werk |
| /proactive on | Sofia mag af en toe zélf een bericht sturen. Dat staat eerst **uit**. |
| /proactive off | Weer uit |
| /privacy | Waar je gegevens staan |
| /export | Alles downloaden als bestand |
| /reset | Alles wissen en opnieuw beginnen. Vraagt eerst of je het zeker weet. |
| /about | Wat Sofia is |

**Testen of ze onthoudt:**
1. Vertel haar iets wat over een tijdje gebeurt. Bijvoorbeeld een plan met een datum.
2. Typ daarna **/memory**. ✔️ Je ziet het in de lijst staan.

---

## Deel H — De volgende keren

**Hoe het werkt:**
- Zolang het **zwarte venster** (Windows) of het **Terminal-venster** (Mac) open is, is Sofia **online**.
- Venster dicht = Sofia **offline**. Computer uit = Sofia **offline**.
- Zolang Sofia draait, gaat je computer niet vanzelf slapen. Laptop dichtklappen kan hem nog wel laten slapen.
- Stuur je een bericht terwijl Sofia offline is? Dan antwoordt ze zodra je haar weer start.
  Telegram bewaart zulke berichten maximaal 24 uur.

**Sofia starten:**
- **Windows:** dubbelklik op **Sofia** op je **bureaublad**.
  (Die snelkoppeling is de eerste keer vanzelf gemaakt. Staat hij er niet? Dubbelklik dan op **START-WINDOWS** in de Sofia-map.)
- **Mac:** open de Sofia-map en dubbelklik op **Sofia starten**.
  (Dat bestand is de eerste keer vanzelf gemaakt. Werkt het niet? Doe dan Deel F, Mac stap 1 t/m 5.)

> 💡 Start Sofia maar **één keer tegelijk**: niet op twee computers en niet in twee vensters.
> Kijk eerst onderaan in je scherm (taakbalk of Dock) of er al een venster van Sofia open is.

**Sofia stoppen:**
- **Windows:** klik rechtsboven in het zwarte venster op het **kruisje ✕**.
- **Mac:** klik linksboven in het Terminal-venster op het **rode rondje**.
  Vraagt je Mac of je de processen wilt beëindigen? Klik op **Beëindig**.

---

## Lukt het niet?

**Stopt het met een regel die begint met STOP?**
Lees die regel. Doe wat er staat. Sluit het venster. Start Sofia daarna opnieuw (Deel H). Je krijgt de vragen dan opnieuw.

| Wat zie je? | Wat moet je doen? |
|---|---|
| *Python 3.14 is niet gevonden* | Doe **Deel D** opnieuw, met de link uit Deel D. Start Sofia daarna opnieuw. |
| Veel Engelse regels met *error*, *Rust* of *Cargo*, en daarna *Er ging iets mis* | Je hebt waarschijnlijk Python 3.15. Doe **Deel D** (3.14). Start Sofia opnieuw; de rest gaat vanzelf goed. |
| *Er ging iets mis. Controleer of je internet werkt.* | Controleer je internet. Sluit het venster. Start Sofia opnieuw. |
| *Je hebt START-WINDOWS geopend vanuit het ZIP-bestand* | Doe **Deel E, stap 3 en 4** (uitpakken). Start daarna START-WINDOWS uit de uitgepakte map. |
| *Dat lijkt geen Telegram-token* | Kopieer je Telegram-token opnieuw, **helemaal**, uit BotFather. |
| *Telegram kent dit token niet* | Typ in BotFather **/token**, kies je bot, en gebruik het nieuwe token. |
| *Ik heb 10 minuten geen bericht ontvangen* | Start Sofia opnieuw. Bij vraag 2: klik op **START** bij je bot, of typ **hallo**. |
| *Sofia draait nog in een ander venster* | Sluit het andere venster van Sofia. Start daarna opnieuw. |
| *Je OpenAI-account heeft geen tegoed* | Doe **Deel C, stap 4 t/m 10**. Wacht 5 minuten. Start Sofia opnieuw. |
| *OpenAI kent deze sleutel niet* | Kopieer de sleutel opnieuw, helemaal. Lukt het niet? Maak een nieuwe (**Deel C, stap 11 t/m 18**). |
| *Geen enkele AI-versie werkte* | Controleer je tegoed. Ga naar **https://platform.openai.com/settings/organization/general**. Staat daar **Verify Organization**? Klik erop, leg je **paspoort, ID-kaart of rijbewijs** klaar en volg de stappen. Doe daarna **Instellingen opnieuw doen**. |
| *STOP: Telegram accepteert het token van je bot niet (meer)* | Doe **Instellingen opnieuw doen**. Typ in BotFather **/token** voor een nieuw token. |
| *STOP: Ik kan Telegram niet bereiken* | Controleer je internet. Start Sofia opnieuw. |
| Sofia antwoordt steeds *"wait, something glitched on my side"* | Stop Sofia. Doe **Instellingen opnieuw doen**. Je mag je codes hetzelfde laten. |
| Sofia antwoordt helemaal niet | Is het venster nog open? Staat er bovenin *Selecteren*? Druk dan op **Esc**. Staat er een regel met **ERROR**? Maak een screenshot en vraag om hulp. |
| (Mac) *Operation not permitted* | Open **Systeeminstellingen → Privacy en beveiliging → Bestanden en mappen → Terminal**. Zet de schakelaar bij **Downloads** aan. Sluit Terminal met **Cmd+Q** en begin opnieuw bij **Deel F**. |
| (Mac) Een Apple-venster over *ontwikkelaarstools* | Klik **Niet nu** of **Annuleer** (niet *Installeer*). Doe daarna **Deel D**. |
| (Mac) *Sofia starten* kan niet worden geopend | Start Sofia via Terminal: **Deel F, Mac stap 1 t/m 5**. |

**Hulp vragen:** maak een screenshot van het venster en stuur die naar Claude.
Je codes zijn niet te zien: het venster verbergt ze zelf. Kijk toch even of er geen lange code met **sk-** of een **:** erin op staat.

---

## Instellingen opnieuw doen

Hiermee krijg je de vragen opnieuw. Bijvoorbeeld voor een nieuwe code, of als Sofia steeds "glitched" zegt.
Je gesprekken en Sofia's geheugen blijven gewoon bewaard.

1. Stop Sofia (zie Deel H).
2. Start de instellingen:
   - **Windows:** open de Sofia-map en dubbelklik op **INSTELLEN-WINDOWS**.
     (Komt het blauwe scherm? **Meer informatie → Toch uitvoeren**.)
   - **Mac:** open de Sofia-map en dubbelklik op **Sofia opnieuw instellen**.
     (Werkt dat niet? Doe Deel F, Mac stap 1 t/m 4, typ dan nog een spatie en **--setup** erachter, en druk op **Enter**.)
3. Bij *Er zijn al instellingen. Opnieuw instellen?* typ je **j** en **Enter**.
4. Bij *Je Telegram-instellingen hetzelfde laten?*:
   typ **j** als je Telegram-token niet veranderd is. Typ **n** als je een nieuw token hebt.
5. Bij *Je OpenAI-sleutel hetzelfde laten?*:
   typ **j** als je sleutel niet veranderd is. Typ **n** als je een nieuwe sleutel hebt.
6. Daarna test het venster alles opnieuw en start Sofia vanzelf.

---

## Een code per ongeluk gedeeld?

- **Telegram-token:** typ in BotFather **/revoke** en kies je bot. Daarna **/token**: je krijgt een nieuw token.
  Doe **Instellingen opnieuw doen**. Typ bij *Je Telegram-instellingen hetzelfde laten?* een **n**.
- **OpenAI-sleutel:** ga naar **https://platform.openai.com/api-keys**. Klik op het **prullenbakje** bij de sleutel.
  Maak een nieuwe (**Deel C, stap 12 t/m 18**). Doe **Instellingen opnieuw doen**. Typ bij *Je OpenAI-sleutel hetzelfde laten?* een **n**.

---

## Later: Sofia 24 uur per dag online

Wil je dat Sofia ook online is als je computer uit staat? Dan moet ze op een kleine server "in de cloud" draaien
(ongeveer €5 per maand). Dat is een volgende stap. Vraag het als je zover bent.
