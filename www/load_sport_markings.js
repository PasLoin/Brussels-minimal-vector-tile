/**
 * load_sport_markings.js
 * ──────────────────────
 * Charge les SVG de marquage sportif dans MapLibre GL.
 *
 *   setupSportMarkings(map);          // après new Map()
 *
 * - Pré-charge toutes les images dès map.on('load').
 * - Fallback styleimagemissing pour les images pas encore prêtes.
 * - Rasterise les SVG via <canvas> à la taille native.
 *   pixelRatio = 1, coefficients calibrés pour le tileSize 512
 *   de MapLibre GL JS (et non 256 comme dans l'ancien Mapbox GL).
 */

var SPORT_MARKINGS = [
  'sport-markings-tennis',
  'sport-markings-soccer',
  'sport-markings-basketball',
  'sport-markings-boules'
];

var _pending = {};

function rasterizeAndAdd(map, name, basePath) {
  if (map.hasImage(name) || _pending[name]) return;
  _pending[name] = true;

  var img = new Image();
  img.crossOrigin = 'anonymous';

  img.onload = function() {
    if (map.hasImage(name)) return;

    var w = img.naturalWidth  || img.width  || 200;
    var h = img.naturalHeight || img.height || 100;

    var canvas  = document.createElement('canvas');
    canvas.width  = w;
    canvas.height = h;

    var ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, w, h);

    var imageData = ctx.getImageData(0, 0, w, h);

    map.addImage(name, imageData, { pixelRatio: 1 });
    console.log('[sport-markings] ' + name + ' (' + w + 'x' + h + ')');
  };

  img.onerror = function() {
    console.warn('[sport-markings] ' + name + ': not found at ' + basePath + name + '.svg');
    _pending[name] = false;
  };

  img.src = basePath + name + '.svg';
}

function setupSportMarkings(map, basePath) {
  if (basePath === undefined) basePath = './assets/icons/';

  map.on('styleimagemissing', function(e) {
    if (e.id.indexOf('sport-markings-') === 0) {
      rasterizeAndAdd(map, e.id, basePath);
    }
  });

  function preload() {
    SPORT_MARKINGS.forEach(function(name) {
      rasterizeAndAdd(map, name, basePath);
    });
  }

  if (map.loaded()) {
    preload();
  } else {
    map.on('load', preload);
  }
}
