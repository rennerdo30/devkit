const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(require('node:path').join(__dirname, '../web/app.js'), 'utf8');
const helper = code.slice(code.indexOf('function unityRunParams('), code.indexOf('function openRun('));
const context = vm.createContext({});
vm.runInContext(helper, context);
function params(values) {
  return JSON.parse(JSON.stringify(context.unityRunParams(k => values[k] || '')));
}
test('compile gate can omit target and quit through its own exit', () => {
  assert.deepEqual(params({unity_method: 'Gate.Run', unity_quit: 'false', unity_timeout: '60'}),
    {mode: 'executeMethod', method: 'Gate.Run', quit: false, nographics: false, timeout: 60});
});
test('test mode strips stale executeMethod fields and preserves filter argv', () => {
  assert.deepEqual(params({unity_mode: 'test', unity_method: 'Old.Build', unity_quit: 'true',
    unity_timeout: '300', unity_graphics: 'off', test_platform: 'PlayMode', test_filter: 'Game.Tests;Other', assembly_names: 'Game.Tests'}),
    {mode: 'test', nographics: true, timeout: 300, test_platform: 'PlayMode', extra: ['-testFilter', 'Game.Tests;Other', '-assemblyNames', 'Game.Tests']});
});
