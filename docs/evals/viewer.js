// Progressive enhancement only. The complete documentation exists in the HTML.
const panels = [...document.querySelectorAll('.mode-panel')];
const controls = [...document.querySelectorAll('input[name="input-mode"]')];

function showInputMode(mode) {
  panels.forEach(panel => { panel.hidden = panel.dataset.mode !== mode; });
}

controls.forEach(control => control.addEventListener('change', () => showInputMode(control.value)));
showInputMode(controls.find(control => control.checked).value);

function revealAnchor() {
  const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (!target) return;
  let parent = target.parentElement;
  while (parent) {
    if (parent.tagName === 'DETAILS') parent.open = true;
    parent = parent.parentElement;
  }
  if (target.tagName === 'DETAILS') target.open = true;
  if (location.hash.startsWith('#bron-')) target.scrollIntoView();
  document.querySelectorAll('.sidebar nav a').forEach(link => {
    if (link.hash === location.hash) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
}

window.addEventListener('hashchange', revealAnchor);
revealAnchor();
