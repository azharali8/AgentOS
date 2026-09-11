const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../lib/voice-endpoint.ts'), 'utf8');
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const exportsObject = {};
vm.runInNewContext(output, {exports: exportsObject});
const { VoiceEndpoint } = exportsObject;

test('continuous speech and partial pauses never finish a turn', () => {
  const endpoint = new VoiceEndpoint(0);
  for (let t = 50; t <= 1000; t += 50) assert.equal(endpoint.sample(0.1, t), 'listen');
  assert.equal(endpoint.sample(0, 2300), 'listen');
  assert.equal(endpoint.sample(0.1, 2350), 'listen');
  assert.equal(endpoint.sample(0, 3749), 'listen');
  assert.equal(endpoint.sample(0, 3750), 'finish');
});
test('silence and a short noise burst are discarded', () => {
  const endpoint = new VoiceEndpoint(0);
  endpoint.sample(0.1, 50);
  assert.equal(endpoint.sample(0, 1500), 'listen');
  assert.equal(endpoint.sample(0, 12000), 'discard');
  assert.equal(endpoint.heardSpeech, false);
});
test('maximum duration discards speech even at a silence boundary', () => {
  const endpoint = new VoiceEndpoint(0);
  for (let t = 50; t <= 1000; t += 50) endpoint.sample(0.1, t);
  assert.equal(endpoint.sample(0, 60000), 'discard');
});
test('a delayed sample cannot make a click count as sustained speech', () => {
  const endpoint = new VoiceEndpoint(0);
  endpoint.sample(0.1, 5000);
  assert.equal(endpoint.heardSpeech, false);
});
