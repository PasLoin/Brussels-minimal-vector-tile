export const FALLBACK_COLOR = '#cccccc';
export const SWATCHES = ['fill', 'line', 'dot'];

const PAINT_COLOR_KEYS = [
  'fill-color', 'line-color', 'circle-color', 'fill-extrusion-color', 'icon-color', 'text-color',
];
const SWATCH_OF_TYPE = {
  fill: 'fill', 'fill-extrusion': 'fill', line: 'line', circle: 'dot', symbol: 'dot',
};
const NAMED_COLORS = new Set(['white', 'black', 'transparent']);

export function isColor(value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  const v = value.trim().toLowerCase();
  return v.startsWith('#') || v.startsWith('rgb') || v.startsWith('hsl') || NAMED_COLORS.has(v);
}

export function exprColor(expr) {
  if (isColor(expr)) return expr;
  if (!Array.isArray(expr)) return null;
  for (let i = expr.length - 1; i >= 1; i--) {
    const found = exprColor(expr[i]);
    if (found) return found;
  }
  return null;
}

const colorRank = (layer) => ['casing', 'tunnel', 'bridge']
  .map((part) => (String(layer.id).split('-').includes(part) ? 1 : 0))
  .join('');

export function paintColor(layers) {
  const sorted = [...(layers || [])].sort((a, b) => colorRank(a).localeCompare(colorRank(b)));
  for (const layer of sorted) {
    const paint = layer.paint || {};
    for (const key of PAINT_COLOR_KEYS) {
      const found = exprColor(paint[key]);
      if (found) return found;
    }
  }
  return null;
}

export function swatchType(layers) {
  const counts = { fill: 0, line: 0, dot: 0 };
  for (const layer of layers || []) {
    if (layer.type === 'symbol') continue;
    counts[SWATCH_OF_TYPE[layer.type] || 'dot'] += 1;
  }
  if (!Object.values(counts).some(Boolean)) return 'dot';
  return SWATCHES.reduce((best, k) => (counts[k] > counts[best] ? k : best), SWATCHES[0]);
}

function resolveEntry(entry, byId, inheritedColor) {
  const ids = (Array.isArray(entry.layers) ? entry.layers : []).filter((id) => byId.has(id));
  const layers = ids.map((id) => byId.get(id));
  const color = (isColor(entry.color) && entry.color) || paintColor(layers) || inheritedColor || FALLBACK_COLOR;
  const swatch = SWATCHES.includes(entry.swatch) ? entry.swatch : swatchType(layers);
  const out = { id: String(entry.id), label: String(entry.label || entry.id), color, swatch, layers: ids };
  if (Array.isArray(entry.filter) && entry.filter.length) out.filter = entry.filter;
  const colors = (Array.isArray(entry.colors) ? entry.colors : []).filter(isColor);
  if (colors.length > 1) out.colors = colors;
  return out;
}

function groupsFromMetadata(meta, byId) {
  const groups = [];
  for (const raw of meta) {
    if (!raw || raw.id == null) continue;
    const base = resolveEntry(raw, byId, null);
    const items = (Array.isArray(raw.items) ? raw.items : [])
      .filter((item) => item && item.id != null)
      .map((item) => resolveEntry(item, byId, base.color))
      .filter((item) => item.layers.length || (item.filter && base.layers.length));
    if (!base.layers.length && !items.length) continue;
    if (!isColor(raw.color) && !base.layers.length && items.length) base.color = items[0].color;
    groups.push({ ...base, visible: raw.visible !== false, items });
  }
  return groups;
}

function groupsFromSources(layers) {
  const bySource = new Map();
  for (const layer of layers) {
    if (!layer.source) continue;
    if (!bySource.has(layer.source)) bySource.set(layer.source, []);
    bySource.get(layer.source).push(layer);
  }
  return [...bySource.entries()].map(([source, group]) => ({
    id: source,
    label: source.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()),
    color: paintColor(group) || FALLBACK_COLOR,
    swatch: swatchType(group),
    visible: true,
    layers: group.map((l) => l.id),
    items: [],
  }));
}

export function legendGroups(style) {
  const layers = (style && style.layers) || [];
  const byId = new Map(layers.map((l) => [l.id, l]));
  const meta = ((style && style.metadata) || {})['brussels:legend'];
  if (Array.isArray(meta)) {
    const groups = groupsFromMetadata(meta, byId);
    if (groups.length) return groups;
  }
  return groupsFromSources(layers);
}

export function allLayerIds(group) {
  return [...group.layers, ...group.items.flatMap((item) => item.layers)];
}

export function swatchBackground(entry) {
  const colors = entry.colors || [];
  if (colors.length < 2) return entry.color;
  const step = 100 / colors.length;
  const stops = colors.map((c, i) => `${c} ${(i * step).toFixed(2)}% ${((i + 1) * step).toFixed(2)}%`);
  return `linear-gradient(170deg, ${stops.join(', ')})`;
}

function swatchEl(entry) {
  const el = document.createElement('div');
  el.className = entry.swatch === 'line' ? 'swatch' : `swatch ${entry.swatch}`;
  el.style.background = swatchBackground(entry);
  return el;
}

function rowEl(className, entry) {
  const row = document.createElement('div');
  row.className = className;
  row.setAttribute('role', 'checkbox');
  row.tabIndex = 0;
  row.dataset.id = entry.id;
  const label = document.createElement('span');
  label.textContent = entry.label;
  row.append(swatchEl(entry), label);
  return row;
}

function onActivate(el, fn) {
  el.addEventListener('click', fn);
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); }
  });
}

