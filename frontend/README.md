# Esper — frontend

Interfaccia web (Svelte 5 + Vite + TypeScript). Per ora lavora su **dati simulati**: non serve il backend.

```bash
npm install
npm run dev      # http://localhost:5173
npm run check    # type-check con svelte-check
npm run build    # produce dist/
```

- `?q=testo` nell'URL precompila la ricerca.
- Per usare il backend vero: `VITE_API=http npm run dev` (vedi `../docs/API_CONTRACT.md`).

## Interfaccia

- La schermata iniziale mette al centro la ricerca in linguaggio naturale, con
  esempi cliccabili e documenti aggiunti di recente. La console di richiamo mostra
  anche immagini selezionabili dell’archivio, con inquadratura ottica e date.
- `Tutti i documenti` apre l’archivio completo: vista a griglia o elenco,
  ordinamento e filtri per formato ed etichette combinabili.
- I risultati mostrano i passaggi pertinenti e, quando disponibili, le pagine.
- Il dettaglio documento offre anteprima, passaggi, informazioni, modifica delle
  etichette, apertura dell’originale ed eliminazione con conferma.
- Il pulsante sole/luna nella barra laterale cambia il tema monocromatico.
  Tema, ordinamento e vista vengono ricordati nel browser.
- `/` oppure `Ctrl+K` / `Cmd+K` porta il focus alla ricerca. `Esc` chiude il
  dettaglio o il menu mobile. Nel dettaglio, le frecce cambiano scheda.
- Il pulsante pausa nella barra superiore ferma le animazioni e ricorda la
  preferenza. È rispettata anche l’impostazione di movimento ridotto del sistema.

La direzione visiva, i riferimenti e il prompt della fotografia dimostrativa
generata sono documentati in [`DESIGN.md`](DESIGN.md).

La modalità demo mantiene i documenti in memoria: ricaricando la pagina si torna
ai dati di esempio. Ricerca e indicizzazione nell’interfaccia sono ancora simulate;
la ricerca reale del backend non è implementata.

## Struttura

- `src/lib/types.ts` — contratto dati e interfaccia `EsperApi`
- `src/lib/api/` — `mock.ts` (demo), `http.ts` (backend), `seed.ts` (documenti d'esempio)
- `src/lib/store.svelte.ts` — stato globale (runes)
- `src/components/` — componenti UI
