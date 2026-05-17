/**
 * map_ui.js
 * ─────────
 * Fonctions UI réutilisables de la carte Brussels.
 * Importé par index.html et par les tests unitaires.
 */

/**
 * Replie / déplie un panneau.
 * @param {string} id - ID de l'élément panneau
 */
export function togglePanel(id) {
  document.getElementById(id).classList.toggle('collapsed');
}

/**
 * Met à jour le lien « éditer dans OpenStreetMap ».
 * Actif uniquement à zoom ≥ 16.
 * @param {object} map - Instance MapLibre GL (getZoom, getCenter)
 */
export function updateOsmLink(map) {
  const link = document.getElementById('osm-edit');
  const zoom = map.getZoom();
  const center = map.getCenter();

  if (zoom >= 16) {
    link.classList.remove('disabled');
    link.href = `https://www.openstreetmap.org/edit#map=${Math.round(zoom)}/${center.lat.toFixed(5)}/${center.lng.toFixed(5)}`;
  } else {
    link.classList.add('disabled');
    link.href = '#';
  }
}

/**
 * Échappe le HTML pour éviter les injections XSS dans le popup DATA.
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Construit le HTML du popup DATA à partir d'une feature MapLibre.
 * @param {object} feature - Feature retournée par queryRenderedFeatures
 * @returns {string} HTML sécurisé
 */
export function buildDataPopupHtml(feature) {
  const props = feature.properties;
  const layerId = escapeHtml(String(feature.layer.id));
  const sourceLayer = escapeHtml(String(feature.sourceLayer || ''));

  let html = `<div class="layer-info">${layerId} (${sourceLayer})</div><table>`;
  const sortedKeys = Object.keys(props).sort();
  for (const key of sortedKeys) {
    html += `<tr><th>${escapeHtml(String(key))}</th><td>${escapeHtml(String(props[key]))}</td></tr>`;
  }
  html += `</table>`;
  return html;
}
