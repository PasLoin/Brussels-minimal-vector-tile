import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  FALLBACK_COLOR,
  exprColor,
  paintColor,
  swatchType,
  legendGroups,
  allLayerIds,
  createLegend,
} from '../../www/legend.js';

const line = (id, color, source = 'roads') => ({ id, type: 'line', source, paint: { 'line-color': color } });
const fill = (id, color, source = 'landuse') => ({ id, type: 'fill', source, paint: { 'fill-color': color } });

function sampleStyle(legend) {
  return {
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#fff' } },
      fill('landuse-residential', '#e0dfdf'),
      fill('landuse-retail', '#ffd6d1'),
      line('roads-casing-primary', '#a06b00'),
      line('roads-fill-primary', '#fcd6a4'),
      line('roads-fill-service', '#ffffff'),
      { id: 'road-labels', type: 'symbol', source: 'roads', paint: { 'text-color': '#333' } },
      { id: 'buildings-fill', type: 'fill', source: 'buildings', paint: { 'fill-color': '#fce1c5' } },
    ],
    metadata: legend === undefined ? {} : { 'brussels:legend': legend },
  };
}

const sampleLegend = () => ([
  {
    id: 'landuse', label: 'Occupation du sol', color: '#e0dfdf', swatch: 'fill', visible: true, layers: [],
    items: [
      { id: 'residential', label: 'Résidentiel', color: '#e0dfdf', swatch: 'fill', layers: ['landuse-residential'] },
      { id: 'retail', label: 'Commerces', color: '#ffd6d1', swatch: 'fill', layers: ['landuse-retail'] },
    ],
  },
  {
    id: 'roads', label: 'Routes', swatch: 'line', layers: ['road-labels'],
    items: [
      { id: 'primary', label: 'Route principale', layers: ['roads-casing-primary', 'roads-fill-primary'] },
      { id: 'service', label: 'Voie de service', color: 'pas-une-couleur', layers: ['roads-fill-service'] },
      { id: 'ghost', label: 'Absent', layers: ['roads-ghost'] },
    ],
  },
  { id: 'buildings', label: 'Bâtiments', color: '#fce1c5', visible: false, layers: ['buildings-fill'], items: [] },
  { id: 'empty', label: 'Vide', layers: ['nope'], items: [] },
]);

describe('exprColor / paintColor', () => {
  it('retourne une couleur littérale', () => {
    expect(exprColor('#abc')).toBe('#abc');
  });

  it('prend le repli d’une expression match', () => {
    expect(exprColor(['match', ['get', 'k'], 'a', '#111', '#222'])).toBe('#222');
  });

  it('ignore les valeurs non colorées', () => {
    expect(exprColor(['get', 'colour'])).toBeNull();
    expect(exprColor(3)).toBeNull();
  });

  it('préfère les couches hors casing, tunnel et pont', () => {
    const layers = [
      line('railway-tunnel-rail-casing', '#ddd'),
      line('railway-rail-bridge-core', '#aaa'),
      line('railway-rail-core', '#787878'),
    ];
    expect(paintColor(layers)).toBe('#787878');
  });

  it('renvoie null sans couleur exploitable', () => {
    expect(paintColor([{ id: 'x', type: 'symbol', paint: {} }])).toBeNull();
  });
});

describe('swatchType', () => {
  it('retient le type majoritaire', () => {
    expect(swatchType([line('a', '#000'), line('b', '#000'), fill('c', '#000')])).toBe('line');
  });

  it('donne fill en cas d’égalité', () => {
    expect(swatchType([line('a', '#000'), fill('c', '#000')])).toBe('fill');
  });

  it('donne dot pour des symboles seuls', () => {
    expect(swatchType([{ id: 's', type: 'symbol' }])).toBe('dot');
  });
});

describe('legendGroups', () => {
  it('construit la légende depuis les métadonnées', () => {
    const groups = legendGroups(sampleStyle(sampleLegend()));
    expect(groups.map((g) => g.id)).toEqual(['landuse', 'roads', 'buildings']);
  });

  it('écarte les couches absentes du style', () => {
    const roads = legendGroups(sampleStyle(sampleLegend())).find((g) => g.id === 'roads');
    expect(roads.items.map((i) => i.id)).toEqual(['primary', 'service']);
  });

  it('applique le repli de couleur : config, peinture, groupe', () => {
    const roads = legendGroups(sampleStyle(sampleLegend())).find((g) => g.id === 'roads');
    expect(roads.color).toBe('#333');
    expect(roads.items[0].color).toBe('#fcd6a4');
    expect(roads.items[1].color).toBe('#ffffff');
  });

  it('utilise la couleur de repli quand rien n’est trouvé', () => {
    const style = {
      layers: [{ id: 'x', type: 'symbol', source: 's' }],
      metadata: { 'brussels:legend': [{ id: 's', label: 'S', layers: ['x'], items: [] }] },
    };
    expect(legendGroups(style)[0].color).toBe(FALLBACK_COLOR);
  });

  it('conserve l’état visible de la configuration', () => {
    const groups = legendGroups(sampleStyle(sampleLegend()));
    expect(groups.find((g) => g.id === 'buildings').visible).toBe(false);
    expect(groups.find((g) => g.id === 'landuse').visible).toBe(true);
  });

  it('se rabat sur les sources sans métadonnées', () => {
    const groups = legendGroups(sampleStyle());
    expect(groups.map((g) => g.id)).toEqual(['landuse', 'roads', 'buildings']);
    expect(groups[1].layers).toContain('road-labels');
    expect(groups[1].swatch).toBe('line');
  });

  it('couvre toutes les couches sourcées du vrai style.json', () => {
    const style = JSON.parse(readFileSync(resolve(__dirname, '../../www/style.json'), 'utf8'));
    const covered = new Set(legendGroups(style).flatMap(allLayerIds));
    const missing = style.layers.filter((l) => l.source && !covered.has(l.id)).map((l) => l.id);
    expect(missing).toEqual([]);
  });
});

