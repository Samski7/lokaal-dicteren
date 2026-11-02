# Lokaal dicteren

**Dicteren in het Nederlands (en Vlaams) op Windows, volledig lokaal.** Druk een sneltoets,
spreek, en de tekst verschijnt bij je cursor: in Word, Outlook, je browser of elk ander
programma. Geen abonnement, geen cloud: je audio verlaat je pc nooit.

- **Spraakherkenning** met [Whisper](https://github.com/openai/whisper) large-v3-turbo via
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper), op je NVIDIA-GPU als je die hebt,
  anders op de CPU.
- **Live**: bij elke korte pauze verschijnt dat stuk tekst al terwijl je verder spreekt.
- **Opschonen**: "euh", "ehm" verdwijnen; optioneel maakt een lokaal taalmodel
  ([gemma4](https://ollama.com/library/gemma4) via [Ollama](https://ollama.com)) er nette zinnen van.
- **Extra's**: een web-app (opnemen of uploaden, ook vanaf je gsm), een CLI voor audiobestanden,
  en `eval.py` om spraakmodellen objectief te vergelijken.

Enkel bij de eerste start worden de modellen eenmalig gedownload (~1,6 GB voor Whisper,
~3 GB voor gemma4); daarna werkt alles offline.

## Snel starten

Nodig: Windows 10/11, [Python 3.11+](https://www.python.org/downloads/), en optioneel
[Ollama](https://ollama.com) voor nette zinnen.

1. Download deze repo (groene knop **Code → Download ZIP**, of `git clone`) en pak hem uit.
2. Dubbelklik **`installeer.bat`** (eenmalig, enkele minuten). Dat installeert alles, ook de
   GPU-ondersteuning als je een NVIDIA-kaart hebt, en haalt het taalmodel op als Ollama er is.
3. Dubbelklik **`dicteer.bat`**, wacht op *Klaar*, klik in een tekstvak en druk
   **Ctrl + Shift + Spatie**.

Handmatig installeren kan ook:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt   # enkel met NVIDIA-GPU
ollama pull gemma4:e2b-it-qat                                       # enkel voor opschonen
```

ffmpeg en een aparte CUDA-installatie zijn niet nodig.

## Dicteren (tekst bij je cursor)

Dubbelklik op `dicteer.bat`. Na een paar seconden staat er *Klaar*.

1. Zet je cursor waar de tekst moet komen (Word, Outlook, browser, ...).
2. Druk **Ctrl + Shift + Spatie**: hoge piep = opnemen.
3. Spreek in en druk opnieuw **Ctrl + Shift + Spatie**: lage piep = stoppen.
4. **Live**: telkens je even pauzeert (0,7 s), wordt dat stuk al omgezet en bij je cursor
   geplakt terwijl je verder spreekt. Het laatste stuk volgt na de stop-piep.
5. Je vorige klembordtekst wordt na het plakken teruggezet. (Staat Windows-klembordgeschiedenis,
   Win+V, aan, dan zie je de gedicteerde tekst daar ook.)

Laat het venster open (minimaliseren mag). Audio komt nooit op schijf.

**Opschonen**: "euh", "ehm" ... worden altijd weggefilterd. Met `opschonen.llm: true` maakt
gemma4 er ook nette zinnen van en houdt het bij een verbetering ("morgen, nee overmorgen")
enkel de verbeterde versie. Dat kost ~3,5 s extra per stuk; zet het op `false` als je snelheid
belangrijker vindt. Als Ollama niet draait, gaat het gewoon verder zonder.

**Veiligheid**: de tekst wordt enkel geplakt in het venster waar je begon te dicteren. Wissel
je ondertussen van programma, dan wordt er niets geplakt: de tekst staat dan op het klembord
(Ctrl+V) en je hoort een lage piep.

Het taalmodel mag enkel woorden weglaten: wat je dicteert ("Hey Gemini", "vertaal dit ...")
is nooit een opdracht voor het model. Herschrijft of vertaalt het toch, dan wordt die uitvoer
verworpen en krijg je je eigen tekst (zonder opvulwoorden).

- Er kan maar één dicteervenster tegelijk draaien; een tweede weigert te starten (anders wordt
  alles dubbel geplakt).
- In programma's die als administrator draaien kan Windows het plakken blokkeren.
- Andere sneltoets of microfoon: zie `dicteren` in `config.yaml`
  (microfoons tonen: `.\.venv\Scripts\python.exe -m app.dicteer --microfoons`).

## Web-UI (pc en gsm)

Dubbelklik op `start.bat`, of in PowerShell vanuit de projectmap:

```powershell
.\.venv\Scripts\python.exe start.py
```

De terminal toont de adressen, bv. `https://localhost:8443` (deze pc) en
`https://192.168.x.x:8443` (gsm in hetzelfde wifi-netwerk).

**Wifi op Privé**: staat je netwerk in Windows op *Openbaar*, dan blokkeert de firewall je gsm.
Zet het via Instellingen → Netwerk en internet → Wi-Fi → je netwerk op *Privénetwerk*.

- **Opnemen**: tik op *Opnemen*, spreek, tik op *Stop*. Het transcript verschijnt daarna.
- **Bestand kiezen**: upload een opname (bv. uit de dictafoon-app van je gsm).
- Het transcript is bewerkbaar; kopiëren of downloaden als `.txt`, `.srt` of `.json`.
- Geüploade audio wordt meteen na transcriptie verwijderd (`audio_bewaren: false`).

**Eerste keer op de gsm**: de app gebruikt een eigen (self-signed) certificaat, omdat browsers
de microfoon enkel via https toestaan. Je krijgt een waarschuwing; kies *Geavanceerd* →
*Toch doorgaan*. Het certificaat staat in `certs/` en wordt vanzelf vernieuwd als het IP-adres
van je pc verandert.

**Windows Firewall**: bij de eerste start vraagt Windows of Python toegang mag krijgen tot het
netwerk. Vink enkel **Privénetwerken** aan. Zonder die toestemming bereikt je gsm de pc niet.

Opties: `--poort 9000`, `--host 127.0.0.1` (enkel deze pc), `--http` (zonder certificaat; de
microfoon werkt dan alleen op `http://localhost`).

## Gebruik via de terminal (CLI)

```powershell
.\.venv\Scripts\python.exe -m app.cli pad\naar\opname.m4a
```

Opties:

| Optie | Betekenis |
| --- | --- |
| `--model medium` | ander Whisper-model (bv. `small`, `medium`, `large-v3`) |
| `--taal en` | andere taal, of `auto` om te detecteren |
| `--niet-opslaan` | enkel tonen, geen bestanden schrijven |
| `-v` | meer uitleg (welk model laadt, inkorten vocabulaire) |

Je krijgt het transcript met tijdsstempels per segment in de terminal. Daarnaast komen in
`uitvoer/` twee bestanden: `<naam>_<tijd>.txt` (platte tekst) en `.json` (met segmenten,
taal, duur, model en gebruikte prompt).

De eerste keer duurt het laden langer (download ~1,6 GB voor `large-v3-turbo`).

## Modellen vergelijken (`eval.py`)

Zet testopnames in een map als paren `naam.wav` + `naam.txt` (wat er echt gezegd is) en run:

```powershell
.\.venv\Scripts\python.exe tests\haal_testdata.py      # 15 Nederlandse testzinnen (FLEURS)
.\.venv\Scripts\python.exe eval.py tests\data\fleurs_nl
.\.venv\Scripts\python.exe eval.py tests\data\mijn_opnames --modellen large-v3-turbo large-v3
```

Je krijgt per model het foutpercentage (WER, lager = beter) en de snelheid, ook in
`uitvoer/eval_<tijd>.md`. Eigen opnames met jouw accent en jargon geven het eerlijkste beeld.

Voorbeeldmeting (15 FLEURS-zinnen, 138 s audio, laptop met GTX 1650 Ti, oktober 2026):

| Model | WER | Snelheid CPU | Snelheid GPU (GTX 1650 Ti, int8) |
| --- | --- | --- | --- |
| large-v3-turbo (standaard) | 7,5% | x1,0 realtime | **x4,5 realtime** |
| large-v3 | 7,5% | x0,5 | x2,5 |
| NVIDIA Canary 1B v2 (`onnx:nemo-canary-1b-v2`) | 10,8% | x6,0 | – |
| medium | 13,7% | x1,1 | – |
| NVIDIA Parakeet v3 (`onnx:nemo-parakeet-tdt-0.6b-v3`) | 17,0% | x15,8 | – |

Andere modellen kies je met `whisper.model` (bv. `onnx:nemo-canary-1b-v2`); die kennen
`vocabulaire.txt` niet.

## Configuratie (`config.yaml`)

- `whisper.model`: standaard `large-v3-turbo`; `fallback_model` (`medium`) wordt gebruikt als
  het eerste model niet laadt.
- `whisper.device` / `compute_type`: `auto` = NVIDIA-GPU met int8 als die er is, anders CPU.
  (Op een GTX 1650 Ti is float16 3,5x trager dan int8.)
- `opschonen`: opvulwoorden weg en optioneel het taalmodel (zie hierboven).
- `dicteren`: sneltoets, live aan/uit, pauzeduur, microfoon.
- `whisper.taal`: `nl`; `null` = automatisch.
- `whisper.vad_filter`: slaat stiltes over, vermindert verzonnen tekst bij pauzes.
- `audio_bewaren`: `false` = audio uit de web-UI wordt na transcriptie verwijderd uit
  `uploads/`. De CLI verwijdert nooit jouw eigen bestanden.
- `web.host` / `web.poort`: waar de web-UI luistert (standaard `0.0.0.0:8443`).

## Vaktermen (`data/vocabulaire.txt`)

Zet hier namen, merken en jargon die Whisper juist moet schrijven (één per lijn of
komma-gescheiden, belangrijkste bovenaan). Ze gaan mee als `initial_prompt` en worden
automatisch ingekort tot de limiet van Whisper (223 tokens). Herstart daarna `dicteer.bat`.

## Hoe het werkt

```
microfoon ─► stukken per pauze (Silero VAD) ─► Whisper (GPU/CPU) ─► opvulwoorden weg
         ─► [optioneel] gemma4 via Ollama + vangnet ─► klembord + Ctrl+V ─► klembord terug
```

| Bestand | Wat |
| --- | --- |
| `app/dicteer.py` | sneltoets, opnemen, live knippen, plakken |
| `app/asr.py` | spraakherkenning (faster-whisper of onnx-asr) |
| `app/opschonen.py` + `prompts/opschonen.md` | opvulwoorden en taalmodel |
| `app/gpu.py` | CUDA-bibliotheken vinden, GPU of CPU kiezen |
| `app/web.py` + `app/static/index.html` | web-app |
| `app/cli.py` | audiobestanden omzetten |
| `eval.py` | modellen vergelijken |

## Beperkingen

- Dicteren werkt enkel op Windows (klembord, sneltoets en geluidjes via de Windows-API).
  De web-app en CLI werken ook op macOS/Linux.
- Op een CPU zonder NVIDIA-GPU duurt het omzetten ongeveer even lang als de opname.

## Licentie en dank

MIT, zie [LICENSE](LICENSE). Gebouwd op [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(OpenAI Whisper), [onnx-asr](https://github.com/istupakov/onnx-asr), [Ollama](https://ollama.com)
en [Gemma](https://ai.google.dev/gemma). Testdata: [FLEURS](https://huggingface.co/datasets/google/fleurs)
(CC BY 4.0). De modellen hebben elk hun eigen licentie.