export function exclusionFilter(group, isItemOn) {
  const hidden = group.items.filter((item) => item.filter && !isItemOn(item.id)).map((item) => item.filter);
  if (!hidden.length) return null;
  return ['!', hidden.length === 1 ? hidden[0] : ['any', ...hidden]];
}

export function createLegend(root, groups, { onChange = () => {}, onFilter = () => {} } = {}) {
  const state = new Map();
  const owner = new Map();
  for (const group of groups) {
    const on = group.visible !== false;
    state.set(group.id, { on, items: new Map(group.items.map((i) => [i.id, on])) });
    for (const id of group.layers) owner.set(id, [group.id, null]);
    for (const item of group.items) for (const id of item.layers) owner.set(id, [group.id, item.id]);
  }

  const groupOn = (gid) => {
    const s = state.get(gid);
    return s.items.size ? [...s.items.values()].some(Boolean) : s.on;
  };

  const isOn = (layerId) => {
    const own = owner.get(layerId);
    if (!own) return true;
    const [gid, iid] = own;
    return iid == null ? groupOn(gid) : state.get(gid).items.get(iid);
  };

  const views = new Map();

  function render(gid) {
    const view = views.get(gid);
    const s = state.get(gid);
    const values = s.items.size ? [...s.items.values()] : [s.on];
    const all = values.every(Boolean);
    const none = !values.some(Boolean);
    view.row.classList.toggle('off', none);
    view.row.classList.toggle('mixed', !all && !none);
    view.row.setAttribute('aria-checked', all ? 'true' : (none ? 'false' : 'mixed'));
    for (const [iid, el] of view.items) {
      const on = s.items.get(iid);
      el.classList.toggle('off', !on);
      el.setAttribute('aria-checked', String(on));
    }
  }

  const appliedFilters = new Map();

  function emitFilter(group) {
    if (!group.layers.length || !group.items.some((item) => item.filter)) return;
    const expr = exclusionFilter(group, (iid) => state.get(group.id).items.get(iid));
    const key = JSON.stringify(expr);
    if ((appliedFilters.get(group.id) ?? 'null') === key) return;
    appliedFilters.set(group.id, key);
    for (const id of group.layers) onFilter(id, expr);
  }

  function emit(ids) {
    const visible = ids.filter(isOn);
    const hidden = ids.filter((id) => !isOn(id));
    if (visible.length) onChange(visible, true);
    if (hidden.length) onChange(hidden, false);
  }

  function setGroup(gid, on) {
    const s = state.get(gid);
    s.on = on;
    for (const iid of s.items.keys()) s.items.set(iid, on);
    render(gid);
    const group = groups.find((g) => g.id === gid);
    emitFilter(group);
    emit(allLayerIds(group));
  }

  function setItem(gid, iid, on) {
    const s = state.get(gid);
    s.items.set(iid, on);
    s.on = groupOn(gid);
    render(gid);
    const group = groups.find((g) => g.id === gid);
    emitFilter(group);
    emit([...group.layers, ...group.items.find((i) => i.id === iid).layers]);
  }

  function setAll(on) {
    for (const group of groups) setGroup(group.id, on);
  }

  root.innerHTML = '';
  const actions = document.createElement('div');
  actions.className = 'legend-actions';
  const showAll = document.createElement('button');
  showAll.type = 'button';
  showAll.dataset.action = 'show-all';
  showAll.textContent = 'Tout afficher';
  showAll.addEventListener('click', () => setAll(true));
  const hideAll = document.createElement('button');
  hideAll.type = 'button';
  hideAll.dataset.action = 'hide-all';
  hideAll.textContent = 'Tout masquer';
  hideAll.addEventListener('click', () => setAll(false));
  actions.append(showAll, hideAll);
  root.appendChild(actions);

  for (const group of groups) {
    const wrap = document.createElement('div');
    wrap.className = 'legend-group';
    wrap.dataset.group = group.id;
    const row = rowEl('legend-row', group);
    onActivate(row, () => setGroup(group.id, !(row.getAttribute('aria-checked') === 'true')));
    wrap.appendChild(row);
    const itemEls = new Map();
    if (group.items.length) {
      const list = document.createElement('div');
      list.className = 'legend-items';
      list.id = `legend-items-${group.id}`;
      list.hidden = true;
      const expand = document.createElement('button');
      expand.type = 'button';
      expand.className = 'legend-expand';
      expand.textContent = '▸';
      expand.setAttribute('aria-expanded', 'false');
      expand.setAttribute('aria-controls', list.id);
      expand.setAttribute('aria-label', `Détails : ${group.label}`);
      expand.addEventListener('click', (e) => {
        e.stopPropagation();
        list.hidden = !list.hidden;
        expand.setAttribute('aria-expanded', String(!list.hidden));
      });
      expand.addEventListener('keydown', (e) => e.stopPropagation());
      row.appendChild(expand);
      for (const item of group.items) {
        const el = rowEl('legend-item', item);
        onActivate(el, () => setItem(group.id, item.id, !state.get(group.id).items.get(item.id)));
        list.appendChild(el);
        itemEls.set(item.id, el);
      }
      wrap.appendChild(list);
    }
    root.appendChild(wrap);
    views.set(group.id, { row, items: itemEls });
    render(group.id);
  }

  for (const group of groups) emitFilter(group);
  const initiallyHidden = groups.flatMap(allLayerIds).filter((id) => !isOn(id));
  if (initiallyHidden.length) onChange(initiallyHidden, false);

  return { isOn, setAll, setGroup, setItem };
}
