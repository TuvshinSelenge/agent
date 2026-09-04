# ELK Lead Agent

Ein **Orchestrator mit spezialisierten Agenten**, der täglich öffentliche
österreichische Quellen nach neuen Projekten im Bereich **temporäres Wohnen /
Beherbergung** durchsucht, sie bewertet und morgens einen Lead-Report für den
Vertrieb erzeugt (mit Fokus auf Holz-/Modulbau – „ELK-Relevanz").

## Ziel

Tägliche Identifikation neuer Projekte in Österreich in den Kategorien:

- Mitarbeiterquartiere
- Wohnen auf Zeit / Boarding Houses
- Serviced Apartments
- Budget-Hotels
- Arbeiterunterkünfte
- Studentenheime
- Pflege- und Sozialwohnen mit temporärem Charakter
- Gewerbliche Wohnanlagen für Mitarbeiter

## Architektur

Ein **Orchestrator** koordiniert mehrere Agenten entlang einer Pipeline:

```
Collector-Agenten (parallel)   ->   Analyst-Agent        ->   Enrichment-Agent   ->   Reporting-Agent
(eine Klasse pro Quellgruppe)       (Kategorisierung +        (Ansprechpartner,       (Konsole / Markdown
  · Vergabe/Behörden                 Scoring)                  Volumen, Potenzial,      / HTML / JSON)
  · Widmung/Bauverfahren             + Relevanzfilter          ELK-Relevanz,
  · Immobilienentwickler             + Dedup                   nächste Aktion)
  · Hotel/Tourismus                  + 24h-Zeitfenster
  · Presse/Fachportale               + „schon gesehen"-Filter
```

| Komponente | Datei | Aufgabe |
| --- | --- | --- |
| Orchestrator | `orchestrator.py` | Führt Agenten (parallel) aus und steuert die Pipeline |
| Collector-Agenten | `sources/collectors.py` | Ein Agent pro Quellgruppe (Vergabe, Widmung, Entwickler, Hotel, Presse) |
| Analyst-Agent | `scoring.py` | Kategorisierung + Bewertung nach dem Punkteschema |
| Enrichment-Agent | `enrichment.py` | Ansprechpartner, Volumen, Potenzial, ELK-Relevanz, nächste Aktion |
| Reporting-Agent | `report.py` | Report in Konsole, Markdown, HTML, JSON |
| E-Mail-Agent | `emailer.py` | Formatiertes HTML-Mail mit Report-Link + HTML-Anhang |
| Web-UI (on demand) | `webapp.py` | Seite mit Buttons: „Jetzt aktualisieren" und „… & per E-Mail senden" |
| Report-Server | `server.py` | Liefert `output/` als statische Website aus (für Report-Links) |
| Scheduler | `scheduler.py` | Täglicher Lauf (Standard 06:00) |
| Zustand | `state.py` | Dedup über Läufe hinweg (nur „neue" Projekte melden) |

### Quellen

Die Quellen (ANKÖ, Auftrag.at, TED, Bundesbeschaffung, Landesvergabeportale,
Amtsblätter/Kundmachungen/UVP, UBM/ARE/Soravia/Buwog/Value One,
Tourismusverbände/WKO, Immobilien Magazin/Der Standard/Leadersnet/Kommunalnet)
sind in `config/config.yaml` konfiguriert.

Jeder Collector kann **live** (echter Netzwerkabruf) oder aus **Fixtures**
(mitgelieferte Beispieldaten) laufen. Standardmäßig laufen alle Quellen aus
Fixtures, damit die Pipeline deterministisch und offline lauffähig ist. Für TED
ist ein Best-Effort-Live-Abruf implementiert (`live: true` in der Config); bei
Fehlern wird automatisch auf Fixtures zurückgefallen. Die übrigen Collector sind
als saubere Erweiterungspunkte für echte Integrationen angelegt.

## Bewertungssystem

| Kriterium | Punkte |
| --- | --- |
| Projektvolumen > 2 Mio. € | +20 |
| Holz- oder Modulbau erwähnt | +30 |
| Einreichung steht bevor | +20 |
| Investor bekannt | +10 |
| Hotel / Mitarbeiterquartier | +20 |

**Ab 60 Punkten → Lead für den Vertrieb.** Alle Regeln, Kategorien, Suchbegriffe
und Schwellen sind in `config/config.yaml` anpassbar.

## Installation

```bash
bash scripts/setup.sh        # legt .venv an und installiert das Paket
```

## Nutzung

```bash
# Einmaliger Lauf mit Konsolen-Report (schreibt zusätzlich md/html/json nach output/)
.venv/bin/elk-agent run

# Andere Ausgabeformate auf stdout
.venv/bin/elk-agent run --format markdown
.venv/bin/elk-agent run --format json

# Ohne Zustandsspeicher (zeigt bei jedem Lauf alle Projekte, nichts wird als "gesehen" markiert)
.venv/bin/elk-agent run --no-state

# Konfigurierte Quellen anzeigen
.venv/bin/elk-agent sources

# Täglich um 06:00 laufen (blockierend)
.venv/bin/elk-agent schedule --at 06:00
```

## E-Mail-Versand

Der Report kann automatisch per E-Mail verschickt werden. Die E-Mail ist selbst
schön formatiert (Übersicht + Top-Leads), enthält einen **„HTML-Report öffnen"-Link**
und den vollständigen HTML-Report als **Anhang** (Klick öffnet die formatierte Seite).

SMTP-Zugangsdaten werden aus Umgebungsvariablen / Secrets gelesen (nie im Repo):

| Variable | Bedeutung | Standard |
| --- | --- | --- |
| `SMTP_HOST` | SMTP-Server | – (erforderlich) |
| `SMTP_PORT` | Port | `587` |
| `SMTP_USERNAME` | Login-Benutzer | – |
| `SMTP_PASSWORD` | Login-Passwort | – |
| `SMTP_FROM` | Absenderadresse | `SMTP_USERNAME` |
| `SMTP_STARTTLS` | STARTTLS verwenden | `true` |
| `SMTP_TO` | Empfänger überschreiben (optional) | `config email.recipients` |

Empfänger und Betreff-Präfix stehen in `config/config.yaml` (`email:`). Der
Standardempfänger ist bereits hinterlegt.

```bash
# Report erzeugen und per E-Mail senden
.venv/bin/elk-agent run --email

# Empfänger ad hoc überschreiben
.venv/bin/elk-agent run --email --to "name@firma.at"

# Täglich um 06:00 erzeugen UND versenden
.venv/bin/elk-agent schedule --at 06:00 --email
```

### On-Demand (Web-UI mit Buttons)

Für den Abruf „auf Knopfdruck" gibt es eine kleine Web-Oberfläche. Sie zeigt den
aktuellen Report und bietet zwei Buttons:

- **🔄 Jetzt aktualisieren** – führt sofort einen frischen Lauf aus und zeigt das Ergebnis.
- **📧 Aktualisieren & per E-Mail senden** – führt einen frischen Lauf aus und schickt den Report **sofort** per E-Mail an die konfigurierten Empfänger.

```bash
.venv/bin/elk-agent web --port 8000
# -> Browser öffnen: http://<host>:8000/  und Button klicken
```

In der Cloud-Agent-Umgebung läuft diese Web-UI automatisch als Terminal
`lead-agent-web` auf Port `8000` – einfach die Seite öffnen und den Button
klicken, um jederzeit den aktuellen Stand per Mail zu bekommen.

## Report als Website (GitHub Pages) – ohne E-Mail

Wenn E-Mails im Postfach blockiert/quarantänisiert werden, lässt sich der Report
stattdessen als **Web-Seite** veröffentlichen. Der Workflow
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) erzeugt den Report
und stellt ihn über **GitHub Pages** bereit – einfach die URL öffnen, kein
E-Mail-Versand und keine blockierbaren Links nötig.

- **Aktualisierung:** **stündlich automatisch** (cron), bei jedem `push` auf `main`, und on demand über **Actions → „Report-Website (GitHub Pages)" → Run workflow**.
- Die Seite lädt sich alle 15 Minuten selbst neu, damit neue Stände ohne manuelles Neuladen erscheinen. In der Praxis muss man also **gar nicht klicken** – der Button ist nur für „sofort neu berechnen".
- Kein SMTP nötig.
- **Recherche-Agent:** Ist das GitHub-Actions-Secret `OPENAI_API_KEY` gesetzt, liest der Agent echte Quellen (RSS/TED) und lässt ein LLM die relevanten Projekte auswählen/extrahieren – **alle Links sind echt und aufrufbar**. Ohne Key läuft der deterministische Live-Modus (nur echte Feeds). `Settings → Secrets and variables → Actions → OPENAI_API_KEY`.

### Einmalige Einrichtung

1. `Repo → Settings → Pages → Build and deployment → Source: **GitHub Actions**`.
2. Workflow einmal laufen lassen (Push auf `main` oder **Run workflow**).
3. Die veröffentlichte URL steht danach im Deploy-Schritt des Workflows und unter
   `Settings → Pages` – typischerweise `https://<owner>.github.io/agent/`.

Hinweis: GitHub Pages ist für öffentliche Repositories kostenlos; für private
Repositories ist ggf. ein entsprechender GitHub-Plan nötig.

### Damit der Link funktioniert (Report hosten)

Der Link in der Mail zeigt auf `email.public_base_url` + `report_filename`.
Setze `public_base_url` in der Config (oder die Umgebungsvariable
`REPORT_PUBLIC_URL`) auf die öffentliche Adresse, unter der die Reports liegen.

Zum Ausliefern des `output/`-Verzeichnisses gibt es einen kleinen Server:

```bash
.venv/bin/elk-agent serve --port 8000
# -> http://<host>:8000/report_latest.html
```

Ist keine `public_base_url` gesetzt, wird der vollständige Report als Anhang
mitgeschickt (öffnet ebenfalls die formatierte Seite).

Der Report enthält pro Projekt: **Projekt, Ort, Status, Score, Potenzial,
ELK-Relevanz** sowie in den Lead-Details **Link zur Quelle, Ansprechpartner,
Projektstand, geschätztes Volumen, ELK-Relevanz und die empfohlene nächste
Aktion**.

## Tests & Lint

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```
