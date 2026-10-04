// Run with: node --test frontend/tests/loans.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(`${__dirname}/../myloans.html`, 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\n  init\(\);\s*$/, '');

function setup() {
  const requests = [];
  const elements = new Map();
  const context = vm.createContext({
    requireAuth() {},
    FormData,
    LOCKER_LABELS: { top: 'Top', bottom: 'Bottom' },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {
          style: {}, classList: { contains: () => true, remove() {} },
        });
        return elements.get(id);
      },
    },
    showError(el, message) { throw new Error(message); },
    apiFetch: async (path, options) => {
      requests.push({ path, options });
      return context.response;
    },
  });
  vm.runInContext(source, context);
  vm.runInContext(`
    render = () => {};
    allItems = [{id: 1, available: false}, {id: 2, available: true}, {id: 3, available: false}];
    allLoans = [{id: 1, status: 'active', item_ids: [1], photos: []}];
  `, context);
  return { context, requests, run: script => vm.runInContext(script, context) };
}

test('saving gear updates the saved loan and availability with one request', async () => {
  const { context, requests, run } = setup();
  context.response = { id: 1, status: 'active', item_ids: [2], photos: [] };
  await run('editState[1] = {item_ids: [2]}; saveItems(1)');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].options.method, 'PUT');
  assert.equal(run('allItems[0].available'), true);
  assert.equal(run('allItems[1].available'), false);
  assert.equal(run('allItems[2].available'), false);
  assert.equal(run('allLoans[0].item_ids[0]'), 2);
});

test('photo upload uses the returned loan without refetching catalogues', async () => {
  const { context, requests, run } = setup();
  context.response = { loan: { id: 1, status: 'active', item_ids: [1], photos: [{id: 5}] } };
  await run('uploadPhoto(1, "top", "return", {files: ["test-photo"]})');
  assert.equal(requests.length, 1);
  assert.equal(run('allLoans[0].photos[0].id'), 5);
});

test('return immediately moves the saved loan to returned and releases its items', async () => {
  const { context, requests, run } = setup();
  context.response = { returned_at: '2026-10-04T12:00:00', loan: {id: 1, status: 'returned', item_ids: [1]} };
  await run('confirmReturn(1)');
  assert.equal(requests.length, 1);
  assert.equal(run('allLoans[0].status'), 'returned');
  assert.equal(run('allItems[0].available'), true);
  assert.equal(run('allItems[2].available'), false);
});

test('creating a loan and closing its modal does not trigger redundant reloads', async () => {
  const { context, requests, run } = setup();
  context.response = { id: 2, status: 'active', item_ids: [], locker_codes: {top: '123'}, due_date: '2026-10-05T12:00:00' };
  await run('currentLoanMode = "inside"; modalNextToLoan()');
  run('closeStartModal()');
  assert.equal(requests.length, 1);
  assert.equal(run('allLoans[0].id'), 2);
  assert.equal(run('allLoans.length'), 2);
});

test('adding a group uses the authoritative saved item list', async () => {
  const { context, requests, run } = setup();
  context.response = { id: 1, status: 'active', item_ids: [1, 2], photos: [] };
  await run('addGearGroup(1, 4)');
  assert.equal(requests.length, 1);
  assert.equal(run('allLoans[0].item_ids.length'), 2);
  assert.equal(run('allItems[1].available'), false);
});

test('initial data requests start without waiting for the user lookup', async () => {
  const { context, requests, run } = setup();
  let resolveUser;
  context.getMe = () => new Promise(resolve => { resolveUser = resolve; });
  context.response = [];
  const ready = run('init()');
  assert.equal(requests.length, 3);
  resolveUser({is_approved: true});
  await ready;
  assert.equal(run('allLoans.length'), 0);
});
