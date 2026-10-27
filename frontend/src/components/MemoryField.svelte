<script lang="ts">
  import { app } from '../lib/store.svelte';
  import Icon from './Icon.svelte';

  let chosen = $state<number | null>(null);
  const memories = $derived.by(() => {
    const images = app.docs.filter(doc => doc.kind === 'image' && doc.thumbnailUrl);
    images.sort((a, b) => {
      const aPhoto = /\.jpe?g$/i.test(a.name);
      const bPhoto = /\.jpe?g$/i.test(b.name);
      return Number(bPhoto) - Number(aPhoto) || a.createdAt.localeCompare(b.createdAt);
    });
    return (images.length ? images : app.docs.filter(doc => doc.excerpt)).slice(0, 4);
  });
  const selected = $derived(memories.find(doc => doc.id === chosen) ?? memories[0]);
  const position = $derived(Math.max(0, memories.findIndex(doc => doc.id === selected?.id)));
  const date = (iso: string) => new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' });
</script>

<div class="memory-field" aria-label="Esplora le immagini del tuo archivio">
  <div class="field-top"><span><span class="signal"></span> Immagini</span><span>{selected ? `AGGIUNTO ${date(selected.createdAt)}` : 'NESSUN DOCUMENTO'}</span></div>
  <div class="optical-field">
    <div class="orbit orbit-one" aria-hidden="true"></div>
    <div class="orbit orbit-two" aria-hidden="true"></div>
    <span class="axis horizontal" aria-hidden="true"></span>
    <span class="axis vertical" aria-hidden="true"></span>
    <div class="ruler" aria-hidden="true">{#each Array(21) as _, i}<i class:major={i % 5 === 0}></i>{/each}</div>
    <div class="capture">
      <span class="corner top-left" aria-hidden="true"></span><span class="corner top-right" aria-hidden="true"></span><span class="corner bottom-left" aria-hidden="true"></span><span class="corner bottom-right" aria-hidden="true"></span>
      {#if selected}
        {#key selected.id}
          <button class="memory-screen" onclick={() => app.openDoc(selected.id)} aria-label={`Apri ${selected.name}`}>
            {#if selected.thumbnailUrl}<img src={selected.thumbnailUrl} alt={selected.name} />{:else}<span class="text-memory">{selected.excerpt}</span>{/if}
            <span class="screen-grain" aria-hidden="true"></span>
            <span class="scan" aria-hidden="true"></span>
            <span class="screen-reticle" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
            <span class="screen-open"><Icon name="external" size={13} /> APRI</span>
          </button>
        {/key}
      {:else}
        <div class="memory-screen empty"><Icon name="focus" size={64} stroke={.7} /><span>Nessuna anteprima</span></div>
      {/if}
    </div>
  </div>
  <div class="field-bottom">
    <span class="memory-name">{selected?.name ?? 'Nessun documento'}</span>
    <span class="position">{String(memories.length ? position + 1 : 0).padStart(2, '0')} <span>/ {String(memories.length).padStart(2, '0')}</span></span>
  </div>
  {#if memories.length > 1}
    <div class="memory-track" aria-label="Seleziona un’immagine dell’archivio">
      {#each memories as memory (memory.id)}
        <button class:active={selected?.id === memory.id} aria-pressed={selected?.id === memory.id} aria-label={`Richiama ${memory.name}`} onclick={() => (chosen = memory.id)}>
          {#if memory.thumbnailUrl}<img src={memory.thumbnailUrl} alt="" />{:else}<Icon name="file-text" size={14} />{/if}
          <span class="track-line"></span>
        </button>
      {/each}
      <span class="track-end" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
    </div>
  {/if}
</div>

<style>
  .memory-field { position: relative; width: 100%; max-width: 455px; margin-left: auto; color: var(--text-dim); }
  .field-top, .field-bottom { display: flex; align-items: center; justify-content: space-between; gap: 12px; font: 11px/1.5 var(--mono); letter-spacing: .03em; }
  .field-top { padding: 0 9px 10px; color: var(--text-faint); }
  .field-top > span:first-child { display: flex; align-items: center; gap: 7px; }
  .signal { width: 4px; height: 4px; border-radius: 50%; background: var(--text-dim); box-shadow: 0 0 8px var(--glow); }
  .optical-field { position: relative; display: grid; place-items: center; height: 245px; overflow: hidden; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .orbit { position: absolute; width: 340px; height: 340px; border: 1px solid var(--border); border-radius: 50%; pointer-events: none; }
  .orbit-one { width: 310px; height: 310px; border-style: dashed; opacity: .65; animation: orbit 100s linear infinite; }
  .orbit-two { width: 378px; height: 378px; opacity: .45; }
  .axis { position: absolute; background: var(--border); pointer-events: none; }
  .horizontal { height: 1px; width: 100%; top: 50%; }
  .vertical { width: 1px; height: 100%; left: 50%; }
  .ruler { position: absolute; inset: 15px auto 15px 0; width: 9px; display: flex; flex-direction: column; justify-content: space-between; }
  .ruler i { display: block; width: 3px; height: 1px; background: var(--border-strong); }
  .ruler i.major { width: 8px; background: var(--text-faint); }
  .capture { position: relative; width: 76%; height: 185px; padding: 7px; transform: perspective(1000px) rotateY(-8deg) rotateX(3deg); transition: transform .7s cubic-bezier(.2,.7,.2,1); }
  .memory-field:hover .capture, .memory-field:focus-within .capture { transform: perspective(1000px) rotateY(0) rotateX(0); }
  .corner { position: absolute; width: 16px; height: 16px; border-color: var(--text-dim); border-style: solid; pointer-events: none; }
  .top-left { top: 0; left: 0; border-width: 1px 0 0 1px; }
  .top-right { top: 0; right: 0; border-width: 1px 1px 0 0; }
  .bottom-left { bottom: 0; left: 0; border-width: 0 0 1px 1px; }
  .bottom-right { bottom: 0; right: 0; border-width: 0 1px 1px 0; }
  .memory-screen { position: relative; display: block; width: 100%; height: 100%; padding: 0; overflow: hidden; border: 1px solid #565656; border-radius: 0; background: #151515; color: #eee; isolation: isolate; }
  .memory-screen img { display: block; width: 100%; height: 100%; object-fit: cover; filter: grayscale(1) contrast(1.12) brightness(.8); animation: resolve 1.4s cubic-bezier(.2,.7,.2,1) both; }
  .screen-grain { position: absolute; z-index: 1; inset: 0; pointer-events: none; opacity: .26; background-image: repeating-linear-gradient(0deg, transparent 0, transparent 2px, #000 3px, transparent 4px); }
  .scan { position: absolute; z-index: 2; left: 0; right: 0; top: -5%; height: 1px; background: #ffffff9c; box-shadow: 0 0 16px 4px #ffffff1c; animation: scan 1.5s ease-out both; pointer-events: none; }
  .screen-reticle { position: absolute; z-index: 2; top: 50%; left: 50%; width: 68px; height: 48px; transform: translate(-50%, -50%); opacity: .75; transition: width .5s, height .5s; }
  .memory-screen:hover .screen-reticle { width: 95px; height: 65px; }
  .screen-reticle i { position: absolute; width: 9px; height: 9px; border: solid #fff; }
  .screen-reticle i:nth-child(1) { top: 0; left: 0; border-width: 1px 0 0 1px; }
  .screen-reticle i:nth-child(2) { top: 0; right: 0; border-width: 1px 1px 0 0; }
  .screen-reticle i:nth-child(3) { bottom: 0; left: 0; border-width: 0 0 1px 1px; }
  .screen-reticle i:nth-child(4) { bottom: 0; right: 0; border-width: 0 1px 1px 0; }
  .screen-open { position: absolute; z-index: 3; left: 11px; bottom: 11px; display: flex; align-items: center; gap: 6px; padding: 5px 7px; background: #0009; color: #ddd; font: 11px var(--mono); letter-spacing: .06em; opacity: 0; transform: translateY(3px); transition: opacity .2s, transform .2s; }
  .memory-screen:hover .screen-open, .memory-screen:focus-visible .screen-open { opacity: 1; transform: none; }
  .field-bottom { padding: 12px 9px 0; }
  .memory-name { max-width: 80%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: 0; font-size: 12px; }
  .position { white-space: nowrap; color: var(--text); }
  .position > span { color: var(--text-faint); }
  .memory-track { display: flex; align-items: center; gap: 7px; padding: 11px 9px 0; }
  .memory-track button { position: relative; display: grid; place-items: center; width: 44px; height: 32px; padding: 0; border: 1px solid var(--border-strong); border-radius: 0; background: var(--bg-elev-2); color: var(--text-faint); opacity: .5; transition: opacity .2s, border-color .2s; }
  .memory-track button.active, .memory-track button:hover { border-color: var(--text-dim); opacity: 1; }
  .memory-track img { display: block; width: 100%; height: 100%; object-fit: cover; filter: grayscale(1); }
  .track-line { position: absolute; left: 0; right: 0; bottom: -5px; height: 1px; background: var(--text); opacity: 0; }
  .active .track-line { opacity: 1; }
  .track-end { display: flex; align-items: center; justify-content: space-between; flex: 1; margin-left: 7px; height: 1px; background: var(--border); }
  .track-end i { width: 1px; height: 4px; background: var(--border-strong); }
  .text-memory { display: block; padding: 25px; font: 13px/1.8 var(--mono); text-align: left; }
  .empty { display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 15px; color: #aaa; }
  .empty > span { font: 12px var(--mono); }
  @keyframes scan { from { top: -5%; opacity: 0; } 15% { opacity: .8; } to { top: 110%; opacity: 0; } }
  @keyframes resolve { from { opacity: .35; transform: scale(1.08); filter: grayscale(1) contrast(1.5) brightness(1.4) blur(3px); } to { opacity: 1; transform: scale(1); filter: grayscale(1) contrast(1.12) brightness(.8); } }
  @keyframes orbit { to { transform: rotate(360deg); } }
  @media (max-width: 1100px) { .optical-field { height: 220px; } .capture { width: 83%; height: 161px; } }
  @media (prefers-reduced-motion: reduce) { .orbit, .scan, .memory-screen img { animation: none; } .capture { transform: none; } }
</style>
