<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/store.svelte';
  import { ACCEPT } from './lib/format';
  import DetailPanel from './components/DetailPanel.svelte';
  import Icon from './components/Icon.svelte';
  import Library from './components/Library.svelte';
  import MemoryField from './components/MemoryField.svelte';
  import SearchBar from './components/SearchBar.svelte';
  import SearchResults from './components/SearchResults.svelte';
  import Sidebar from './components/Sidebar.svelte';
  import Toasts from './components/Toasts.svelte';

  let picker: HTMLInputElement;
  let dragDepth = $state(0);
  const examples = ['Il contratto della casa in affitto', 'Come funziona una rete neurale', 'Una foto del mare al tramonto'];

  onMount(() => {
    document.documentElement.dataset.motion = app.motion;
    void app.init();
    const q = new URLSearchParams(location.search).get('q');
    if (q) app.setQuery(q);
    return () => app.destroy();
  });

  const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files');

  function onkeydown(e: KeyboardEvent) {
    const el = e.target as HTMLElement | null;
    const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
    if (((e.key === '/' && !typing && !e.metaKey && !e.ctrlKey) || (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey))) && app.selectedId === null) {
      e.preventDefault();
      document.getElementById('search')?.focus();
    } else if (e.key === 'Escape') {
      if (app.selectedId !== null) app.closeDoc();
      else if (app.sidebarOpen) app.sidebarOpen = false;
    }
  }
</script>

<svelte:window
  {onkeydown}
  ondragenter={(e) => { if (hasFiles(e)) { e.preventDefault(); dragDepth++; } }}
  ondragover={(e) => hasFiles(e) && e.preventDefault()}
  ondragleave={(e) => hasFiles(e) && (dragDepth = Math.max(0, dragDepth - 1))}
  ondrop={(e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    void app.addFiles([...(e.dataTransfer?.files ?? [])]);
  }}
/>

