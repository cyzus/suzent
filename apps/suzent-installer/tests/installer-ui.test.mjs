import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../ui/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const permissions = JSON.parse(readFileSync(new URL('../capabilities/default.json', import.meta.url), 'utf8')).permissions;

test('window runtime includes the Windows resize handle-leak fix', () => {
  // https://github.com/tauri-apps/tauri/pull/15614
  const lock = readFileSync(new URL('../Cargo.lock', import.meta.url), 'utf8');
  const match = lock.match(/name = "tauri-runtime-wry"\r?\nversion = "(\d+)\.(\d+)\.(\d+)"/);
  assert.ok(match, 'window runtime must be locked');
  const [major, minor, patch] = match.slice(1).map(Number);
  assert.ok(major > 2 || (major === 2 && (minor > 11 || (minor === 11 && patch >= 4))),
    'tauri-runtime-wry must include the 2.11.4 Windows HDC leak fix');
});

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

async function harness({mode = 'install', result = null, status = null, shortcutFailure = false, shortcutSkipped = false, skippedStage = null, branch = null, language = 'en', closeError = null, destinationKind = 'new', recoveryAccepted = false, nativeTitlebar = false} = {}) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const calls = [];
  const handlers = {};
  const invoke = async (command, args) => {
    calls.push([command, args]);
    if (command === 'confirm_git_recovery') return recoveryAccepted;
    if (command === 'inspect_destination') return {kind:destinationKind, branch:destinationKind === 'development' ? 'feature/local' : null};
    if (command === 'installer_context') return {mode, branch, native_titlebar:nativeTitlebar, dir: 'D:\\workspace\\suzent', target:'v0.15.0'};
    if (command === 'default_install_dir_command') return 'C:\\Users\\test\\suzent';
    if (command === 'installer_manifest') return JSON.stringify({stages: [{name:'backend',title:'Synchronizing Python environment'}, {name:'shortcuts',title:'Creating launch shortcuts'}, ...(skippedStage ? [{name:skippedStage,title:skippedStage}] : [])]});
    if (command === 'updater_status') return status && JSON.stringify(status);
    if (command === 'updater_result') return result;
    if (command === 'save_diagnostics') return true;
    if (command === 'run_installer_stage') return JSON.stringify({ok: !(shortcutFailure && args.request.stage === 'shortcuts'), skipped: (shortcutSkipped && args.request.stage === 'shortcuts') || args.request.stage === skippedStage, reason: args.request.stage === skippedStage ? `${skippedStage} unavailable; repair required` : 'shortcut denied', logs:[], duration_ms:1});
  };
  const appWindow = {
    async onCloseRequested(fn) { handlers.close = fn; },
    async close() {
      if (closeError) throw new Error(closeError);
      calls.push(['close']);
      let prevented = false;
      await handlers.close?.({preventDefault() {prevented = true;}});
      if (!prevented) {
        assert.ok(permissions.includes('core:window:allow-destroy'), 'Tauri onCloseRequested destroys the window when not prevented');
        calls.push(['destroy']);
      }
    },
  };
  const window = {
    __TAURI__: {core:{invoke}, dialog:{open:async () => 'D:\\work folder\\custom'}, event:{listen:async (name, fn) => {handlers[name] = fn;}}, window:{getCurrentWindow:() => appWindow}},
    setInterval() {return 1;}, clearInterval() {}, setTimeout() {}, clearTimeout() {}, addEventListener() {},
  };
  const context = vm.createContext({
    window, document:{body:element('body'), documentElement:element('html'), getElementById:element, querySelector:element, createElement:() => new Element()},
    navigator:{language, clipboard:{writeText:async text => calls.push(['clipboard',text])}},
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

test('Mac uses native controls without reserving a second titlebar', async () => {
  const mac = await harness({nativeTitlebar:true});
  assert.equal(mac.element('.app-titlebar').hidden, true);
  assert.equal(mac.element('main').style.height, '100vh');
  const windows = await harness();
  assert.notEqual(windows.element('.app-titlebar').hidden, true);
});

test('repeated update clicks launch only one standalone updater', async () => {
  const h = await harness({destinationKind:'update'});
  await Promise.all([h.element('start').events.click(), h.element('start').events.click()]);
  assert.equal(h.calls.filter(([name]) => name === 'open_existing_updater').length, 1);
});

for (const recoveryAccepted of [false, true]) {
  test(`conflict retry requires native confirmation: accepted=${recoveryAccepted}`, async () => {
    const h = await harness({mode:'update', result:{code:1,error:'CONFIRM_GIT_RECOVERY: unresolved conflicts'}, recoveryAccepted});
    assert.equal(h.element('retry').textContent, 'Back up and update…');
    await h.element('retry').events.click();
    assert.equal(h.calls.filter(([name]) => name === 'confirm_git_recovery').length, 1);
    assert.equal(h.calls.filter(([name]) => name === 'retry_update').length, 0);
    assert.equal(h.element('finish-close').disabled, recoveryAccepted);
  });
}

for (const language of ['en', 'zh-CN']) {
  test(`branch channel and desktop title are consistent in ${language}`, async () => {
    const h = await harness({branch:'feature/desktop', language});
    assert.equal(h.element('mode-badge').textContent, language === 'en' ? 'Development branch' : '开发分支');
    assert.match(h.element('page-subtitle').textContent, /feature\/desktop/);
    assert.equal(vm.runInContext("translateStage('Building desktop UI from source')", h.context), language === 'en' ? 'Building desktop UI from source' : '从源码构建桌面程序');
    assert.equal(vm.runInContext("translateStage('Downloading desktop UI binary')", h.context), language === 'en' ? 'Downloading desktop UI binary' : '下载桌面程序');
  });
}

for (const destinationKind of ['update', 'repair', 'development', 'occupied', 'invalid']) {
  test(`existing destination ${destinationKind} never enters first installation`, async () => {
    const h = await harness({destinationKind});
    await h.element('start').events.click();
    assert.ok(!h.calls.some(([name]) => name === 'run_installer_stage'));
    if (['update', 'repair'].includes(destinationKind)) {
      assert.equal(h.calls.find(([name]) => name === 'open_existing_updater')[1].dir, 'D:\\workspace\\suzent');
    } else {
      assert.ok(!h.calls.some(([name]) => name === 'open_existing_updater'));
    }
    if (destinationKind === 'development') {
      assert.equal(h.element('start').textContent, 'Copy update steps');
      assert.match(h.calls.find(([name]) => name === 'clipboard')[1], /merge --ff-only/);
    }
    if (['occupied', 'invalid'].includes(destinationKind)) assert.equal(h.element('start').disabled, true);
  });
}

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

for (const phase of ['repair_required', 'rolled_back']) {
test(`${phase} state offers an actual repair operation`, async () => {
  const h = await harness({mode:'update',result:{code:1,error:'run suzent repair'},status:{phase,message:'Recovery needs retry',progress:100}});
  assert.equal(h.element('retry').textContent, 'Repair installation');
  await h.element('retry').events.click();
  assert.equal(h.calls.find(([name]) => name === 'retry_update')[1].repair, true);
});
}

test('active work blocks closing the window', async () => {
  const h = await harness({mode:'update'});
  let prevented = false;
  h.handlers.close({preventDefault() {prevented = true;}});
  assert.equal(prevented, true);
  await h.element('finish-close').events.click();
  assert.ok(!h.calls.some(([name]) => name === 'close'));
});

test('idle close can complete the Tauri close-and-destroy flow', async () => {
  const h = await harness();
  await h.element('finish-close').events.click();
  assert.ok(h.calls.some(([name]) => name === 'destroy'));
});

test('completed update close can destroy the window', async () => {
  const h = await harness({mode:'update',result:{code:0}});
  await h.element('finish-close').events.click();
  assert.ok(h.calls.some(([name]) => name === 'destroy'));
});

test('close errors are displayed rather than silently ignored', async () => {
  const h = await harness({closeError:'permission denied'});
  await h.element('finish-close').events.click();
  assert.match(h.element('error-message').textContent, /Could not close.*permission denied/);
});

test('shortcut failure is a visible partial success with launch available', async () => {
  const h = await harness({shortcutFailure:true});
  await h.element('start').events.click();
  assert.equal(h.element('complete-title').textContent, 'Completed with notes');
  assert.equal(h.element('launch').hidden, false);
  assert.match(h.element('complete-message').textContent, /shortcut denied/);
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
  assert.equal(h.element('complete-title').textContent, 'Completed with notes');
  assert.equal(h.element('launch').hidden, false);
  await h.element('copy-result').events.click();
  assert.match(h.calls.find(([name]) => name === 'clipboard')[1], /shortcut denied/);
});

for (const skippedStage of ['playwright', 'ui']) {
  test(`skipped ${skippedStage} result is visible at completion`, async () => {
    const h = await harness({skippedStage});
    await h.element('start').events.click();
    assert.equal(h.element('complete-title').textContent, 'Completed with notes');
    assert.match(h.element('complete-message').textContent, new RegExp(`${skippedStage} unavailable`));
    assert.equal(h.element('launch').hidden, skippedStage === 'ui');
    await h.element('copy-result').events.click();
    assert.match(h.calls.find(([name]) => name === 'clipboard')[1], new RegExp(`${skippedStage} unavailable`));
  });
}
