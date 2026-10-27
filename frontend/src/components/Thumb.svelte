<script lang="ts">
  import type { Doc } from '../lib/types';
  import { KIND_SHORT } from '../lib/format';
  import Icon from './Icon.svelte';
  let { doc, compact = false }: { doc: Doc; compact?: boolean } = $props();
  const title = $derived(doc.name.replace(/\.[^.]+$/, ''));
</script>

<span class="thumb" class:compact class:image={doc.kind === 'image'} class:markdown={doc.kind === 'markdown'}>
  {#if doc.kind === 'image' && doc.thumbnailUrl}
    <img src={doc.thumbnailUrl} alt="" loading="lazy" />
  {:else if compact}
    <Icon name="file-text" size={19} stroke={1.3} />
  {:else}
    <span class="paper">
      <span class="paper-title">{title}</span>
      <span class="paper-rule"></span>
      <span class="lines">{doc.excerpt || 'Il documento è in preparazione.'}</span>
      <span class="paper-lines" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
  {/if}
  {#if !compact}<span class="kind">{KIND_SHORT[doc.kind]}</span>{/if}
</span>

<style>
  .thumb { position: relative; display: block; height: 140px; overflow: hidden; background: var(--bg-elev-2); border-bottom: 1px solid var(--border); }
  .thumb.compact { display: grid; place-items: center; width: 34px; height: 40px; border: 1px solid var(--border-strong); border-radius: 0; color: var(--text-dim); flex: none; background: var(--bg-elev); }
  img { display: block; width: 100%; height: 100%; object-fit: cover; filter: grayscale(1); }
  .image:not(.compact) img { object-position: center 55%; }
  .paper { position: absolute; inset: 16px 17px -8px; display: flex; flex-direction: column; gap: 10px; padding: 15px 16px; background: var(--paper); border: 1px solid var(--border-strong); border-radius: 0; overflow: hidden; transform: none; transition: transform .25s; }
  .markdown .paper { transform: none; }
  :global(.card:hover) .paper { transform: translateY(-3px); }
  .paper-title { display: -webkit-box; flex: none; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-dim); font: 500 12px/1.5 var(--mono); letter-spacing: -.02em; }
  .paper-rule { flex: none; height: 1px; background: var(--border-strong); }
  .lines { display: block; flex: 1; min-height: 0; overflow: hidden; color: var(--paper-text); font: 10px/1.8 var(--mono); word-break: break-word; mask-image: linear-gradient(#000 45%, transparent); }
  .paper-lines { display: grid; gap: 4px; position: absolute; bottom: 15px; left: 16px; right: 16px; opacity: .6; }
  .paper-lines i { height: 2px; background: var(--border-strong); }
  .paper-lines i:last-child { width: 65%; }
  .kind { position: absolute; right: 9px; bottom: 9px; padding: 2px 5px; border: 1px solid var(--border-strong); border-radius: 0; background: var(--bg-elev); color: var(--text-dim); font: 11px var(--mono); }
  .thumb::before, .thumb::after { content: ''; position: absolute; z-index: 2; width: 8px; height: 8px; border: solid var(--text-faint); pointer-events: none; opacity: .5; }
  .thumb::before { top: 7px; left: 7px; border-width: 1px 0 0 1px; }
  .thumb::after { bottom: 7px; right: 7px; border-width: 0 1px 1px 0; }
  .thumb.compact::before, .thumb.compact::after { display: none; }
</style>