describe('createLegend', () => {
  let root;
  let onChange;
  let legend;
  let groups;

  beforeEach(() => {
    document.body.innerHTML = '<div id="legend-content"></div>';
    root = document.getElementById('legend-content');
    onChange = vi.fn();
    groups = legendGroups(sampleStyle(sampleLegend()));
    legend = createLegend(root, groups, { onChange });
  });

  const groupRow = (id) => root.querySelector(`.legend-group[data-group="${id}"] > .legend-row`);
  const itemRow = (gid, iid) => root.querySelector(`.legend-group[data-group="${gid}"] .legend-item[data-id="${iid}"]`);

  it('crée une ligne par groupe et des sous-entrées repliées', () => {
    expect(root.querySelectorAll('.legend-row')).toHaveLength(3);
    expect(root.querySelectorAll('.legend-item')).toHaveLength(4);
    expect(root.querySelector('.legend-items').hidden).toBe(true);
  });

  it('masque au départ les groupes visible: false', () => {
    expect(onChange).toHaveBeenCalledWith(['buildings-fill'], false);
    expect(groupRow('buildings').classList.contains('off')).toBe(true);
    expect(legend.isOn('buildings-fill')).toBe(false);
  });

  it('un clic sur un groupe masque toutes ses couches', () => {
    onChange.mockClear();
    groupRow('roads').click();
    expect(onChange).toHaveBeenCalledWith(['road-labels', 'roads-casing-primary', 'roads-fill-primary', 'roads-fill-service'], false);
    expect(groupRow('roads').getAttribute('aria-checked')).toBe('false');
  });

  it('un clic sur une sous-entrée donne un état mixte', () => {
    itemRow('roads', 'primary').click();
    expect(legend.isOn('roads-fill-primary')).toBe(false);
    expect(legend.isOn('road-labels')).toBe(true);
    expect(groupRow('roads').classList.contains('mixed')).toBe(true);
    expect(groupRow('roads').getAttribute('aria-checked')).toBe('mixed');
  });

  it('les couches communes suivent le groupe quand toutes les sous-entrées sont masquées', () => {
    itemRow('roads', 'primary').click();
    onChange.mockClear();
    itemRow('roads', 'service').click();
    expect(onChange).toHaveBeenCalledWith(['road-labels', 'roads-fill-service'], false);
    expect(groupRow('roads').classList.contains('off')).toBe(true);
  });

  it('un clic sur un groupe mixte réaffiche tout', () => {
    itemRow('roads', 'primary').click();
    groupRow('roads').click();
    expect(legend.isOn('roads-fill-primary')).toBe(true);
    expect(groupRow('roads').getAttribute('aria-checked')).toBe('true');
  });

  it('le bouton de détail déplie sans basculer le groupe', () => {
    onChange.mockClear();
    const expand = groupRow('roads').querySelector('.legend-expand');
    expand.click();
    expect(onChange).not.toHaveBeenCalled();
    expect(expand.getAttribute('aria-expanded')).toBe('true');
    expect(root.querySelector('#legend-items-roads').hidden).toBe(false);
  });

  it('Tout masquer puis Tout afficher', () => {
    root.querySelector('[data-action="hide-all"]').click();
    expect(groups.flatMap(allLayerIds).some((id) => legend.isOn(id))).toBe(false);
    expect(root.querySelectorAll('.legend-row.off')).toHaveLength(3);
    root.querySelector('[data-action="show-all"]').click();
    expect(groups.flatMap(allLayerIds).every((id) => legend.isOn(id))).toBe(true);
    expect(root.querySelectorAll('.legend-row.off, .legend-item.off')).toHaveLength(0);
  });

  it('se pilote au clavier', () => {
    groupRow('landuse').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(legend.isOn('landuse-retail')).toBe(false);
  });

  it('considère visibles les couches hors légende', () => {
    expect(legend.isOn('inconnue')).toBe(true);
  });

  it('applique la couleur et la forme des pastilles', () => {
    const swatch = groupRow('landuse').querySelector('.swatch');
    expect(swatch.classList.contains('fill')).toBe(true);
    expect(swatch.style.background).not.toBe('');
  });
});
