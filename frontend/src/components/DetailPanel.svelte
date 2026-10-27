<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from '../lib/store.svelte';
  import { KIND_LABEL, formatDate, formatSize } from '../lib/format';
  import { queryTerms, renderMarkdown } from '../lib/text';
  import Highlight from './Highlight.svelte';
  import Icon from './Icon.svelte';
  import StatusBadge from './StatusBadge.svelte';
  import TagEditor from './TagEditor.svelte';

  const d = $derived(app.detail);
  const terms = $derived(queryTerms(app.query));
  const fullText = $derived(d ? d.chunks.map((chunk) => chunk.text).join('\n\n') : '');
  const sources: Record<string, string> = { text: 'Testo', ocr: 'Testo riconosciuto', visual: 'Descrizione immagine' };
  let confirming = $state(false);
  let tab = $state<'preview' | 'passages'>('preview');
  let dialog: HTMLDialogElement;

  onMount(() => {
    dialog.showModal();
    return () => dialog.close();
  });

  function backdropClick(event: MouseEvent) {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) app.closeDoc();
  }

  function tabKey(event: KeyboardEvent) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    tab = event.key === 'Home' ? 'preview' : event.key === 'End' ? 'passages' : tab === 'preview' ? 'passages' : 'preview';
    document.getElementById(`${tab}-tab`)?.focus();
  }
</script>

