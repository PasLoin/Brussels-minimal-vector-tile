export const PATTERN_PIXEL_RATIO = 2;

export function prepareSvg(svg, replace) {
  let out = svg;
  for (const [from, to] of Object.entries(replace || {})) {
    out = out.split(from).join(to);
  }
  return out;
}

export function patternUrl(file, base = './') {
  return /^(https?:)?\/\//.test(file) ? file : base + file.replace(/^\.?\//, '');
}

async function rasterize(svgText, size, pixelRatio) {
  const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
  const blobUrl = URL.createObjectURL(blob);
  try {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = blobUrl;
    });
    const px = Math.round(size * pixelRatio);
    const canvas = document.createElement('canvas');
    canvas.width = px;
    canvas.height = px;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, px, px);
    return ctx.getImageData(0, 0, px, px);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}

export async function loadPattern(map, name, cfg, base = './') {
  if (!cfg || !cfg.file || map.hasImage(name)) return false;
  try {
    const res = await fetch(patternUrl(cfg.file, base));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const svg = prepareSvg(await res.text(), cfg.replace);
    if (!svg.includes('<svg')) throw new Error('SVG invalide');
    const imageData = await rasterize(svg, cfg.size || 32, PATTERN_PIXEL_RATIO);
    if (!map.hasImage(name)) map.addImage(name, imageData, { pixelRatio: PATTERN_PIXEL_RATIO });
    return true;
  } catch (err) {
    console.warn(`Motif ${name} indisponible (${cfg.file}) :`, err.message || err);
    return false;
  }
}

export async function loadPatterns(map, patterns, base = './') {
  const entries = Object.entries(patterns || {});
  const results = await Promise.all(entries.map(([name, cfg]) => loadPattern(map, name, cfg, base)));
  const loaded = results.filter(Boolean).length;
  console.log(`Motifs : ${loaded}/${entries.length} chargés`);
  map.triggerRepaint();
  return loaded;
}
