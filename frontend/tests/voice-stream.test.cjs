const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/voice-stream.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const exportsObject = {};
vm.runInNewContext(output, {exports:exportsObject});
const {VoicePlayback, reconnectDelay, supervisorStage} = exportsObject;

test('barge-in stops TTS immediately and suppresses older responses', () => {
  let cancelled = 0;
  const p = new VoicePlayback(() => cancelled++);
  p.processing(0);
  p.speechStarted();
  assert.equal(cancelled, 1);
  assert.equal(p.userSpeaking, true);
  assert.equal(p.canSpeak(0), false);
  p.final(); p.processing(1);
  assert.equal(p.canSpeak(1), true);
  assert.equal(p.canSpeak(1), false);
});
test('reconnect is bounded and provider auth failures do not retry', () => {
  assert.equal(reconnectDelay(0,true),1000);
  assert.equal(reconnectDelay(1,true),2000);
  assert.equal(reconnectDelay(2,true),null);
  assert.equal(reconnectDelay(0,false),null);
});
test('Supervisor progress uses real lifecycle and delegated step metadata', () => {
  assert.equal(supervisorStage('WAITING_APPROVAL',[]),'Awaiting approval');
  assert.equal(supervisorStage('RUNNING',[{event_type:'SUBTASK_STARTED',payload:{agent:'TESTING'}}]),'Running tests');
  assert.equal(supervisorStage('FAILED',[]),'Failed');
});
for (const rate of [16000,44100,48000]) test(`PCM16 converts ${rate}Hz to 16kHz little endian frames across arbitrary blocks`, async () => {
  const {Pcm16Encoder} = await import('../public/voice-pcm.mjs');
  const frames = [];
  const encoder = new Pcm16Encoder(rate, frame => frames.push(frame));
  let remaining = rate;
  while(remaining > 0) {
    const size = Math.min(128,remaining);
    encoder.push([new Float32Array(size).fill(1), new Float32Array(size).fill(0)]);
    remaining -= size;
  }
  assert.equal(frames.length,10);
  for(const frame of frames) {
    assert.equal(frame.byteLength,3200);
    const data = new DataView(frame);
    for(let i=0;i<1600;i++) assert.ok(Math.abs(data.getInt16(i*2,true) - 16384) <= 1);
  }
});
test('PCM16 clamps negative and positive samples and does not emit partial frames', async () => {
  const {Pcm16Encoder} = await import('../public/voice-pcm.mjs');
  const frames=[]; const encoder=new Pcm16Encoder(16000,f=>frames.push(f));
  encoder.push([new Float32Array(800).fill(-2)]); assert.equal(frames.length,0);
  encoder.push([new Float32Array(800).fill(2)]);
  const data=new DataView(frames[0]);
  assert.equal(data.getInt16(0,true),-32768); assert.equal(data.getInt16(1600,true),32767);
});
test('queued response remains stale after speech starts before Processing arrives', () => {
  const p=new VoicePlayback(()=>{});
  p.final(0); p.speechStarted(); p.processing(0); p.final(1);
  assert.equal(p.canSpeak(0),false);
});
test('reconnect resets turn identity and speech state before provider numbering restarts', () => {
  const p = new VoicePlayback(()=>{});
  p.final(0); p.speechStarted(); p.begin();
  assert.equal(p.userSpeaking, false);
  assert.equal(p.canSpeak(0), false);
  p.final(0); p.processing(0);
  assert.equal(p.canSpeak(0), true);
});
test('duplicate final revision cannot end newer speech or revive an old response', () => {
  const p = new VoicePlayback(()=>{});
  p.final(0); assert.equal(p.canSpeak(0), true);
  p.speechStarted(); p.final(0);
  assert.equal(p.userSpeaking, true);
  assert.equal(p.canSpeak(0), false);
});
