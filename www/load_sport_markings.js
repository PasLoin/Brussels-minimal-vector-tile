/**
 * load_sport_markings.js
 * ──────────────────────
 * Charge les SVG de marquage sportif dans MapLibre GL.
 *
 * Deux modes d'intégration (au choix) :
 *
 *   A) Lazy via styleimagemissing (recommandé) :
 *        setupSportMarkings(map);
 *      → les images sont chargées à la demande quand le renderer en a besoin.
 *
 *   B) Eager au chargement :
 *        await loadSportMarkings(map);
 *      → toutes les images sont pré-chargées.
 *
 * Les SVG sont rasterisés via <canvas> pour éviter les problèmes WebGL
 * avec les sources SVG non-bitmap.
 */

const SPORT_MARKINGS = [
  'sport-markings-tennis',
  'sport-markings-soccer',
  'sport-markings-basketball',
  // ← ajouter les futurs sports ici
];

// Résolution de rasterisation (2× pour retina)
const RASTER_SCALE = 2;

/**
 * Rasterise un SVG en ImageData via canvas, puis l'ajoute à la map.
 */
function loadAndAddImage(map, name, basePath) {
  return new Promise(function(resolve) {
    if (map.hasImage(name)) { resolve(); return; }

    var img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = function() {
      var w = img.naturalWidth  || img.width;
      var h = img.naturalHeight || img.height;
      if (w === 0 || h === 0) {
        console.warn('[sport-markings] ' + name + ': dimensions nulles, skip');
        resolve();
        return;
      }

      var canvas  = document.createElement('canvas');
      canvas.width  = w * RASTER_SCALE;
      canvas.height = h * RASTER_SCALE;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      if (!map.hasImage(name)) {
        map.addImage(name, ctx.getImageData(0, 0, canvas.width, canvas.height), {
          pixelRatio: RASTER_SCALE,
          sdf: false
        });
      }
      resolve();
    };

    img.onerror = function() {
      console.warn('[sport-markings] ' + name + ': introuvable (' + basePath + name + '.svg)');
      resolve();
    };

    img.src = basePath + name + '.svg';
  });
}

/**
 * Mode A — Lazy : écoute styleimagemissing et charge à la demande.
 * Appeler une seule fois, même avant map.on('load').
 */
function setupSportMarkings(map, basePath) {
  if (basePath === undefined) basePath = './assets/icons/';
  var pending = {};

  map.on('styleimagemissing', function(e) {
    var id = e.id;
    if (id.indexOf('sport-markings-') !== 0) return;
    if (pending[id]) return;
    pending[id] = true;
    loadAndAddImage(map, id, basePath);
  });
}

/**
 * Mode B — Eager : pré-charge toutes les images connues.
 * Retourne une Promise résolue quand tout est chargé.
 */
function loadSportMarkings(map, basePath) {
  if (basePath === undefined) basePath = './assets/icons/';
  return Promise.all(
    SPORT_MARKINGS.map(function(name) {
      return loadAndAddImage(map, name, basePath);
    })
  );
}