<dialog bind:this={dialog} aria-labelledby="document-title" onclick={backdropClick} onclose={() => app.closeDoc()} oncancel={(event) => { event.preventDefault(); app.closeDoc(); }}>
  <header><div class="heading"><span class="file-icon"><Icon name={d?.kind === 'image' ? 'image' : 'file-text'} size={20} stroke={1.4} /></span><div><h2 id="document-title">{d?.name ?? 'Caricamento documento…'}</h2></div></div><button class="icon-btn close" aria-label="Chiudi documento" onclick={() => app.closeDoc()}><Icon name="x" size={18} /></button></header>
  {#if !d}
    <div class="loading"><Icon name="loader" size={25} spin /><span>Un momento…</span></div>
  {:else}
    <div class="body">
      <div class="reader">
        <div class="tabs" role="tablist" aria-label="Contenuto documento"><button id="preview-tab" role="tab" aria-selected={tab === 'preview'} aria-controls="document-content" tabindex={tab === 'preview' ? 0 : -1} class:active={tab === 'preview'} onkeydown={tabKey} onclick={() => (tab = 'preview')}>Anteprima</button><button id="passages-tab" role="tab" aria-selected={tab === 'passages'} aria-controls="document-content" tabindex={tab === 'passages' ? 0 : -1} class:active={tab === 'passages'} onkeydown={tabKey} onclick={() => (tab = 'passages')}>Passaggi <span>{d.chunks.length}</span></button></div>
        <div id="document-content" class="reader-content" role="tabpanel" aria-labelledby={tab === 'preview' ? 'preview-tab' : 'passages-tab'} tabindex="0">
          {#if tab === 'passages'}
            <div class="passages">{#each d.chunks as chunk (chunk.id)}<article class="passage"><span class="passage-meta">{String(chunk.index + 1).padStart(2, '0')} <span>/{chunk.page ? ` Pagina ${chunk.page} ·` : ''} {sources[chunk.source]}</span></span><p><Highlight text={chunk.text} {terms} /></p></article>{:else}<p class="no-preview">I passaggi saranno disponibili al termine dell’elaborazione.</p>{/each}</div>
          {:else if d.kind === 'image' && d.fileUrl}
            <div class="image-preview"><img src={d.fileUrl} alt={`Anteprima di ${d.name}`} /></div>
          {:else if d.kind === 'pdf' && d.fileUrl}
            <iframe src={d.fileUrl} title={`Anteprima di ${d.name}`}></iframe>
          {:else if d.chunks.length}
            <article class="paper">
              {#if d.kind === 'markdown'}<div class="markdown">{@html renderMarkdown(fullText)}</div>{:else}<h3>{d.name.replace(/\.[^.]+$/, '')}</h3>{#each d.chunks as chunk (chunk.id)}<div class="text-block">{#if chunk.page}<span class="page-number">Pagina {chunk.page}</span>{/if}<p><Highlight text={chunk.text} {terms} /></p></div>{/each}{/if}
            </article>
          {:else}
            <div class="no-preview"><Icon name="file" size={32} stroke={1.2} /><h3>{d.status === 'error' ? 'Il documento richiede attenzione.' : 'Stiamo preparando il documento.'}</h3><p>{d.status === 'error' ? 'Trovi i dettagli nella sezione sullo stato del file.' : 'L’anteprima sarà disponibile al termine dell’elaborazione.'}</p></div>
          {/if}
        </div>
      </div>
      <aside class="inspector" aria-label="Informazioni documento">
        <section><h3>Stato del documento</h3><StatusBadge doc={d} />{#if d.status === 'processing'}<div class="progress"><span style:width="{Math.round(d.progress * 100)}%"></span></div>{/if}{#if d.error}<p class="error-message">{d.error}</p>{/if}</section>
        <section><h3>Informazioni</h3><dl><div><dt>Formato</dt><dd>{KIND_LABEL[d.kind]}</dd></div><div><dt>Dimensione</dt><dd>{formatSize(d.size)}</dd></div>{#if d.pages}<div><dt>Pagine</dt><dd>{d.pages}</dd></div>{/if}<div><dt>Passaggi</dt><dd>{d.chunkCount}</dd></div><div class="date"><dt>Aggiunto</dt><dd>{formatDate(d.createdAt)}</dd></div></dl></section>
        <section><h3>Etichette</h3><TagEditor tags={d.tags} suggestions={app.tagList.map((tag) => tag.name)} onchange={(tags) => app.setTags(d.id, tags)} /></section>
        <div class="inspector-actions">{#if d.fileUrl}<a class="btn" href={d.fileUrl} target="_blank" rel="noopener"><Icon name="external" size={14} /> Apri originale</a>{/if}{#if confirming}<div class="confirm"><p>Eliminare questo documento dall’archivio?</p><div><button class="btn" onclick={() => (confirming = false)}>Annulla</button><button class="btn btn-primary" onclick={() => app.removeDoc(d.id)}>Elimina</button></div></div>{:else}<button class="delete" onclick={() => (confirming = true)}><Icon name="trash" size={13} /> Elimina documento</button>{/if}</div>
      </aside>
    </div>
  {/if}
</dialog>

<style>
  dialog { width: min(1060px, calc(100vw - 72px)); height: min(790px, calc(100dvh - 72px)); max-width: none; max-height: none; padding: 0; border: 1px solid var(--border-strong); border-radius: 2px; background: var(--bg-elev); color: var(--text); box-shadow: var(--shadow); overflow: hidden; }
  dialog[open] { display: flex; flex-direction: column; animation: reader-focus .25s cubic-bezier(.2,.7,.2,1) both; }
  dialog::backdrop { background: var(--scrim); backdrop-filter: blur(5px); }
  header { display: flex; align-items: center; justify-content: space-between; gap: 20px; flex: none; min-height: 83px; padding: 18px 25px; border-bottom: 1px solid var(--border); }
  .heading { display: flex; align-items: center; gap: 14px; min-width: 0; }
  .heading > div { min-width: 0; }
  .file-icon { display: grid; place-items: center; flex: none; width: 36px; height: 41px; border: 1px solid var(--border-strong); border-radius: 1px; color: var(--text-dim); }
  h2 { margin-top: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 17px; font-weight: 500; letter-spacing: -.02em; }
  .close { flex: none; }
  .body { display: flex; flex: 1; min-height: 0; }
  .reader { flex: 1; min-width: 0; display: flex; flex-direction: column; background: var(--bg); }
  .tabs { display: flex; align-items: center; gap: 23px; flex: none; height: 48px; padding: 0 27px; border-bottom: 1px solid var(--border); }
  .tabs button { display: flex; align-items: center; gap: 7px; height: 100%; padding: 0; border: 0; border-bottom: 1px solid transparent; background: transparent; color: var(--text-faint); font-size: 13px; }
  .tabs button.active { border-bottom-color: var(--text); color: var(--text); }
  .tabs span { color: var(--text-faint); font: 12px var(--mono); }
  .reader-content { flex: 1; min-height: 0; padding: 30px; overflow-y: auto; overscroll-behavior: contain; }
  .paper { min-height: 100%; padding: 32px 35px; border: 1px solid var(--border); background: var(--paper); border-radius: 3px; font-size: 15px; line-height: 1.85; }
  .paper h3 { margin-bottom: 22px; font-size: 24px; font-weight: 500; line-height: 1.5; letter-spacing: -.035em; }
  .text-block { margin-top: 20px; }
  .text-block p { white-space: pre-wrap; color: var(--text-dim); }
  .page-number { display: block; margin-bottom: 7px; font: 12px var(--mono); letter-spacing: .05em; text-transform: uppercase; color: var(--text-faint); }
  .markdown :global(h1) { font-size: 28px; line-height: 1.3; font-weight: 500; letter-spacing: -.04em; margin-bottom: 22px; }
  .markdown :global(h2) { font-size: 19px; font-weight: 500; margin: 24px 0 13px; }
  .markdown :global(h3) { font-size: 17px; margin: 20px 0 10px; }
  .markdown :global(p) { margin-bottom: 13px; color: var(--text-dim); }
  .markdown :global(ul), .markdown :global(ol) { padding-left: 18px; color: var(--text-dim); }
  .markdown :global(code) { padding: 2px 5px; border-radius: 3px; background: var(--bg-hover); font: 12px var(--mono); }
  .markdown :global(pre) { overflow-x: auto; padding: 12px; background: var(--bg-hover); }
  .image-preview { display: flex; align-items: center; justify-content: center; min-height: 100%; }
  .image-preview img { display: block; max-width: 100%; max-height: 530px; object-fit: contain; border-radius: 4px; }
  iframe { display: block; width: 100%; height: 100%; min-height: 400px; border: 0; }
  .passage { padding: 20px; margin-bottom: 14px; border: 1px solid var(--border); border-radius: 1px; background: var(--bg-elev); }
  .passage-meta { display: block; margin-bottom: 12px; font: 12px var(--mono); }
  .passage-meta > span { color: var(--text-faint); }
  .passage p { white-space: pre-wrap; font-size: 15px; line-height: 1.8; color: var(--text-dim); }
  .inspector { display: flex; flex-direction: column; gap: 25px; width: 270px; flex: none; padding: 24px; border-left: 1px solid var(--border); overflow-y: auto; }
  section h3 { margin-bottom: 13px; font-size: 12px; font-weight: 500; color: var(--text-faint); }
  dl { display: flex; flex-direction: column; gap: 14px; margin: 0; font-size: 13px; }
  dl > div { display: flex; justify-content: space-between; gap: 10px; }
  dt { color: var(--text-faint); }
  dd { margin: 0; text-align: right; }
  dl .date { flex-direction: column; gap: 7px; }
  dl .date dd { text-align: left; }
  .progress { height: 2px; margin-top: 14px; background: var(--border); }
  .progress > span { display: block; height: 100%; background: var(--text-dim); transition: width .3s; }
  .error-message { margin-top: 12px; padding: 11px; border: 1px dashed var(--border-strong); border-radius: 5px; font-size: 13px; line-height: 1.7; }
  .inspector-actions { display: flex; flex-direction: column; gap: 14px; margin-top: auto; padding-top: 20px; }
  .inspector-actions > .btn { font-size: 13px; }
  .delete { display: flex; align-items: center; justify-content: center; gap: 7px; padding: 5px; border: 0; background: transparent; color: var(--text-faint); font-size: 12px; }
  .delete:hover { color: var(--text); }
  .confirm { padding: 12px; border: 1px dashed var(--border-strong); border-radius: 1px; }
  .confirm p { font-size: 13px; margin-bottom: 12px; }
  .confirm > div { display: flex; gap: 7px; }
  .confirm .btn { flex: 1; padding: 0 7px; font-size: 12px; }
  .loading, .no-preview { display: flex; flex: 1; align-items: center; justify-content: center; flex-direction: column; gap: 16px; min-height: 240px; color: var(--text-faint); font-size: 14px; text-align: center; }
  .no-preview h3 { color: var(--text); font-size: 17px; font-weight: 450; }
  .no-preview p { max-width: 270px; font-size: 14px; line-height: 1.8; }
  @keyframes reader-focus { from { opacity: 0; transform: translateY(6px) scale(.99); } to { opacity: 1; transform: none; } }
  @media (max-width: 760px) {
    dialog { width: calc(100vw - 24px); height: calc(100dvh - 24px); border-radius: 1px; }
    header { min-height: 70px; padding: 14px 17px; gap: 8px; }
    h2 { font-size: 12px; }
    .body { flex-direction: column; overflow-y: auto; }
    .reader { flex: none; min-height: 330px; }
    .reader-content { flex: none; max-height: 460px; padding: 18px; }
    .paper { padding: 23px; }
    .inspector { width: 100%; overflow: visible; border-left: 0; border-top: 1px solid var(--border); padding: 22px; gap: 22px; }
    .inspector-actions { margin-top: 0; }
    .tabs { padding-inline: 22px; }
  }
</style>
