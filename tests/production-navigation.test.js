'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

for (const name of ['server_index.html', 'server_patch/frontend/courses.html']) {
  test(`${name} preserves existing production navigation extensions`, () => {
    const html = fs.readFileSync(path.resolve(__dirname, '..', name), 'utf8');
    const nav = html.match(/<nav\b[\s\S]*?<\/nav>/)[0];
    for (const target of ['shuige/index.html', 'brain-training/index.html', 'zhangyiming/index.html']) {
      assert.ok(nav.includes(`href="${target}"`), `Missing production navigation: ${target}`);
      assert.equal(nav.split(`href="${target}"`).length - 1, 1);
    }
  });
}
