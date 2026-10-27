<script lang="ts">
  import type { Doc } from '../lib/types';
  import { KIND_LABEL, formatRelative, formatSize } from '../lib/format';
  import { app } from '../lib/store.svelte';
  import StatusBadge from './StatusBadge.svelte';
  import Thumb from './Thumb.svelte';
  import Icon from './Icon.svelte';
  let { doc, view }: { doc: Doc; view: 'grid' | 'list' } = $props();
  const shownTags = $derived(doc.tags.slice(0, 2));
  const extra = $derived(doc.tags.length - shownTags.length);
</script>

{#if view === 'grid'}
  <button class="card" style:--reveal-delay="{Math.min(doc.id % 6, 5) * 35}ms" onclick={() => app.openDoc(doc.id)} aria-label={`Apri ${doc.name}`} title={doc.name}>
    <Thumb {doc} />
    {#if doc.status !== 'indexed'}<span class="status"><StatusBadge {doc} /></span>{/if}
    <span class="body"><span class="name">{doc.name}</span><span class="meta">{formatSize(doc.size)}<span>·</span>{formatRelative(doc.createdAt)}</span><span class="bottom"><span class="tags">{#each shownTags as tag}<span class="chip">{tag}</span>{/each}{#if extra > 0}<span class="extra">+{extra}</span>{/if}</span><span class="open"><Icon name="arrow-up-right" size={13} /></span></span></span>
    {#if doc.status === 'processing'}<span class="bar"><span style:width="{Math.round(doc.progress * 100)}%"></span></span>{/if}
  </button>
{:else}
  <button class="row" onclick={() => app.openDoc(doc.id)} aria-label={`Apri ${doc.name}`} title={doc.name}>
    <span class="identity"><Thumb {doc} compact /><span class="info"><span class="name">{doc.name}</span><span class="row-tags">{doc.tags.join(' · ')}</span></span></span>
    <span class="cell hide-sm">{KIND_LABEL[doc.kind]}</span><span class="cell hide-sm">{formatSize(doc.size)}</span><span class="cell hide-sm">{formatRelative(doc.createdAt)}</span><span class="cell"><StatusBadge {doc} /></span>
  </button>
{/if}

<style>
  button { text-align: left; transition: background .15s, border-color .15s; }
  .card { position: relative; display: block; width: 100%; padding: 0; overflow: hidden; border: 1px solid var(--border); border-radius: 1px; background: var(--bg-elev); animation: rise .35s both; animation-delay: var(--reveal-delay, 0ms); }
  .card:hover { border-color: var(--text-faint); }
  .body { display: flex; flex-direction: column; gap: 7px; padding: 13px 14px 12px; }
  .name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 500; letter-spacing: -.01em; }
  .meta { display: flex; align-items: center; gap: 7px; color: var(--text-faint); font-size: 12px; }
  .meta > span { color: var(--border-strong); }
  .bottom { display: flex; align-items: center; justify-content: space-between; gap: 7px; min-height: 23px; margin-top: 3px; }
  .tags { display: flex; align-items: center; gap: 5px; min-width: 0; overflow: hidden; }
  .extra { color: var(--text-faint); font: 11px var(--mono); }
  .open { display: flex; align-items: center; gap: 8px; color: var(--text-faint); }
  .status { position: absolute; left: 9px; top: 9px; }
  .bar { display: block; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: var(--border); }
  .bar > span { display: block; height: 100%; background: var(--text-dim); transition: width .4s; }
  .row { display: grid; grid-template-columns: minmax(0, 1fr) 70px 80px 96px 128px; align-items: center; gap: 14px; width: 100%; padding: 13px 12px; border: 0; border-bottom: 1px solid var(--border); background: transparent; }
  .row:hover { background: var(--bg-elev); }
  .identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .info { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .row-tags { color: var(--text-faint); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cell { color: var(--text-dim); font-size: 12px; }
  @media (max-width: 760px) { .row { grid-template-columns: minmax(0, 1fr) 110px; gap: 10px; } .hide-sm { display: none; } }
</style>
