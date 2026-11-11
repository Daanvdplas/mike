// Native details provide the complete experience without JavaScript.
const evalItems = [...document.querySelectorAll('.eval-item')];

// Keep the overview compact: opening a row closes the previous row.
evalItems.forEach(item => item.addEventListener('toggle', () => {
  if (item.open) evalItems.forEach(other => { if (other !== item) other.open = false; });
}));

function revealAnchor() {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); }
  catch { return; }
  const target = document.getElementById(id);
  if (!target) return;
  let parent = target.parentElement;
  while (parent) {
    if (parent.tagName === 'DETAILS') parent.open = true;
    parent = parent.parentElement;
  }
  if (target.tagName === 'DETAILS') target.open = true;
  requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
}

window.addEventListener('hashchange', revealAnchor);
revealAnchor();
