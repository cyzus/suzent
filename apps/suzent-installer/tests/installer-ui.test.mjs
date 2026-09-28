import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../ui/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class Element {
  constructor() {
    this.textContent = ''; this.value = ''; this.children = []; this.style = {};
    this.dataset = {}; this.events = {}; this.attributes = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  set innerHTML(value) { this.children = []; }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  addEventListener(name, callback) { this.events[name] = callback; }
  querySelectorAll() { return []; }
}

async function harness({mode = 'install', result = null, status = null, shortcutFailure = false, shortcutSkipped = false} = {}) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const calls = [];
  const handlers = {};
  const invoke = async (command, args) => {
    calls.push([command, args]);
    if (command === 'installer_context') return {mode, dir: 'D:\\workspace\\suzent', target:'v0.15.0'};
    if (command === 'default_install_dir_command') return 'C:\\Users\\test\\suzent';
    if (command === 'installer_manifest') return JSON.stringify({stages: [{name:'backend',title:'Synchronizing Python environment'}, {name:'shortcuts',title:'Creating launch shortcuts'}]});
    if (command === 'updater_status') return status && JSON.stringify(status);
    if (command === 'updater_result') return result;
    if (command === 'save_diagnostics') return true;
    if (command === 'run_installer_stage') return JSON.stringify({ok: !(shortcutFailure && args.request.stage === 'shortcuts'), skipped: shortcutSkipped && args.request.stage === 'shortcuts', reason:'shortcut denied', logs:[], duration_ms:1});
  };
  const appWindow = {onCloseRequested(fn) { handlers.close = fn; }, close() {calls.push(['close']);}};
  const window = {
    __TAURI__: {core:{invoke}, dialog:{open:async () => 'D:\\work folder\\custom'}, event:{listen:async (name, fn) => {handlers[name] = fn;}}, window:{getCurrentWindow:() => appWindow}},
    setInterval() {return 1;}, clearInterval() {}, setTimeout() {}, clearTimeout() {}, addEventListener() {},
  };
  const context = vm.createContext({
    window, document:{body:element('body'), documentElement:element('html'), getElementById:element, querySelector:element, createElement:() => new Element()},
    navigator:{language:'en', clipboard:{writeText:async text => calls.push(['clipboard',text])}},
    location:{search:''}, URLSearchParams, Date, clearInterval() {}, console,
  });
  vm.runInContext(script, context);
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
  return {element, calls, handlers, context};
}

test('explicit custom path survives initialization and directory selection is exact', async () => {
  const h = await harness();
  assert.equal(h.element('install-dir').value, 'D:\\workspace\\suzent');
  await h.element('browse-dir').events.click();
  assert.equal(h.element('install-dir').value, 'D:\\work folder\\custom');
  await h.element('start').events.click();
  assert.ok(h.calls.filter(([name]) => name === 'run_installer_stage').every(([,args]) => args.request.dir === 'D:\\work folder\\custom'));
  assert.equal(h.element('launch').hidden, false);
  assert.equal(h.element('start').hidden, true);
  assert.equal(h.element('finish-close').disabled, false);
});

test('completion before event subscription is recovered from native result', async () => {
  const h = await harness({mode:'update',result:{code:0,error:null},status:{phase:'complete',progress:100,message:'Done'}});
  assert.equal(h.element('launch').hidden, false);
  assert.equal(h.element('finish-close').disabled, false);
  assert.equal(h.element('complete').style.display, 'block');
});

test('early failure reports actual error without claiming rollback', async () => {
  const h = await harness({mode:'update',result:{code:1,error:'D drive is unavailable'}});
  assert.equal(h.element('error-message').textContent, 'D drive is unavailable');
  assert.doesNotMatch(h.element('error-message').textContent, /restored|preserved/i);
  await h.element('copy-error').events.click();
  assert.match(h.calls.find(([name]) => name === 'clipboard')[1], /D drive is unavailable/);
  await h.element('save-error').events.click();
  assert.match(h.calls.find(([name]) => name === 'save_diagnostics')[1].content, /D:\\workspace\\suzent/);
});

test('repair-required state offers an actual repair operation', async () => {
  const h = await harness({mode:'update',result:{code:1,error:'run suzent repair'},status:{phase:'repair_required',message:'Recovery failed',progress:100}});
  assert.equal(h.element('retry').textContent, 'Repair installation');
  await h.element('retry').events.click();
  assert.equal(h.calls.find(([name]) => name === 'retry_update')[1].repair, true);
});

test('active work blocks closing the window', async () => {
  const h = await harness({mode:'update'});
  let prevented = false;
  h.handlers.close({preventDefault() {prevented = true;}});
  assert.equal(prevented, true);
  await h.element('finish-close').events.click();
  assert.ok(!h.calls.some(([name]) => name === 'close'));
});

test('shortcut failure is a visible partial success with launch available', async () => {
  const h = await harness({shortcutFailure:true});
  await h.element('start').events.click();
  assert.equal(h.element('complete-title').textContent, 'Installed with a warning');
  assert.equal(h.element('launch').hidden, false);
  assert.match(h.element('complete-message').textContent, /suzent shortcuts/);
});

test('update shortcut warnings remain available in diagnostics', async () => {
  const h = await harness({mode:'update',result:{code:0},status:{phase:'complete',progress:100,warnings:['Access denied creating shortcut']}});
  assert.equal(h.element('complete-title').textContent, 'Completed with a warning');
  await h.element('copy-result').events.click();
  assert.match(h.calls.find(([name]) => name === 'clipboard')[1], /Access denied/);
});

test('skipped shortcut stage with a reason is a visible warning', async () => {
  const h = await harness({shortcutSkipped:true});
  await h.element('start').events.click();
  assert.equal(h.element('complete-title').textContent, 'Installed with a warning');
  assert.equal(h.element('launch').hidden, false);
  await h.element('copy-result').events.click();
  assert.match(h.calls.find(([name]) => name === 'clipboard')[1], /shortcut denied/);
});
