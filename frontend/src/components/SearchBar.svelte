<script lang="ts">
  import { app } from '../lib/store.svelte';
  import Icon from './Icon.svelte';
</script>

<form class="search" class:busy={app.searching} role="search" onsubmit={(e) => { e.preventDefault(); void app.runSearch(); }}>
  <span class="lead"><Icon name="focus" size={22} stroke={1.2} /></span>
  <input
    id="search"
    type="search"
    autocomplete="off"
    spellcheck="false"
    placeholder="Descrivi ciò che cerchi…"
    aria-label="Cerca nei documenti con parole tue"
    value={app.query}
    oninput={(e) => app.setQuery(e.currentTarget.value)}
    onkeydown={(e) => {
      if (e.key === 'Escape') { app.setQuery(''); e.currentTarget.blur(); }
    }}
  />
  {#if app.query}
    <button class="icon-btn clear" type="button" aria-label="Cancella ricerca" onclick={() => { app.setQuery(''); document.getElementById('search')?.focus(); }}><Icon name="x" size={16} /></button>
  {:else}
    <kbd class="kbd shortcut">/</kbd>
  {/if}
  <button class="submit" type="submit" aria-label="Avvia ricerca" disabled={!app.query.trim()}>
    <span class="submit-label">{app.searching ? 'Cerco' : 'Ricerca'}</span><Icon name={app.searching ? 'loader' : 'arrow-right'} size={17} spin={app.searching} />
  </button>
</form>

<style>
  .search { position: relative; display: flex; align-items: center; gap: 15px; width: 100%; min-height: 70px; padding: 8px 9px 8px 19px; background: var(--bg-elev); border: 1px solid var(--border-strong); border-radius: 0; transition: border-color .2s, box-shadow .2s; }
  .search:focus-within { border-color: var(--text-dim); box-shadow: 0 0 24px var(--glow); }
  .search::before { content: ''; position: absolute; top: -1px; bottom: -1px; left: -1px; width: 2px; background: var(--text); opacity: 0; transition: opacity .2s; }
  .search:focus-within::before { opacity: 1; }
  .search::after { content: ''; position: absolute; bottom: -1px; left: 0; width: 0; height: 1px; background: var(--text); pointer-events: none; }
  .search.busy::after { animation: searching 1.2s ease-in-out infinite; }
  .lead { display: grid; color: var(--text-faint); }
  input { flex: 1; min-width: 0; height: 48px; padding: 0; border: 0; outline: none; background: transparent; font-size: 17px; letter-spacing: -.01em; }
  input::placeholder { color: var(--text-faint); }
  input::-webkit-search-cancel-button { display: none; }
  .submit { display: flex; align-items: center; justify-content: center; gap: 15px; flex: none; height: 48px; min-width: 115px; padding: 0 15px; border: 1px solid var(--accent); border-radius: 0; background: var(--accent); color: var(--accent-ink); transition: background .15s; }
  .submit-label { font: 12px var(--mono); letter-spacing: .09em; text-transform: uppercase; }
  .submit:hover:not(:disabled) { background: var(--accent-hover); }
  .submit:disabled { background: var(--bg-hover); border-color: var(--border-strong); color: var(--text-faint); opacity: 1; }
  .clear { flex: none; }
  .shortcut { border-radius: 0; }
  @keyframes searching { from { width: 0; left: 0; opacity: 0; } 20% { opacity: .7; } 70% { width: 35%; } to { left: 100%; width: 0; opacity: 0; } }
  @media (max-width: 1100px) { .submit { min-width: 95px; gap: 10px; } input { font-size: 16px; } }
  @media (max-width: 600px) { .search { min-height: 61px; padding-left: 12px; gap: 9px; } input { font-size: 16px; height: 43px; } .shortcut, .submit-label { display: none; } .submit { min-width: 39px; height: 40px; padding: 0; } .lead :global(svg) { width: 18px; height: 18px; } .clear { width: 23px; } }
</style>
