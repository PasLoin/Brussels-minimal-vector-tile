/**
 * load_sport_markings.js
 * ──────────────────────
 * Charge les SVG de marquage sportif dans MapLibre GL.
 *
 *   setupSportMarkings(map);          // après new Map()
 *
 * - Pré-charge toutes les images dès map.on('load').
 * - Fallback styleimagemissing pour les images pas encore prêtes.
 * - Rasterise les SVG à la résolution device (canvas = natif × DPR).
 *   pixelRatio TOUJOURS 1 → MapLibre voit l'image à sa taille canvas.
 *   Sur DPR=2 : canvas 400px, logique 400px, rendu 400/2 = 200 CSS px.
 *   Sur DPR=1 : canvas 200px, logique 200px, rendu 200/1 = 200 CSS px.
 *   Les coefficients icon-size sont calibrés sur 200 CSS px.
 */

var SPORT_MARKINGS = [
  'sport-markings-tennis',
  'sport-markings-soccer',
  'sport-markings-basketball'
];

var _pending = {};

function rasterizeAndAdd(map, name, basePath) {
  if (map.hasImage(name) || _pending[name]) return;
  _pending[name] = true;

  var dpr = window.devicePixelRatio || 1;
  var img = new Image();
  img.crossOrigin = 'anonymous';

  img.onload = function() {
    if (map.hasImage(name)) return;

    var w = img.naturalWidth  || img.width  || 200;
    var h = img.naturalHeight || img.height || 100;

    var canvas  = document.createElement('canvas');
    canvas.width  = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);

    var ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    map.addImage(name, imageData, { pixelRatio: 1 });
    console.log('[sport-markings] ' + name + ' (' + canvas.width + 'x' + canvas.height + ' DPR=' + dpr + ')');
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
