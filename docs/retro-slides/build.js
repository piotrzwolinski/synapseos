const pptxgen = require('pptxgenjs');
const html2pptx = require('/Users/piotrzwolinski/.claude/plugins/cache/anthropic-agent-skills/example-skills/69c0b1a06741/skills/pptx/scripts/html2pptx');
const path = require('path');

async function build() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'Piotr Zwolinski';
  pptx.title = 'Product Advisor — Status & Nächste Schritte';

  const dir = __dirname;
  for (let i = 1; i <= 5; i++) {
    await html2pptx(path.join(dir, `slide${i}.html`), pptx);
  }

  const outPath = path.join(dir, '..', 'retro-thorsten-2026-03-06.pptx');
  await pptx.writeFile({ fileName: outPath });
  console.log('Created:', outPath);
}

build().catch(e => { console.error(e); process.exit(1); });
