#!/usr/bin/env node
/**
 * Fetch the candidate Sheet, check it with the map's own rules, and (with
 * --write) save it as site/candidates.json, which is what the map shows.
 *
 *   node scripts/publish_candidates.js           # preview only
 *   node scripts/publish_candidates.js --write   # preview, then save
 *   node scripts/publish_candidates.js --csv file.csv [--write]   # use a downloaded CSV
 *
 * Run by the "Publish candidates" GitHub Action. The preview is printed, and
 * also written to the Action's run summary ($GITHUB_STEP_SUMMARY).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const GCDCandidates = require('../site/assets/candidates.js');

const ROOT = path.resolve(__dirname, '..');
const CONFIG = path.join(ROOT, 'site', 'config.json');
const PUBLISHED = path.join(ROOT, 'site', 'candidates.json');

// Only these columns are published (see README). Anything else in the Sheet,
// such as notes or contact details, stays out of the public repo and site.
const COLUMNS = ['office', 'race_type', 'district', 'candidate', 'website', 'photo_url', 'order', 'next_election_year', 'write_in'];

/** RFC 4180 CSV -> array of string arrays. */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      row.push(cell); cell = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); rows.push(row); row = []; cell = '';
    } else {
      cell += ch;
    }
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

/** CSV text -> [{lowercase header: value}], keeping blank rows so row numbers match the Sheet. */
function sheetRows(text) {
  const [header, ...lines] = parseCsv(text.replace(/^﻿/, ''));
  if (!header) throw new Error('The file is empty.');
  const names = header.map((h) => h.trim().toLowerCase());
  ['candidate', 'race_type'].forEach((required) => {
    if (!names.includes(required)) throw new Error(`The file has no "${required}" column. Is this the candidate sheet?`);
  });
  const rows = lines.map((cells) => {
    const row = {};
    names.forEach((name, i) => { if (COLUMNS.includes(name)) row[name] = (cells[i] || '').replace(/\s+/g, ' ').trim(); });
    return row;
  });
  while (rows.length && !Object.values(rows[rows.length - 1]).join('')) rows.pop();
  return rows;
}

async function fetchSheet(url) {
  if (!url) throw new Error('Add the published Sheet CSV link as "sheetUrl" in site/config.json.');
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`Google returned HTTP ${res.status}.`);
  if (/html/i.test(res.headers.get('content-type') || '')) {
    throw new Error('The link returned a web page, not CSV. In the Sheet use File → Share → Publish to web, ' +
      'choose "Comma-separated values (.csv)", and copy that link.');
  }
  return res.text();
}

function cell(s) {
  return String(s == null ? '' : s).replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function table(head, rows) {
  if (!rows.length) return '';
  return `| ${head.join(' | ')} |\n|${head.map(() => '---').join('|')}|\n` +
    rows.map((r) => `| ${r.map(cell).join(' | ')} |`).join('\n') + '\n';
}

/** Candidate key for "what changed since the last publish". */
function key(c) {
  return `${c.raceType}|${c.district || ''}|${c.name}`;
}

function changes(before, after) {
  const show = (c) => ({ office: c.officeLabel, name: c.name, onBallot: c.onBallot, writeIn: c.writeIn, website: c.website, photo: c.photo, order: c.order });
  const old = new Map(before.map((c) => [key(c), c]));
  const now = new Map(after.map((c) => [key(c), c]));
  const out = [];
  now.forEach((c, k) => {
    if (!old.has(k)) out.push(['Added', c.officeLabel, c.name]);
    else if (JSON.stringify(show(old.get(k))) !== JSON.stringify(show(c))) out.push(['Changed', c.officeLabel, c.name]);
  });
  old.forEach((c, k) => { if (!now.has(k)) out.push(['Removed', c.officeLabel, c.name]); });
  return out;
}

function report(opts, result, previous) {
  const { candidates, issues } = result;
  const errors = issues.filter((i) => i.level === 'error');
  const onBallot = candidates.filter((c) => c.onBallot).length;
  const diff = changes(previous, candidates);

  let md = `**${candidates.length} candidates will be shown** (${onBallot} on the ${opts.electionYear} ballot, ` +
    `${candidates.length - onBallot} current officials). ` +
    (issues.length ? `${errors.length} rows skipped, ${issues.length - errors.length} warnings.` : 'No problems found.') + '\n\n';

  md += '### Changes since the last publish\n\n' +
    (diff.length ? table(['Change', 'Office', 'Candidate'], diff) : 'None.\n') + '\n';

  if (issues.length) {
    md += '### Problems\n\n' + table(['Sheet row', 'Candidate', 'Problem'],
      issues.map((i) => [i.row, i.name, (i.level === 'error' ? '**Skipped:** ' : 'Warning: ') + i.message])) + '\n';
  }

  md += '### Everyone on the map\n\n' + table(['Office', 'Candidate', 'Shown to', 'Status'], candidates.map((c) => {
    const shownTo = { state: 'Everyone', county: `All of ${opts.homeCounty} County` }[c.scope] ||
      ({ house: 'House District ', senate: 'Senate District ', congress: 'Congressional District ' }[c.scope] + c.district);
    const status = c.onBallot ? 'On the ballot' + (c.writeIn ? ' · **write-in**' : '')
      : 'Current official' + (c.nextElectionYear ? ` (next election ${c.nextElectionYear})` : '');
    return [c.officeLabel, c.name, shownTo, status];
  }));
  return md;
}

async function main() {
  const args = process.argv.slice(2);
  const write = args.includes('--write');
  const csvIndex = args.indexOf('--csv');
  const opts = JSON.parse(fs.readFileSync(CONFIG, 'utf8'));

  const text = csvIndex !== -1 ? fs.readFileSync(args[csvIndex + 1], 'utf8') : await fetchSheet(opts.sheetUrl);
  const rows = sheetRows(text);
  const previousRows = fs.existsSync(PUBLISHED) ? JSON.parse(fs.readFileSync(PUBLISHED, 'utf8')) : [];
  const md = report(opts, GCDCandidates.normalize(rows, opts), GCDCandidates.normalize(previousRows, opts).candidates);

  const heading = write ? '## Published candidates\n\n' : '## Candidate preview (not published)\n\n' +
    '_Nothing changed on the map. To publish, run this action again and choose **publish**._\n\n';
  console.log(heading + md);
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, heading + md);

  if (write) {
    fs.writeFileSync(PUBLISHED, JSON.stringify(rows, null, 2) + '\n');
    console.log(`Wrote ${path.relative(ROOT, PUBLISHED)} (${rows.length} rows).`);
  }
}

main().catch((err) => {
  console.error(`Couldn't read the candidate Sheet: ${err.message}`);
  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `## Couldn't read the candidate Sheet\n\n${err.message}\n`);
  }
  process.exit(1);
});
