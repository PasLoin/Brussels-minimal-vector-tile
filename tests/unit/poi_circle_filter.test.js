import { describe, it, expect } from 'vitest';
import { buildNoIconFilter } from '../../www/poi_icons.js';

const META = {
  type_keys: ['shop', 'amenity', 'craft'],
  presence_keys: ['entrance'],
  special_cases: [{ key: 'cuisine', value: 'friture', icon_key: 'cuisine-friture' }],
};

describe('buildNoIconFilter', () => {
  it('nie la présence d\'une icône chargée', () => {
    const f = buildNoIconFilter(META, ['restaurant', 'bakery']);
    expect(f[0]).toBe('!');
    expect(f[1][0]).toBe('any');
  });

  it('teste chaque type_key contre les icônes chargées, triées', () => {
    const f = buildNoIconFilter(META, ['restaurant', 'bakery']);
    const clauses = f[1].slice(1);
    for (const key of META.type_keys) {
      expect(clauses).toContainEqual(['in', ['get', key], ['literal', ['bakery', 'restaurant']]]);
    }
  });

  it('n\'inclut un cas spécial que si son icône est chargée', () => {
    expect(buildNoIconFilter(META, ['bakery'])[1]).not.toContainEqual(['==', ['get', 'cuisine'], 'friture']);
    expect(buildNoIconFilter(META, ['cuisine-friture'])[1]).toContainEqual(['==', ['get', 'cuisine'], 'friture']);
  });

  it('gère les clés de présence et le repli shop', () => {
    const f = buildNoIconFilter(META, ['entrance', 'shop']);
    expect(f[1]).toContainEqual(['has', 'entrance']);
    expect(f[1]).toContainEqual(['has', 'shop']);
  });

  it('affiche tous les cercles si aucune icône n\'est chargée', () => {
    expect(buildNoIconFilter(META, [])).toEqual(['!', ['any']]);
    expect(buildNoIconFilter({}, undefined)).toEqual(['!', ['any']]);
  });
});
