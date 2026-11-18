// Состязательная проверка демо: 14 вопросов, включая те, где легко ошибиться.
// Запуск: node test-demo-adversarial.mjs
import fs from 'node:fs';
import vm from 'node:vm';

const файл = 'C:/Users/MIKHAIL/Documents/Obsidian Vault/Портфолио/rag-demo/demo.html';
const html = fs.readFileSync(файл, 'utf8');
const скрипт = html.split('<script>')[1].split('</script>')[0];

const песочница = { console, Math, Object, Map, Set, String, Number, Array, JSON };
vm.createContext(песочница);
vm.runInContext(скрипт, песочница);

// [вопрос, что должно быть в ответе, или null если ассистент обязан отказаться]
const вопросы = [
  ['How much is a radiator?', '£220'],
  ['What is the out of hours callout price?', '£210'],
  ['What happens if I cancel on the day?', '£40'],
  ['Do you cover Liverpool?', 'outside our area'],
  ['How long is the warranty on labour?', 'Twelve months'],
  ['How much is a CP12 for two appliances?', '£75'],
  ['Do you repair boilers?', 'repair'],
  ['Can I pay by card?', 'card'],
  ['Do you work on Sundays?', 'Sunday'],
  ['How much is a combi boiler replacement?', '£2,400'],
  ['What is your phone number?', null],
  ['Do you offer finance?', null],
  ['Are you Gas Safe registered?', null],
  ['Do you fix washing machines?', null],
];

let провалов = 0;
for (const [вопрос, ожидание] of вопросы) {
  const р = песочница.answer(вопрос);
  const текст = String(р.text);
  let вердикт;
  if (ожидание === null) {
    вердикт = р.refused ? 'OK отказ' : `ПРОВАЛ (ответил: ${текст.slice(0, 70)})`;
  } else if (р.refused) {
    вердикт = 'ПРОВАЛ (отказался, а ответ есть)';
  } else {
    вердикт = текст.includes(ожидание) ? 'OK' : `ПРОВАЛ (ждём «${ожидание}», а в ответе: ${текст.slice(0, 70)})`;
  }
  if (!вердикт.startsWith('OK')) провалов++;
  console.log(`${вердикт.padEnd(22)} ${р.score.toFixed(3)}  ${вопрос}`);
}
console.log(провалов === 0 ? '\nИТОГ: 14 из 14' : `\nИТОГ: провалов ${провалов} из 14`);
