/* Settings → District Map: preview of candidate rows using the same rules as the map. */
/* global GCDCandidates */
(function () {
  'use strict';

  var el = document.getElementById('gcd-dm-preview');
  var cfg = window.GCD_DM_ADMIN;
  if (!el || !cfg) return;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var result = GCDCandidates.normalize(cfg.candidates.rows, cfg);
  var candidates = result.candidates;
  var issues = result.issues;
  var errors = issues.filter(function (i) { return i.level === 'error'; });
  var onBallot = candidates.filter(function (c) { return c.onBallot; }).length;

  var html = '<p><strong>' + candidates.length + ' candidates will be shown</strong> (' + onBallot + ' on the ' +
    cfg.electionYear + ' ballot, ' + (candidates.length - onBallot) + ' current officials). ' +
    (issues.length
      ? errors.length + ' rows skipped, ' + (issues.length - errors.length) + ' warnings.'
      : 'No problems found.') + '</p>';

  if (issues.length) {
    html += '<table class="widefat striped gcd-dm-issues"><thead><tr><th>Sheet row</th><th>Candidate</th><th>Problem</th></tr></thead><tbody>' +
      issues.map(function (i) {
        return '<tr class="is-' + i.level + '"><td>' + i.row + '</td><td>' + esc(i.name) + '</td><td>' +
          '<span class="gcd-dm-badge">' + (i.level === 'error' ? 'Skipped' : 'Warning') + '</span> ' + esc(i.message) + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  html += '<table class="widefat striped"><thead><tr><th>Office</th><th>Candidate</th><th>Shown to</th><th>Status</th></tr></thead><tbody>' +
    candidates.map(function (c) {
      var shownTo = { state: 'Everyone', county: 'All of ' + cfg.homeCounty + ' County' }[c.scope] ||
        ({ house: 'House District ', senate: 'Senate District ', congress: 'Congressional District ' }[c.scope] + c.district);
      var status = c.onBallot ? 'On the ballot' + (c.writeIn ? ' · <strong>write-in</strong>' : '')
        : 'Current official' + (c.nextElectionYear ? ' (next election ' + c.nextElectionYear + ')' : '');
      return '<tr><td>' + esc(c.officeLabel) + '</td><td>' + esc(c.name) + '</td><td>' + esc(shownTo) + '</td><td>' + status + '</td></tr>';
    }).join('') + '</tbody></table>';

  el.innerHTML = html;
})();
