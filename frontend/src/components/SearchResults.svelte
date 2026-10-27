<script lang="ts">
  import { app } from '../lib/store.svelte';
  import { queryTerms } from '../lib/text';
  import { KIND_LABEL, formatSize } from '../lib/format';
  import Highlight from './Highlight.svelte';
  import Icon from './Icon.svelte';
  import Thumb from './Thumb.svelte';
  const terms = $derived(queryTerms(app.query));
</script>

<section class="results" aria-label="Risultati di ricerca" aria-busy={app.searching}>
  <div class="head"><div><h2>{#if app.searching && !app.visibleHits.length}Cerco tra i tuoi documenti…{:else}{app.visibleHits.length} {app.visibleHits.length === 1 ? 'risultato' : 'risultati'}{/if}</h2></div><span class="order"><Icon name="layers" size={12} /> Per pertinenza</span></div>
  {#if app.activeTags.length || app.kindFilter !== 'all'}<div class="filters">{#each app.activeTags as tag}<button class="chip" onclick={() => app.toggleTag(tag)} aria-label={`Rimuovi filtro ${tag}`}>#{tag}<Icon name="x" size={11} /></button>{/each}{#if app.kindFilter !== 'all'}<button class="chip" onclick={() => app.setKind('all')} aria-label="Rimuovi filtro tipo">{app.kindFilter === 'notes' ? 'Note e testi' : app.kindFilter === 'image' ? 'Immagini' : 'PDF'}<Icon name="x" size={11} /></button>{/if}</div>{/if}

  {#if app.searchError}
    <div class="state"><Icon name="alert" size={27} /><h3>La ricerca si è interrotta.</h3><p>{app.searchError}</p><button class="btn" onclick={() => app.runSearch()}>Riprova</button></div>
  {:else if app.searching && !app.visibleHits.length}
    <div class="skeletons" aria-label="Ricerca in corso">{#each Array(3) as _}<div class="skeleton"></div>{/each}</div>
  {:else if !app.searching && !app.visibleHits.length}
    <div class="state"><Icon name="search" size={30} stroke={1.3} /><h3>Proviamo con altre parole.</h3><p>Nessun documento corrisponde a questa ricerca. Descrivi l’argomento in un altro modo, oppure rimuovi un filtro.</p>{#if app.activeTags.length || app.kindFilter !== 'all'}<button class="btn" onclick={() => { app.clearFilters(); app.setKind('all'); }}>Rimuovi filtri</button>{/if}</div>
  {:else}
    <ol class:stale={app.searching}>
      {#each app.visibleHits as hit, index (hit.doc.id)}
        <li><button class="result" onclick={() => app.openDoc(hit.doc.id)} aria-label={`Apri ${hit.doc.name}`}>
          <span class="rank">{String(index + 1).padStart(2, '0')}</span>
          <span class="result-main">
            <span class="document"><Thumb doc={hit.doc} compact /><span class="document-info"><span class="name"><Highlight text={hit.doc.name} {terms} /></span><span class="meta">{KIND_LABEL[hit.doc.kind]}<span>·</span>{formatSize(hit.doc.size)}{#if hit.doc.pages}<span>·</span>{hit.doc.pages} pagine{/if}</span></span><Icon name="arrow-up-right" size={17} /></span>
            {#each hit.matches.slice(0, 2) as match (match.chunkId)}<span class="passage">{#if match.page}<span class="passage-label">PAGINA {match.page}</span>{/if}<span class="passage-text"><Highlight text={match.text} {terms} /></span></span>{:else}<span class="passage"><span class="passage-text">{hit.doc.excerpt}</span></span>{/each}
            {#if hit.doc.tags.length}<span class="tags">{#each hit.doc.tags as tag}<span class="chip">{tag}</span>{/each}</span>{/if}
          </span>
        </button></li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .head { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 25px; }
  h2 { margin-top: 7px; font-size: 28px; font-weight: 350; letter-spacing: -.04em; }
  .order { display: flex; align-items: center; gap: 7px; padding-bottom: 5px; color: var(--text-faint); font-size: 12px; white-space: nowrap; }
  .filters { display: flex; flex-wrap: wrap; gap: 7px; margin: -8px 0 20px; }
  ol { margin: 0; padding: 0; list-style: none; transition: opacity .2s; }
  ol.stale { opacity: .5; }
  .result { display: flex; align-items: start; gap: 20px; width: 100%; position: relative; padding: 22px 20px 24px; margin-bottom: 14px; border: 1px solid var(--border); background: transparent; text-align: left; transition: background .15s, border-color .15s; }
  .result:hover { background: var(--bg-elev); border-color: var(--border-strong); }
  .result::before { content: ''; position: absolute; left: -1px; top: -1px; width: 13px; height: 13px; border: solid var(--text-faint); border-width: 1px 0 0 1px; }
  .rank { flex: none; width: 23px; padding-top: 12px; color: var(--text-faint); font: 12px var(--mono); }
  .result-main { display: flex; flex-direction: column; flex: 1; min-width: 0; gap: 17px; }
  .document { display: flex; align-items: center; gap: 12px; }
  .document > :global(svg) { margin-left: auto; color: var(--text-faint); flex: none; }
  .document-info { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; font-weight: 500; letter-spacing: -.01em; }
  .meta { display: flex; align-items: center; gap: 7px; color: var(--text-faint); font-size: 12px; }
  .passage { display: flex; flex-direction: column; gap: 8px; padding: 10px 14px; border-left: 1px solid var(--text-faint); background: var(--console); }
  .passage-label { color: var(--text-faint); font: 11px var(--mono); letter-spacing: .1em; }
  .passage-text { display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-dim); font-size: 15px; line-height: 1.8; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .state { display: flex; flex-direction: column; align-items: center; gap: 15px; padding: 70px 20px; border: 1px dashed var(--border-strong); border-radius: 1px; color: var(--text-faint); text-align: center; }
  .state h3 { color: var(--text); font-size: 20px; font-weight: 450; letter-spacing: -.03em; }
  .state p { max-width: 390px; font-size: 14px; line-height: 1.8; }
  .skeleton { height: 150px; margin-bottom: 15px; background: var(--bg-elev); border: 1px solid var(--border); border-radius: 1px; animation: pulse 1.5s infinite; }
  @media (max-width: 600px) { h2 { font-size: 24px; } .order { display: none; } .result { gap: 10px; padding-inline: 12px; } .rank { width: 16px; } .document { gap: 9px; } .name { font-size: 14px; } .passage-text { font-size: 14px; } }
</style>
