# Nordreisa – bildebibliotek

Dette er det offentlige bildearkivet for Nordreisa / PALT. Publiserte bilder ligger i `docs/webp/` og `docs/avif/`. Behold filnavn og mapper når bildene er tatt i bruk på nettsidene.

Åpne [bildebiblioteket](https://leamarketing.github.io/nordreisa-bilder/). Her kan du søke, kopiere bildeadresser, forhåndsvise sidene og hente ferdige TXT-filer.

## Finn og bruk et bilde

Åpne bildebiblioteket, søk etter prosjektkode eller motiv, og velg «Kopier adresse». WebP er standardvalget; AVIF er beholdt der nettsidene allerede bruker det. Flere bredder er bevisste varianter for mobil og større skjermer.

## Oppdateringer

Legg nye motiv inn med et nytt filnavn. Er et bilde i bruk, behold den gamle filen slik at eldre sider fortsatt virker. Endringer har historikk i GitHub. En separat gjenopprettingskopi er også laget.

`asset-manifest.json` beskriver filene. Kjør `python3 scripts/check_assets.py` før publisering. GitHub kontrollerer filene ved endringer.

`source/original/` inneholder publisert sidekode fra før flyttingen. Den inneholder gamle bildeadresser og skal brukes til sporbarhet. Nye komplette HTML-filer for ClickSites ligger som TXT i `clicksites/`. Alle 39 filer kan også lastes ned samlet fra bildebiblioteket. Sidene må fortsatt legges inn og publiseres i ClickSites.

For å gjenskape sidefilene: `python3 scripts/migrate_clicksites.py --base-url https://leamarketing.github.io/nordreisa-bilder/`.

Bildene er prosjektets illustrasjoner og konseptmateriale. Dette arkivet gir ingen generell åpen lisens til gjenbruk.
