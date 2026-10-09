import { describe, it, expect } from 'vitest';
import { buildAttribution, formatUtcDate } from '../../www/map_ui.js';

const META = { 'brussels:map': { version: '1.0.0' }, 'brussels:config_hash': 'abc123def456' };
const DATA = { timestamp: '2026-09-01T05:27:29Z', sha256: 'a10eb5deacbf' };

describe('formatUtcDate', () => {
  it('formate une date ISO en UTC', () => {
    expect(formatUtcDate('2026-09-01T05:27:29Z')).toBe('01/09/2026 05:27 UTC');
  });

  it('retourne null pour une valeur absente ou invalide', () => {
    expect(formatUtcDate(null)).toBeNull();
    expect(formatUtcDate('pas une date')).toBeNull();
  });
});

describe('buildAttribution', () => {
  it('affiche date, version des données et version de config', () => {
    expect(buildAttribution(DATA, META))
      .toBe('Données 01/09/2026 05:27 UTC (a10eb5deacbf) · Config 1.0.0 (abc123def456)');
  });

  it('préfère le timestamp et la séquence de réplication', () => {
    const data = { ...DATA, replication_timestamp: '2026-09-02T00:00:00Z', replication_sequence: 4242 };
    expect(buildAttribution(data, null)).toBe('Données 02/09/2026 00:00 UTC (seq 4242)');
  });

  it('fonctionne sans data-info', () => {
    expect(buildAttribution(null, META)).toBe('Config 1.0.0 (abc123def456)');
  });

  it('retourne null sans aucune information', () => {
    expect(buildAttribution(null, null)).toBeNull();
    expect(buildAttribution(null, {})).toBeNull();
  });

  it('échappe le HTML', () => {
    const meta = { 'brussels:map': { version: '<b>x</b>' } };
    expect(buildAttribution(null, meta)).toBe('Config &lt;b&gt;x&lt;/b&gt;');
  });
});