<div class="shell">
  <Sidebar />
  <main id="main-content">
    <header class="topbar">
      <div class="breadcrumb">
        <button class="icon-btn menu" aria-label="Apri menu" aria-expanded={app.sidebarOpen} onclick={() => (app.sidebarOpen = true)}><Icon name="menu" /></button>
        <span class="header-cross" aria-hidden="true">+</span>
        <strong>{app.workspace === 'search' ? 'Ricerca' : 'Archivio'}</strong>
      </div>
      <div class="top-actions">
        {#if app.inflight > 0}<span class="busy"><span class="activity-dot"></span>{app.inflight} in elaborazione</span>{/if}
        <button class="icon-btn motion-toggle" aria-label={app.motion === 'on' ? 'Metti in pausa le animazioni' : 'Attiva le animazioni'} title={app.motion === 'on' ? 'Pausa animazioni' : 'Attiva animazioni'} aria-pressed={app.motion === 'off'} onclick={() => app.toggleMotion()}><Icon name={app.motion === 'on' ? 'pause' : 'play'} size={15} /></button>
        <button class="btn import" aria-label="Aggiungi documenti" title="Aggiungi documenti" onclick={() => picker.click()}><Icon name="plus" size={17} /><span>Aggiungi documenti</span></button>
      </div>
    </header>

    <div class="content">
      <div class="page" class:archive={app.workspace === 'archive'} class:searching={app.isSearching}>
        <section class="intro" aria-label="Ricerca documenti">
          <div class="recall-stage">
            <div class="intro-copy">
              <h1>{#if app.workspace === 'search'}Cosa vuoi<br /><span>ritrovare?</span>{:else}Il tuo archivio<span>.</span>{/if}</h1>
              {#if app.workspace === 'search'}<p class="description">Ritrova i tuoi documenti con parole tue.</p>{/if}
            </div>
            {#if app.workspace === 'search'}<div class="memory-visual"><MemoryField /></div>{/if}
          </div>
          <SearchBar />
          {#if !app.isSearching && app.workspace === 'search'}
            <div class="suggestions" aria-label="Esempi di ricerca">
              {#each examples as query}
                <button onclick={() => { app.setQuery(query); void app.runSearch(); }}>{query}<Icon name="arrow-up-right" size={13} /></button>
              {/each}
            </div>
          {/if}
        </section>

        {#if app.isSearching}<SearchResults />{:else}<Library />{/if}
      </div>
    </div>
  </main>

  {#if app.selectedId !== null}<DetailPanel />{/if}
  <Toasts />
  {#if dragDepth > 0}
    <div class="drop" aria-hidden="true"><div class="drop-inner"><Icon name="focus" size={42} stroke={1} /><strong>Aggiungi all’archivio</strong><span>Rilascia qui i documenti.</span></div></div>
  {/if}
</div>
<input bind:this={picker} aria-label="Seleziona documenti da importare" type="file" multiple accept={ACCEPT} hidden onchange={(e) => { void app.addFiles([...(e.currentTarget.files ?? [])]); e.currentTarget.value = ''; }} />

<style>
  .shell { display: flex; height: 100%; }
  main { display: flex; flex: 1; flex-direction: column; min-width: 0; }
  .topbar { display: flex; align-items: center; justify-content: space-between; flex: none; gap: 16px; min-height: 68px; padding: 0 32px; border-bottom: 1px solid var(--border); background: var(--bg); }
  .breadcrumb { display: flex; align-items: center; gap: 14px; color: var(--text-dim); font: 12px var(--mono); letter-spacing: .07em; text-transform: uppercase; }
  .breadcrumb strong { font-weight: 400; }
  .header-cross { font-size: 22px; font-weight: 300; }
  .top-actions { display: flex; align-items: center; gap: 13px; }
  .import { min-height: 36px; padding-inline: 12px; border-color: var(--border-strong); background: transparent; font-size: 13px; }
  .busy { display: flex; align-items: center; gap: 7px; color: var(--text-faint); font-size: 12px; }
  .activity-dot { width: 4px; height: 4px; background: var(--text-dim); border-radius: 50%; animation: pulse 2s ease-in-out infinite; }
  .motion-toggle { width: 34px; height: 34px; }
  .content { flex: 1; min-height: 0; overflow-y: auto; background-image: linear-gradient(var(--grid) 1px, transparent 1px), linear-gradient(90deg, var(--grid) 1px, transparent 1px); background-size: 64px 64px; }
  .page { width: 100%; max-width: 1280px; padding: 33px 37px 38px; margin-inline: auto; }
  .intro { position: relative; margin-bottom: 34px; padding: 27px; border: 1px solid var(--border); background: var(--console); }
  .intro::before, .intro::after { content: ''; position: absolute; z-index: 2; width: 13px; height: 13px; border: solid var(--text-dim); pointer-events: none; }
  .intro::before { left: -1px; top: -1px; border-width: 1px 0 0 1px; }
  .intro::after { right: -1px; bottom: -1px; border-width: 0 1px 1px 0; }
  .recall-stage { display: grid; grid-template-columns: 1fr 1.05fr; align-items: center; gap: 30px; margin: 0 0 29px; }
  .intro-copy { padding-block: 18px; }
  h1 { margin: 0 0 22px; font-size: clamp(48px, 4.3vw, 64px); line-height: 1.05; letter-spacing: -.06em; font-weight: 350; }
  h1 span { color: var(--text-dim); }
  .description { max-width: 310px; color: var(--text-dim); font-size: 15px; line-height: 1.8; }
  .memory-visual { min-width: 0; }
  .suggestions { display: flex; flex-wrap: wrap; align-items: center; gap: 7px 21px; margin-top: 19px; }
  .suggestions button { display: inline-flex; align-items: center; gap: 8px; min-height: 32px; padding: 3px 0; border: 0; background: transparent; color: var(--text-dim); font-size: 12px; transition: color .2s; text-align: left; }
  .suggestions button:hover { color: var(--text); }
  .archive .recall-stage { display: block; margin-bottom: 22px; }
  .archive h1 { margin-bottom: 0; font-size: 40px; }
  .archive .intro-copy { padding-block: 0; }
  .searching .recall-stage { display: none; }
  .searching .intro { margin-bottom: 30px; }
  .menu { display: none; }
  .drop { position: fixed; z-index: 200; inset: 0; display: grid; place-items: center; background: var(--scrim); backdrop-filter: blur(8px); pointer-events: none; animation: fade-in .15s; }
  .drop-inner { display: flex; align-items: center; flex-direction: column; gap: 17px; max-width: calc(100vw - 32px); padding: 50px 70px; border: 1px solid var(--text-dim); background: var(--bg-elev); color: var(--text-dim); text-align: center; }
  .drop-inner strong { color: var(--text); font-size: 30px; font-weight: 350; letter-spacing: -.04em; }
  .drop-inner span { font-size: 15px; }
  @media (max-width: 1200px) { .page { padding-inline: 27px; } .intro { padding-inline: 22px; } .recall-stage { gap: 20px; } h1 { font-size: 52px; } }
  @media (max-width: 1000px) { .description { font-size: 14px; } h1 { font-size: 48px; } }
  @media (max-width: 900px) { .menu { display: grid; margin-left: -6px; } .topbar { padding-inline: 24px; } .page { padding-top: 25px; } .header-cross { display: none; } }
  @media (max-width: 680px) { .topbar { min-height: 62px; padding-inline: 16px; } .breadcrumb { gap: 9px; font-size: 12px; } .busy { display: none; } .top-actions { gap: 6px; } .page { padding: 20px 16px 30px; } .intro { padding: 24px 20px; margin-bottom: 28px; } .recall-stage { display: block; margin-bottom: 26px; } .memory-visual { display: none; } .intro-copy { padding-block: 4px; } h1 { font-size: 56px; margin-bottom: 18px; } .description { font-size: 15px; } .suggestions { align-items: flex-start; flex-direction: column; gap: 5px; margin-top: 15px; } .suggestions button { font-size: 12px; } .drop-inner { padding: 35px 25px; } }
  @media (max-width: 480px) { .import { width: 36px; min-height: 36px; padding: 0; } .import span { display: none; } }
  @media (max-width: 360px) { h1 { font-size: 49px; } .intro { padding-inline: 16px; } }
</style>
