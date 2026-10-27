<script lang="ts">
  let { size = 30 }: { size?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
  <path d="M11 3H5a2 2 0 0 0-2 2v6M21 3h6a2 2 0 0 1 2 2v6M29 21v6a2 2 0 0 1-2 2h-6M11 29H5a2 2 0 0 1-2-2v-6" stroke="currentColor" stroke-width="1.6" />
  <circle class="lens" cx="16" cy="16" r="7" stroke="currentColor" stroke-width="1.2" stroke-dasharray="18 4" />
  <circle cx="16" cy="16" r="2.5" fill="currentColor" />
</svg>

<style>
  .lens { transform-origin: 16px 16px; animation: lens-turn 40s linear infinite; }
  @keyframes lens-turn { to { transform: rotate(360deg); } }
</style>
