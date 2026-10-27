<script lang="ts">
  import { onMount } from 'svelte';
  import { app, apiMode } from '../lib/store.svelte';
  import Icon from './Icon.svelte';
  import Logo from './Logo.svelte';

  let mobile = $state(false);
  onMount(() => {
    const media = matchMedia('(max-width: 900px)');
    mobile = media.matches;
    const change = () => { mobile = media.matches; };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  });

  function navigate(view: 'search' | 'archive') {
    app.navigate(view);
    app.sidebarOpen = false;
    if (view === 'search') requestAnimationFrame(() => document.getElementById('search')?.focus());
  }
</script>

{#if app.sidebarOpen}
  <button class="scrim" aria-label="Chiudi menu" onclick={() => (app.sidebarOpen = false)}></button>
{/if}

<aside class:open={app.sidebarOpen} inert={mobile && !app.sidebarOpen} aria-label="Barra laterale">
  <button class="brand" aria-label="Esper, torna alla ricerca" onclick={() => navigate('search')}>
    <Logo size={29} />
    <span>ESPER</span>
  </button>

  <nav aria-label="Navigazione principale">
    <button class="nav" class:active={app.workspace === 'search'} onclick={() => navigate('search')}><Icon name="search" size={17} /> Ricerca <kbd>/</kbd></button>
    <button class="nav" class:active={app.workspace === 'archive' && app.kindFilter === 'all' && !app.activeTags.length} onclick={() => navigate('archive')}><Icon name="library" size={17} /> Tutti i documenti <span class="count">{app.docs.length}</span></button>
  </nav>

  <div class="sections">
    <section>
      <h2>Esplora</h2>
      <button class="nav" class:active={app.kindFilter === 'pdf'} onclick={() => { app.setKind('pdf'); app.sidebarOpen = false; }}><Icon name="file" size={16} /> PDF <span class="count">{app.docs.filter(d => d.kind === 'pdf').length}</span></button>
      <button class="nav" class:active={app.kindFilter === 'image'} onclick={() => { app.setKind('image'); app.sidebarOpen = false; }}><Icon name="image" size={16} /> Immagini <span class="count">{app.docs.filter(d => d.kind === 'image').length}</span></button>
      <button class="nav" class:active={app.kindFilter === 'notes'} onclick={() => { app.setKind('notes'); app.sidebarOpen = false; }}><Icon name="file-text" size={16} /> Note e testi <span class="count">{app.docs.filter(d => d.kind === 'text' || d.kind === 'markdown').length}</span></button>
    </section>
    <section class="tag-section">
      <h2>Etichette <span>{app.tagList.length}</span></h2>
      {#each app.tagList as tag (tag.name)}
        <button class="nav tag" class:active={app.activeTags.includes(tag.name)} aria-pressed={app.activeTags.includes(tag.name)} onclick={() => { app.toggleTag(tag.name); app.sidebarOpen = false; }}>
          <span class="hash">#</span><span class="tag-name">{tag.name}</span><span class="count">{tag.count}</span>
        </button>
      {:else}
        <p class="empty-tags">Le tue etichette appariranno qui.</p>
      {/each}
    </section>
  </div>

  <footer>
    {#if apiMode === 'mock'}
      <div class="mode"><span class="mode-dot"></span> Dati demo</div>
    {:else}
      <div class="mode"><Icon name="lock" size={12} /> Archivio locale</div>
    {/if}
    <div class="bottom"><span class="local"><Icon name="lock" size={12} /> Privato</span>
      <button class="icon-btn" aria-label={app.theme === 'dark' ? 'Attiva tema chiaro' : 'Attiva tema scuro'} title={app.theme === 'dark' ? 'Tema chiaro' : 'Tema scuro'} onclick={() => app.toggleTheme()}><Icon name={app.theme === 'dark' ? 'sun' : 'moon'} size={16} /></button>
    </div>
  </footer>
</aside>

<style>
  aside { display: flex; flex-direction: column; flex: 0 0 214px; width: 214px; height: 100%; padding: 25px 14px 16px; background: var(--sidebar); border-right: 1px solid var(--border); }
  .brand { display: flex; align-items: center; gap: 13px; width: fit-content; padding: 0 8px; border: 0; background: transparent; color: var(--text); }
  .brand > span { font: 24px/1 var(--mono); letter-spacing: .13em; }
  nav { display: grid; gap: 5px; margin: 35px 0 30px; }
  .nav { position: relative; display: flex; align-items: center; gap: 10px; width: 100%; min-height: 42px; padding: 10px 9px; border: 1px solid transparent; border-radius: 0; background: transparent; color: var(--text-dim); text-align: left; font-size: 14px; transition: background .15s, color .15s; }
  .nav:hover { background: var(--bg-elev-2); color: var(--text); }
  .nav.active { background: var(--bg-hover); color: var(--text); border-color: var(--border); }
  .nav.active::before { content: ''; position: absolute; left: -1px; top: 9px; bottom: 9px; width: 2px; background: var(--text); }
  .count, kbd { margin-left: auto; color: var(--text-faint); font: 11px var(--mono); }
  kbd { border: 1px solid var(--border-strong); padding: 1px 5px; border-radius: 0; }
  .sections { flex: 1; min-height: 0; overflow-y: auto; }
  section + section { margin-top: 28px; }
  h2 { display: flex; justify-content: space-between; padding: 0 9px; margin-bottom: 11px; color: var(--text-faint); font: 11px var(--mono); letter-spacing: .14em; text-transform: uppercase; }
  h2 span { letter-spacing: 0; }
  .tag { min-height: 35px; padding-block: 8px; font-size: 13px; }
  .hash { font: 14px var(--mono); width: 16px; color: var(--text-faint); }
  .tag-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty-tags { padding: 5px 10px; font-size: 12px; color: var(--text-faint); }
  footer { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }
  .mode { display: flex; align-items: center; gap: 7px; font-size: 12px; padding: 0 8px 10px; color: var(--text-dim); }
  .mode-dot { width: 4px; height: 4px; border: 1px solid var(--text-dim); border-radius: 50%; }
  .bottom { display: flex; align-items: center; justify-content: space-between; }
  .local { display: flex; align-items: center; gap: 6px; padding-left: 8px; color: var(--text-faint); font-size: 12px; }
  .scrim { display: none; }
  @media (max-width: 900px) {
    aside { position: fixed; z-index: 40; inset: 0 auto 0 0; width: 248px; transform: translateX(-100%); transition: transform .2s; box-shadow: var(--shadow); }
    aside.open { transform: none; }
    .scrim { display: block; position: fixed; z-index: 39; inset: 0; border: 0; background: var(--scrim); animation: fade-in .15s; }
  }
</style>
