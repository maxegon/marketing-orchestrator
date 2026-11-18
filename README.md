# marketing-orchestrator

Lancia all'ora esatta i workflow marketing (`marketing-scelte`, `marketing-storie`, `marketing-render`) di 4 app:
PodcastViewLens, ShowViewLens, SportViewLens e Solo1Meteo.

## Perché esiste

Dal 12 al 18/11/2026 i cron di GitHub sui repo privati sono arrivati con **6-9 ore di ritardo**: tra le 5:00 e le 13:00 (ora di Roma) non partiva quasi nessuna run.
Di conseguenza video consegnati in ritardo, storie scartate e anteprime in piena notte.

## Come funziona

1. **cron-job.org** chiama `tick.yml` di questo repo ogni 5 minuti, dalle 06:00 alle 23:55 (Europe/Rome), con `workflow_dispatch`.
2. **`tick.py`** prende l'ora di creazione della run, la arrotonda ai 5 minuti e cerca in **`orari.json`** i giri di quell'ora.
3. Per ogni giro chiama `POST /repos/maxegon/<repo>/actions/workflows/<workflow>/dispatches` con il secret `ORCH_TOKEN`.

Il repo è **pubblico** perché sui repo pubblici Actions non consuma minuti: circa 216 run al giorno qui sono gratis.
Sui repo privati costerebbero circa 6.500 minuti al mese, contro i 2.000 disponibili.

I cron dei repo delle app restano come **riserva**:
- `scelte` e `storie` sono idempotenti, quindi un doppio giro non fa danni;
- `marketing-render` ha un job `gate` che salta il cron in ritardo se l'orchestrator ha già fatto il giro "genera" nelle ultime 12 ore. In PodcastViewLens c'è lo stesso controllo anche per "oggi".

## Cambiare un orario

Modifica `orari.json`: l'ora è quella di Roma e i minuti devono essere multipli di 5. Poi:

```bash
python3 tick.py --valida && python3 test_tick.py
```

Fai commit e push: vale dal tick successivo. L'ora legale la gestisce `tick.py`, quindi non c'è niente da cambiare a marzo e ottobre.

## Provare

- Su Actions, lancia **tick** a mano con `ora` = `20:00` e `dry_run` = true: mostra cosa lancerebbe, senza lanciare.
- Da terminale: `python3 tick.py --dry-run --ora 20:00`

## Configurazione (una volta)

- **Secret `ORCH_TOKEN`** (Settings > Secrets and variables > Actions): PAT fine-grained.
  - Repository access: PodcastViewLens, showviewlens, SportViewLens, solo1meteo, marketing-orchestrator.
  - Permission: **Actions: Read and write**.
- **cron-job.org**: un solo job.
  - URL: `https://api.github.com/repos/maxegon/marketing-orchestrator/actions/workflows/tick.yml/dispatches`
  - POST con body `{"ref":"main"}` e gli header `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
  - Pianificazione: ogni 5 minuti, ore 6-23, fuso Europe/Rome.
  - Notifica "on failure".

Se una chiamata ai workflow delle app fallisce, la run di `tick` fallisce e GitHub manda una mail.
