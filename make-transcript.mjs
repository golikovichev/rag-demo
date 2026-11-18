// Снимает реальные ответы демо и собирает из них одностраничный транскрипт.
// Запуск: node make-transcript.mjs
import fs from 'node:fs';
import vm from 'node:vm';

const ПАПКА = 'C:/Users/MIKHAIL/Documents/Obsidian Vault/Портфолио/rag-demo';
const html = fs.readFileSync(`${ПАПКА}/demo.html`, 'utf8');
const скрипт = html.split('<script>')[1].split('</script>')[0];

const песочница = { console, Math, Object, Map, Set, String, Number, Array, JSON };
vm.createContext(песочница);
vm.runInContext(скрипт, песочница);

const вопросы = [
  'How much is a boiler service?',
  'Can I pay by card?',
  'How much is a CP12 for two appliances?',
  'How much is a radiator?',
  'Do you require a deposit?',
  'Do you cover Leeds?',
  'Can you install a heat pump?',
  'Do you work on Sundays?',
  'Are you Gas Safe registered?',
  'Do you offer finance?',
];

const строки = вопросы.map((вопрос) => {
  const р = песочница.answer(вопрос);
  return {
    вопрос,
    ответ: String(р.text),
    отказ: Boolean(р.refused),
    score: Number(р.score).toFixed(3),
    источник: р.source ? `${р.source.file} → ${р.source.heading}` : '—',
  };
});

const экранировать = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/£/g, '£');

const карточки = строки
  .map(
    (с) => `
  <div class="row ${с.отказ ? 'refused' : ''}">
    <div class="q">${экранировать(с.вопрос)}</div>
    <div class="a">${экранировать(с.ответ)}</div>
    <div class="meta">${с.отказ ? 'отказ' : 'source: ' + экранировать(с.источник)} · match ${с.score}</div>
  </div>`,
  )
  .join('\n');

const документ = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Demo transcript — grounded document assistant</title>
<style>
  @page { size: A4; margin: 16mm 15mm; }
  body { font-family: "Segoe UI", Arial, sans-serif; color:#141414; font-size:10.5pt; line-height:1.45; margin:0; }
  h1 { font-size:20pt; margin:0 0 4px; letter-spacing:-.3px; }
  .lead { color:#555; font-size:10pt; margin:0 0 14px; }
  .note { background:#f4f4f4; border:1px solid #ddd; padding:9px 12px; font-size:9.5pt; margin:0 0 16px; }
  .row { border-left:3px solid #141414; padding:2px 0 2px 11px; margin:0 0 11px; }
  .row.refused { border-left-color:#a8400f; background:#fdf6f1; padding:8px 0 8px 11px; }
  .q { font-weight:700; font-size:10.5pt; }
  .a { margin:2px 0 2px; }
  .meta { font-size:8.5pt; color:#666; }
  .foot { margin-top:16px; border-top:1px solid #ddd; padding-top:9px; font-size:8.5pt; color:#666; }
</style></head><body>
<h1>Demo transcript</h1>
<p class="lead">Real output of the document assistant, captured from the same page that runs in the browser demo. Ten questions, two of them not answerable from the documents.</p>
<div class="note">This is a transcript, not a marketing summary: every answer below was produced by the retrieval code, with the score it reached and the paragraph it came from. Two questions deliberately have no answer in the corpus — see how the assistant refuses instead of inventing a price.</div>
${карточки}
<div class="foot">Corpus: price list and FAQ for a fictional heating company (2 documents). Retrieval: TF-IDF with a score threshold and a coverage penalty; answers are extractive, no language model in the loop. The full page demo runs offline, with no API key.</div>
</body></html>`;

fs.writeFileSync(`${ПАПКА}/demo-transcript.html`, документ, 'utf8');
console.log('строк в транскрипте: ' + строки.length + ' · отказов: ' + строки.filter((с) => с.отказ).length);
console.log('файл: ' + ПАПКА + '/demo-transcript.html');
