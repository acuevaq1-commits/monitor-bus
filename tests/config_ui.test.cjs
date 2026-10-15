const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = {
  document: {
    getElementById: () => null,
    documentElement: {dataset: {}},
    addEventListener: () => {},
  },
  window: {addEventListener: () => {}},
  localStorage: {getItem: () => null},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('src/presentation/web/static/js/app.js', 'utf8'), context);

assert.equal(
  vm.runInContext("formatTemplateDate('2025-10-13T15:18:19.339328-05:00')", context),
  '13/10/2025 15:18:19',
);
assert.equal(
  vm.runInContext("[...visibleTemplateColumns(['pi_id','pi_codigo','pi_fecha_actividad','pi_sist_orig_id','pi_data','pi_schema'])].join(',')", context),
  'pi_id,pi_fecha_actividad',
);
