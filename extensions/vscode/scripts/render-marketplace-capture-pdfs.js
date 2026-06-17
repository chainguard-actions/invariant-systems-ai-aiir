const fs = require('node:fs');
const path = require('node:path');

const captureDir = process.argv[2];

if (!captureDir) {
  console.error('Usage: node scripts/render-marketplace-capture-pdfs.js <capture-dir>');
  process.exit(1);
}

const shots = [
  ['01-home-view', 'Coverage View'],
  ['02-setup-and-readiness', 'Setup and Readiness'],
  ['03-receipt-explorer-and-viewer', 'Receipts View and Viewer'],
  ['04-control-panel', 'Control Panel'],
  ['05-security-posture', 'Security Posture'],
  ['06-deployment-presets', 'Deployment Presets'],
];

function renderPage(title, imageName) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; padding: 16px; color: #0f172a; }
    h1 { font-size: 22px; margin: 0 0 12px; }
    img { width: 100%; border: 1px solid #cbd5e1; border-radius: 10px; }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <img src="${imageName}.png" alt="${title}">
</body>
</html>
`;
}

const sections = shots.map(([name, title]) => `
<section class="page">
  <h1>${title}</h1>
  <img src="${name}.png" alt="${title}">
</section>`).join('\n');

const deck = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIIR Marketplace Screenshot Pack</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; color: #0f172a; }
    .page { min-height: 100vh; padding: 16px; page-break-after: always; }
    .page:last-child { page-break-after: auto; }
    h1 { font-size: 22px; margin: 0 0 12px; }
    img { width: 100%; border: 1px solid #cbd5e1; border-radius: 10px; }
  </style>
</head>
<body>${sections}
</body>
</html>
`;

for (const [name, title] of shots) {
  fs.writeFileSync(path.join(captureDir, `${name}.html`), renderPage(title, name), 'utf8');
}

fs.writeFileSync(path.join(captureDir, 'MARKETPLACE_SCREENSHOT_PACK.html'), deck, 'utf8');
