/**
 * load_sport_markings.js
 * ──────────────────────
 * Charge les SVG de marquage sportif dans l'instance MapLibre GL.
 * À appeler après map.on('load', …) ou map.on('style.load', …).
 *
 * Usage :
 *   import { loadSportMarkings } from './load_sport_markings.js';
 *   map.on('load', () => loadSportMarkings(map));
 *
 * Ou directement dans le callback existant :
 *   loadSportMarkings(map);
 */

const SPORT_MARKINGS = [
  'sport-markings-tennis',
  'sport-markings-soccer',
  'sport-markings-basketball',
  // ← ajouter les futurs sports ici
];

export function loadSportMarkings(map, basePath = './assets/icons/') {
  const promises = SPORT_MARKINGS.map(name => {
    return new Promise((resolve, reject) => {
      if (map.hasImage(name)) {
        resolve();
        return;
      }
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        if (!map.hasImage(name)) {
          map.addImage(name, img, { sdf: false });
        }
        resolve();
      };
      img.onerror = () => {
        console.warn(`Sport marking image not found: ${basePath}${name}.svg`);
        resolve();   // ne pas bloquer le chargement
      };
      img.src = `${basePath}${name}.svg`;
    });
  });
  return Promise.all(promises);
}
