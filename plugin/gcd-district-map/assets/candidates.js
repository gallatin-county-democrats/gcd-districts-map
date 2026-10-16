/**
 * Candidate sheet rules, shared by the map page and the WordPress admin preview.
 *
 * Input is the raw Sheet rows (objects keyed by lowercase column header).
 * normalize() turns them into display-ready candidates plus a list of issues
 * for the Sync preview; forResult() picks the candidates for a looked-up address.
 */
(function (root) {
  'use strict';

  // race_type -> which boundary decides who sees it. Any race_type starting
  // with "county_" is countywide (commissioners are elected countywide; their
  // district is only a residency requirement).
  var RACES = {
    us_senate: { scope: 'state', level: 'Federal', rank: 10 },
    us_house: { scope: 'congress', level: 'Federal', rank: 20 },
    mt_senate: { scope: 'senate', level: 'State Legislature', rank: 30 },
    mt_house: { scope: 'house', level: 'State Legislature', rank: 40 },
  };
  var COUNTY_RACE = { scope: 'county', level: 'County', rank: 50 };

  var DISTRICT_NAMES = { house: 'House District', senate: 'Senate District', congress: 'Congressional District' };
  var TRUTHY = /^(true|yes|y|x|1)$/i;
  var IMAGE = /\.(jpe?g|png|gif|webp|svg)(\?.*)?$/i;

  function raceInfo(type) {
    if (RACES[type]) return RACES[type];
    if (type.indexOf('county_') === 0) return COUNTY_RACE;
    return null;
  }

  /** "57, 59-69, 77" -> Set {"57", "59", ..., "69", "77"} */
  function parseRanges(spec) {
    var out = new Set();
    String(spec || '').split(',').forEach(function (part) {
      var m = part.trim().match(/^(\d+)\s*(?:-\s*(\d+))?$/);
      if (!m) return;
      var lo = parseInt(m[1], 10);
      var hi = m[2] ? parseInt(m[2], 10) : lo;
      for (var n = lo; n <= hi; n++) out.add(String(n));
    });
    return out;
  }

  /** "MT-01" -> "1", "064" -> "64" */
  function districtNumber(value) {
    var m = String(value || '').match(/\d+/);
    return m ? String(parseInt(m[0], 10)) : null;
  }

  function httpUrl(value) {
    return /^https?:\/\//i.test(value) ? value : '';
  }

  function officeLabel(c) {
    if (!c.district) return c.office;
    if (c.scope === 'congress') return c.office + ' · MT-' + ('0' + c.district).slice(-2);
    return c.office + ' · District ' + c.district;
  }

  function compare(a, b) {
    return (a.rank - b.rank) ||
      (a.order - b.order) ||
      ((parseInt(a.district, 10) || 0) - (parseInt(b.district, 10) || 0)) ||
      (a.row - b.row);
  }

  /**
   * @param rows  Array of {column: value} objects from the Sheet.
   * @param opts  { electionYear, homeCounty, homeCongress, knownDistricts: {house, senate} }
   * @return { candidates: [...], issues: [{row, name, level: 'error'|'warning', message}] }
   */
  function normalize(rows, opts) {
    opts = opts || {};
    var known = {
      house: parseRanges(opts.knownDistricts && opts.knownDistricts.house),
      senate: parseRanges(opts.knownDistricts && opts.knownDistricts.senate),
      congress: parseRanges(opts.homeCongress),
    };
    var homeCounty = opts.homeCounty || 'the';
    var candidates = [];
    var issues = [];

    (rows || []).forEach(function (raw, i) {
      var rowNum = i + 2; // row 1 of the Sheet is the header
      var get = function (key) { return String(raw[key] == null ? '' : raw[key]).trim(); };
      var name = get('candidate');
      var type = get('race_type').toLowerCase();
      var issue = function (level, message) {
        issues.push({ row: rowNum, name: name, level: level, message: message });
      };

      if (!name) {
        if (Object.keys(raw).some(function (k) { return get(k); })) issue('error', 'No candidate name; row skipped.');
        return;
      }
      var race = raceInfo(type);
      if (!race) {
        issue('error', 'Unrecognized race_type "' + type + '"; not shown on the map.');
        return;
      }

      var district = null;
      if (DISTRICT_NAMES[race.scope]) {
        district = districtNumber(get('district'));
        if (!district) {
          issue('error', race.scope + ' races need a district number; row skipped.');
          return;
        }
        if (known[race.scope].size && !known[race.scope].has(district)) {
          issue('warning', DISTRICT_NAMES[race.scope] + ' ' + district + ' has no addresses in ' + homeCounty +
            ' County, so this candidate will never be shown.');
        }
      } else if (race.scope === 'county' && /^\d+$/.test(get('district'))) {
        district = districtNumber(get('district')); // residency district, e.g. commissioners
      }

      var websiteRaw = get('website');
      var photoRaw = get('photo_url');
      var website = httpUrl(websiteRaw);
      var photo = httpUrl(photoRaw);
      if (IMAGE.test(websiteRaw) && photoRaw && !IMAGE.test(photoRaw)) {
        issue('warning', 'website and photo_url look swapped.');
      } else if (IMAGE.test(websiteRaw)) {
        issue('warning', 'website points to an image file.');
      }
      if (websiteRaw && !website) issue('warning', 'website isn\'t a full http(s) link; not shown.');
      if (photoRaw && !photo) issue('warning', 'photo_url isn\'t a full http(s) link; not shown.');

      var yearRaw = get('next_election_year');
      var year = /^\d{4}$/.test(yearRaw) ? parseInt(yearRaw, 10) : null;
      if (!year) {
        issue('warning', yearRaw
          ? 'next_election_year "' + yearRaw + '" isn\'t a year.'
          : 'No next_election_year; shown as a current official, not on the ballot.');
      }

      var writeIn = TRUTHY.test(get('write_in'));
      if (writeIn && year !== opts.electionYear) {
        issue('warning', 'Marked write-in but not on the ' + opts.electionYear + ' ballot; callout not shown.');
      }

      var orderRaw = get('order');
      var order = orderRaw === '' ? Infinity : Number(orderRaw);
      if (isNaN(order)) {
        issue('warning', 'order "' + orderRaw + '" isn\'t a number; ignored.');
        order = Infinity;
      }

      var c = {
        row: rowNum,
        name: name,
        office: get('office') || type,
        raceType: type,
        scope: race.scope,
        level: race.level,
        rank: race.rank,
        district: district,
        website: website,
        photo: photo,
        order: order,
        nextElectionYear: year,
        onBallot: year === opts.electionYear,
        writeIn: writeIn,
      };
      c.officeLabel = officeLabel(c);
      candidates.push(c);
    });

    candidates.sort(compare);
    return { candidates: candidates, issues: issues };
  }

  /**
   * @param result { inHome, congress, senate, house } from the address lookup.
   */
  function forResult(candidates, result) {
    return candidates.filter(function (c) {
      switch (c.scope) {
        case 'state': return true;
        case 'county': return !!result.inHome;
        default: return c.district === result[c.scope];
      }
    });
  }

  var api = { normalize: normalize, forResult: forResult, parseRanges: parseRanges };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GCDCandidates = api;
})(this);
