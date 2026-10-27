<script lang="ts">
  import { app } from '../lib/store.svelte';
  import { ACCEPT } from '../lib/format';
  import DocCard from './DocCard.svelte';
  import Icon from './Icon.svelte';

  let picker: HTMLInputElement;
  const isRecent = $derived(app.workspace === 'search' && !app.activeTags.length && app.kindFilter === 'all');
  const documents = $derived(isRecent ? app.visibleDocs.slice(0, 6) : app.visibleDocs);
  const kindTitle = $derived(app.kindFilter === 'pdf' ? 'Documenti PDF' : app.kindFilter === 'image' ? 'Immagini' : app.kindFilter === 'notes' ? 'Note e testi' : 'Tutti i documenti');
</script>

<section class="library" aria-label={isRecent ? 'Documenti recenti' : 'Archivio documenti'}>
  <div class="head">
    <div class="heading"><h2>{isRecent ? 'Tracce recenti' : app.activeTags.length ? 'Documenti filtrati' : kindTitle}</h2><span class="total">{isRecent ? app.docs.length : app.visibleDocs.length}</span></div>
    <div class="tools">
      <label class="sort"><span class="sr-only">Ordina per</span><select aria-label="Ordina documenti" value={app.sort} onchange={(e) => app.setSort(e.currentTarget.value as 'recent' | 'name' | 'size')}><option value="recent">Più recenti</option><option value="name">Nome</option><option value="size">Dimensione</option></select></label>
      <div class="seg" role="group" aria-label="Vista documenti"><button class:on={app.view === 'grid'} aria-pressed={app.view === 'grid'} aria-label="Vista a griglia" onclick={() => app.setView('grid')}><Icon name="grid" size={14} /></button><button class:on={app.view === 'list'} aria-pressed={app.view === 'list'} aria-label="Vista a elenco" onclick={() => app.setView('list')}><Icon name="list" size={15} /></button></div>
    </div>
  </div>
  {#if app.activeTags.length || app.kindFilter !== 'all'}
    <div class="filters">
      {#if app.kindFilter !== 'all'}<button class="chip" onclick={() => app.setKind('all')} aria-label="Rimuovi filtro tipo">{kindTitle}<Icon name="x" size={10} /></button>{/if}
      {#each app.activeTags as tag}<button class="chip" onclick={() => app.toggleTag(tag)} aria-label={`Rimuovi filtro ${tag}`}>#{tag}<Icon name="x" size={10} /></button>{/each}
      <button class="reset" onclick={() => { app.clearFilters(); app.setKind('all'); }}>Azzera filtri</button>
    </div>
  {/if}

  {#if app.loading}
    <div class="grid">{#each Array(6) as _}<div class="skeleton"></div>{/each}</div>
  {:else if app.loadError}
    <div class="state"><Icon name="alert" size={28} /><h3>Non riusciamo a caricare l’archivio.</h3><p>{app.loadError}</p><button class="btn" onclick={() => app.refresh()}>Riprova</button></div>
  {:else if documents.length === 0}
    <div class="state"><span class="empty-icon"><Icon name="library" size={28} stroke={1.3} /></span><h3>{app.activeTags.length || app.kindFilter !== 'all' ? 'Qui non ci sono ancora documenti.' : 'Ogni archivio inizia da un documento.'}</h3><p>{app.activeTags.length || app.kindFilter !== 'all' ? 'Prova a cambiare i filtri o aggiungi un nuovo file.' : 'Aggiungi i tuoi file. Al momento giusto, saprai dove ritrovarli.'}</p><button class="btn" onclick={() => picker.click()}><Icon name="plus" size={14} /> Aggiungi documenti</button></div>
  {:else if app.view === 'grid'}
    <div class="grid">{#each documents as doc (doc.id)}<DocCard {doc} view="grid" />{/each}</div>
  {:else}
    <div class="list"><div class="list-head" aria-hidden="true"><span>Documento</span><span>Tipo</span><span>Dimensione</span><span>Aggiunto</span><span>Stato</span></div>{#each documents as doc (doc.id)}<DocCard {doc} view="list" />{/each}</div>
  {/if}
  {#if isRecent && app.docs.length > documents.length}
    <button class="see-all" onclick={() => app.navigate('archive')}>Esplora tutti i {app.docs.length} documenti <Icon name="arrow-right" size={13} /></button>
  {/if}
</section>
<input bind:this={picker} aria-label="Aggiungi documenti all’archivio" type="file" multiple accept={ACCEPT} hidden onchange={(e) => { void app.addFiles([...(e.currentTarget.files ?? [])]); e.currentTarget.value = ''; }} />

<style>
  .head { padding-bottom: 13px; border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
  .heading { display: flex; align-items: center; gap: 9px; }
  h2 { font: 12px var(--mono); letter-spacing: .07em; text-transform: uppercase; }
  .total { display: grid; place-items: center; min-width: 22px; padding: 1px 5px; border: 1px solid var(--border); border-radius: 0; color: var(--text-faint); font: 11px/1.6 var(--mono); }
  .tools { display: flex; align-items: center; gap: 8px; margin-left: auto; }
  select { height: 32px; width: 120px; padding: 0 7px; border: 0; background: transparent; color: var(--text-dim); font-size: 12px; }
  select option { background: var(--bg-elev); color: var(--text); }
  .seg { display: flex; padding: 3px; border: 1px solid var(--border); border-radius: 1px; }
  .seg button { display: grid; place-items: center; width: 27px; height: 24px; padding: 0; border: 0; border-radius: 0; background: transparent; color: var(--text-faint); }
  .seg button.on { background: var(--bg-hover); color: var(--text); }
  .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 15px; }
  .list { border-top: 1px solid var(--border); }
  .list-head { display: grid; grid-template-columns: minmax(0, 1fr) 70px 80px 96px 128px; gap: 14px; padding: 10px 12px; border-bottom: 1px solid var(--border); font: 11px var(--mono); text-transform: uppercase; letter-spacing: .04em; color: var(--text-faint); }
  .filters { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin: -3px 0 16px; }
  .reset { border: 0; background: transparent; color: var(--text-faint); font-size: 12px; text-decoration: underline; text-underline-offset: 3px; }
  .see-all { display: flex; align-items: center; justify-content: center; gap: 9px; width: fit-content; margin: 24px auto 0; padding: 7px 12px; border: 0; background: transparent; color: var(--text-dim); font-size: 12px; }
  .see-all:hover { color: var(--text); }
  .skeleton { height: 230px; background: var(--bg-elev); border: 1px solid var(--border); border-radius: var(--radius); animation: pulse 1.5s infinite; }
  .state { display: flex; align-items: center; flex-direction: column; gap: 12px; min-height: 230px; justify-content: center; padding: 35px 20px; border: 1px dashed var(--border-strong); border-radius: 10px; color: var(--text-faint); text-align: center; }
  .empty-icon { display: grid; place-items: center; width: 56px; height: 56px; margin-bottom: 4px; border: 1px solid var(--border-strong); border-radius: 13px; }
  .state h3 { color: var(--text); font-size: 16px; font-weight: 450; letter-spacing: -.025em; }
  .state p { max-width: 360px; font-size: 14px; }
  .state .btn { margin-top: 8px; }
  @media (max-width: 1180px) and (min-width: 901px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 760px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } .list-head { grid-template-columns: minmax(0, 1fr) 110px; } .list-head > span:not(:first-child):not(:last-child) { display: none; } .tools { gap: 5px; } }
  @media (max-width: 420px) { .grid { grid-template-columns: minmax(0, 1fr); } }
</style>
