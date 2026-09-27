const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));

test('every registered page has explicit configuration and render sources', () => {
 for (const page of app.pages) {
 for (const extension of ['json', 'js', 'wxml']) {
 assert.ok(fs.existsSync(path.join(root, `${page}.${extension}`)), `${page}.${extension} is missing`);
 }
 assert.doesNotThrow(() => JSON.parse(fs.readFileSync(path.join(root, `${page}.json`), 'utf8')));
 }
});

test('tab routes and global components resolve to packaged files', () => {
 for (const tab of app.tabBar.list) assert.ok(app.pages.includes(tab.pagePath), tab.pagePath);
 for (const component of Object.values(app.usingComponents)) {
 const config = JSON.parse(fs.readFileSync(path.join(root, `${component.replace(/^\//, '')}.json`), 'utf8'));
 assert.equal(config.component, true, component);
 }
});
