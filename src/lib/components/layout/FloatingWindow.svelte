<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  let width = 400;
  let height = 500;
  let top = 100;
  let left = 100;

  let isResizing = false;
  let resizeDirection = '';
  let startX = 0;
  let startY = 0;
  let startWidth = 0;
  let startHeight = 0;
  let startTop = 0;
  let startLeft = 0;

  function startResize(event: MouseEvent, direction: string) {
    event.preventDefault();
    isResizing = true;
    resizeDirection = direction;
    startX = event.clientX;
    startY = event.clientY;
    startWidth = width;
    startHeight = height;
    startTop = top;
    startLeft = left;

    window.addEventListener('mousemove', resize);
    window.addEventListener('mouseup', stopResize);
  }

  function resize(event: MouseEvent) {
    if (!isResizing) return;

    const dx = event.clientX - startX;
    const dy = event.clientY - startY;

    if (resizeDirection.includes('right')) {
      width = Math.max(200, startWidth + dx);
    }
    if (resizeDirection.includes('left')) {
      width = Math.max(200, startWidth - dx);
      left = startLeft + dx;
    }
    if (resizeDirection.includes('bottom')) {
      height = Math.max(200, startHeight + dy);
    }
    if (resizeDirection.includes('top')) {
      height = Math.max(200, startHeight - dy);
      top = startTop + dy;
    }
  }

  function stopResize() {
    isResizing = false;
    window.removeEventListener('mousemove', resize);
    window.removeEventListener('mouseup', stopResize);
  }
</script>

<div class="window" style="width: {width}px; height: {height}px; top: {top}px; left: {left}px;">
  <slot />

  <!-- 8 Resize handles -->
  <div class="resize-handle top-left"    on:mousedown={(e) => startResize(e, 'top left')}></div>
  <div class="resize-handle top"          on:mousedown={(e) => startResize(e, 'top')}></div>
  <div class="resize-handle top-right"    on:mousedown={(e) => startResize(e, 'top right')}></div>
  <div class="resize-handle right"        on:mousedown={(e) => startResize(e, 'right')}></div>
  <div class="resize-handle bottom-right" on:mousedown={(e) => startResize(e, 'bottom right')}></div>
  <div class="resize-handle bottom"       on:mousedown={(e) => startResize(e, 'bottom')}></div>
  <div class="resize-handle bottom-left"  on:mousedown={(e) => startResize(e, 'bottom left')}></div>
  <div class="resize-handle left"         on:mousedown={(e) => startResize(e, 'left')}></div>
</div>

<style>
  .window {
    position: fixed;
    background: white;
    border: 1px solid #ccc;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    overflow: hidden;
    z-index: 9999;
  }

  .resize-handle {
    position: absolute;
    background: transparent;
  }

  /* Side handles */
  .resize-handle.top,
  .resize-handle.bottom {
    left: 0;
    right: 0;
    height: 8px;
    cursor: ns-resize;
  }
  .resize-handle.top { top: -4px; }
  .resize-handle.bottom { bottom: -4px; }

  .resize-handle.left,
  .resize-handle.right {
    top: 0;
    bottom: 0;
    width: 8px;
    cursor: ew-resize;
  }
  .resize-handle.left { left: -4px; }
  .resize-handle.right { right: -4px; }

  /* Corner handles */
  .resize-handle.top-left,
  .resize-handle.top-right,
  .resize-handle.bottom-left,
  .resize-handle.bottom-right {
    width: 12px;
    height: 12px;
    background: #666;
    border-radius: 50%;
    z-index: 10000;
  }

  .resize-handle.top-left {
    top: -6px;
    left: -6px;
    cursor: nwse-resize;
  }
  .resize-handle.top-right {
    top: -6px;
    right: -6px;
    cursor: nesw-resize;
  }
  .resize-handle.bottom-left {
    bottom: -6px;
    left: -6px;
    cursor: nesw-resize;
  }
  .resize-handle.bottom-right {
    bottom: -6px;
    right: -6px;
    cursor: nwse-resize;
  }
</style>
