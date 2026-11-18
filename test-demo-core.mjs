// Проверка логики demo.html вне браузера: тот же код, который выполняется на странице.
import fs from 'node:fs';
import vm from 'node:vm';

const файл = 'C:/Users/MIKHAIL/Documents/Obsidian Vault/Портфолио/rag-demo/demo.html';
const html = fs.readFileSync(файл, 'utf8');
const скрипт = html.split('<script>')[1].split('</script>')[0];

const песочница = { console, Math, Object, Map, Set, String, Number, Array, JSON };
vm.createContext(песочница);
vm.runInContext(скрипт, песочница);

const вопросы = [
  ['How much is a boiler service?', '£85'],
  ['Do you require a deposit?', 'never ask for a deposit'],
  ['Do you cover Leeds?', 'outside our area'],
  ['Can you install a heat pump?', 'do not install heat pumps'],
  ['Do you issue a Gas Safety certificate for landlords?', 'CP12'],
  ['Do you do solar panels?', null],
];

let провалов = 0;
for (const [вопрос, ожидание] of вопросы) {
  const р = песочница.answer(вопрос);
  const текст = String(р.text);
  let итог;
  if (ожидание === null) {
    итог = р.refused ? 'OK (отказ)' : 'ПРОВАЛ: должен был отказаться';
  } else {
    итог = !р.refused && текст.includes(ожидание) ? 'OK' : `ПРОВАЛ: ${текст.slice(0, 90)}`;
  }
  if (!итог.startsWith('OK')) провалов++;
  console.log(`${итог}  |  ${вопрос}  |  score=${р.score.toFixed(3)}${р.source ? '  |  ' + р.source.heading : ''}`);
}
console.log(провалов === 0 ? 'ИТОГ: все проверки пройдены' : `ИТОГ: провалов ${провалов}`);
