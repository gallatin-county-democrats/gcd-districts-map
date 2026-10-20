/**
 * District lookup map. Reads window.GCD_DM_CONFIG (config.js, written by
 * scripts/build_site.py or dev/server.py) and renders into #gcd-dm-root.
 *
 * All map styling lives in the Mapbox Studio style. This code only:
 *  - shows one district group at a time (Studio layer groups named
 *    house / senate / congress, plus precincts as a checkbox), and
 *  - sets the filter on each "<group>-highlight" layer to the visitor's district.
 */
/* global mapboxgl, MapboxGeocoder, GCDCandidates */
(function () {
  'use strict';

  var cfg = window.GCD_DM_CONFIG || {};
  var root = document.getElementById('gcd-dm-root');

  var SWITCHABLE = [
    { key: 'house', label: 'State House' },
    { key: 'senate', label: 'State Senate' },
    { key: 'congress', label: 'Congress' },
  ];
  // Property each group's highlight filter matches on (see scripts/prepare_tilesets.py).
  var HIGHLIGHT_KEY = { precincts: 'id', house: 'district', senate: 'district', congress: 'district' };
  var CHIP_ZOOM = { precincts: 13, house: 11, senate: 10, congress: 6 };
  var NO_MATCH = '__none__';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  if (!cfg.token) {
    root.innerHTML = '<p class="gcd-dm-error">The district map isn\'t configured yet (missing Mapbox token).</p>';
    return;
  }

  root.innerHTML =
    '<div class="gcd-dm">' +
    '  <div class="gcd-dm-search" id="gcd-dm-search"></div>' +
    '  <div class="gcd-dm-toolbar">' +
    '    <div class="gcd-dm-layers" role="radiogroup" aria-label="Districts shown on the map">' +
    SWITCHABLE.map(function (g) {
      return '<button type="button" role="radio" aria-checked="false" data-group="' + g.key + '">' + g.label + '</button>';
    }).join('') +
    '    </div>' +
    '    <label class="gcd-dm-precinct-toggle"><input type="checkbox" checked> Show Precincts</label>' +
    '  </div>' +
    '  <div class="gcd-dm-map" id="gcd-dm-map"></div>' +
    '  <div class="gcd-dm-bar" aria-live="polite"></div>' +
    '  <div class="gcd-dm-candidates"></div>' +
    '  <p class="gcd-dm-note">Districts are looked up from map boundaries and can be off for addresses right on a line. ' +
    (cfg.voterLookupUrl
      ? 'Confirm your districts and polling place on <a href="' + esc(cfg.voterLookupUrl) + '" target="_blank" rel="noopener">My Voter Page</a>.'
      : '') +
    '  </p>' +
    '</div>';

  var barEl = root.querySelector('.gcd-dm-bar');
  var candidatesEl = root.querySelector('.gcd-dm-candidates');
  var layerButtons = root.querySelectorAll('.gcd-dm-layers button');
  var precinctToggle = root.querySelector('.gcd-dm-precinct-toggle input');

  var sheet = GCDCandidates.normalize((cfg.candidates && cfg.candidates.rows) || [], cfg);
  if (sheet.issues.length) console.info('[district map] candidate sheet issues', sheet.issues);

  var bounds = cfg.bounds; // [west, south, east, north]
  mapboxgl.accessToken = cfg.token;
  var map = new mapboxgl.Map({
    container: 'gcd-dm-map',
    style: cfg.styleUrl || 'mapbox://styles/mapbox/light-v11',
    bounds: bounds,
    fitBoundsOptions: { padding: 20 },
    cooperativeGestures: true,
  });
  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');
  var geolocate = new mapboxgl.GeolocateControl({ showUserLocation: false, fitBoundsOptions: { maxZoom: 13 } });
  map.addControl(geolocate, 'top-right');
  var marker = new mapboxgl.Marker({ color: '#c7753b' });

  var geocoder = new MapboxGeocoder({
    accessToken: cfg.token,
    mapboxgl: mapboxgl,
    marker: false,
    flyTo: false,
    countries: 'us',
    types: 'address,poi,postcode,place',
    placeholder: 'Enter your address',
    bbox: bounds && [bounds[0] - 0.3, bounds[1] - 0.3, bounds[2] + 0.3, bounds[3] + 0.3],
    proximity: bounds && { longitude: (bounds[0] + bounds[2]) / 2, latitude: (bounds[1] + bounds[3]) / 2 },
  });
  geocoder.addTo('#gcd-dm-search');
  geocoder.on('result', function (e) { lookup(e.result.center, 13); });
  geolocate.on('geolocate', function (e) { lookup([e.coords.longitude, e.coords.latitude]); });
  map.on('click', function (e) { lookup([e.lngLat.lng, e.lngLat.lat]); });

  // --- Layer groups (defined in Mapbox Studio) -------------------------------

  var groupLayers = {}; // group key -> [layer ids]
  var activeGroup = 'house';

  function findGroupLayers() {
    var style = map.getStyle();
    var studioGroups = (style.metadata && style.metadata['mapbox:groups']) || {};
    var groupIdsByName = {};
    Object.keys(studioGroups).forEach(function (id) {
      var name = String(studioGroups[id].name || '').trim().toLowerCase();
      (groupIdsByName[name] = groupIdsByName[name] || []).push(id);
    });
    SWITCHABLE.map(function (g) { return g.key; }).concat('precincts').forEach(function (key) {
      var ids = groupIdsByName[key] || [];
      groupLayers[key] = style.layers.filter(function (layer) {
        var group = layer.metadata && layer.metadata['mapbox:group'];
        // Studio group named e.g. "house", or (without groups) layer ids like "house-fill".
        return ids.indexOf(group) !== -1 || layer.id === key || layer.id.indexOf(key + '-') === 0;
      }).map(function (layer) { return layer.id; });
    });
  }

  function setGroupVisible(key, visible) {
    (groupLayers[key] || []).forEach(function (id) {
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    });
  }

  function showGroup(key) {
    activeGroup = key;
    SWITCHABLE.forEach(function (g) { setGroupVisible(g.key, g.key === key); });
    layerButtons.forEach(function (b) { b.setAttribute('aria-checked', String(b.dataset.group === key)); });
  }

  function setHighlights(result) {
    var values = result ? {
      precincts: result.precinct && result.precinct.id,
      house: result.house,
      senate: result.senate,
      congress: result.congress,
    } : {};
    Object.keys(HIGHLIGHT_KEY).forEach(function (key) {
      var id = key + '-highlight';
      if (map.getLayer(id)) map.setFilter(id, ['==', ['get', HIGHLIGHT_KEY[key]], values[key] || NO_MATCH]);
    });
  }

  map.on('load', function () {
    findGroupLayers();
    showGroup(activeGroup);
    setGroupVisible('precincts', precinctToggle.checked);
    setHighlights(null);
  });

  layerButtons.forEach(function (b) {
    b.addEventListener('click', function () { showGroup(b.dataset.group); });
  });
  precinctToggle.addEventListener('change', function () { setGroupVisible('precincts', precinctToggle.checked); });

  // --- Address lookup ----------------------------------------------------------

  var lastPoint = null;
  var lookupSeq = 0;

  function tilequery(lng, lat) {
    if (cfg.tilequeryUrl) { // dev/server.py's local stand-in for Tilequery
      return fetch(cfg.tilequeryUrl.replace('{lng}', lng).replace('{lat}', lat))
        .then(function (res) { return res.json(); })
        .then(function (json) { return json.features || []; });
    }
    var ids = Object.keys(cfg.tilesets || {}).map(function (k) { return cfg.tilesets[k]; }).filter(Boolean);
    if (!ids.length) return Promise.reject(new Error('No tilesets configured'));
    var url = 'https://api.mapbox.com/v4/' + ids.join(',') + '/tilequery/' + lng + ',' + lat +
      '.json?radius=0&limit=50&dedupe=true&access_token=' + encodeURIComponent(cfg.token);
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('Tilequery HTTP ' + res.status);
      return res.json();
    }).then(function (json) { return json.features || []; });
  }

  function kindOf(p) {
    if (p.kind) return p.kind;
    // Fallbacks for tilesets uploaded before "kind" was added.
    if ('precinct' in p) return 'precincts';
    if ('fips' in p) return 'counties';
    if (/^House/.test(p.label)) return 'house';
    if (/^Senate/.test(p.label)) return 'senate';
    if (/Congress/.test(p.label)) return 'congress';
    return null;
  }

  function interpret(features) {
    var by = {};
    features.forEach(function (f) {
      var kind = kindOf(f.properties || {});
      if (kind) (by[kind] = by[kind] || []).push(f.properties);
    });
    var first = function (kind) { return (by[kind] || [])[0] || null; };
    var county = first('counties');
    if (!county) return null;

    var inHome = county.county === cfg.homeCounty;
    var precinct = (by.precincts || []).filter(function (p) { return p.county === county.county; })[0] || null;
    // Precinct attributes decide House/Senate so the answers never contradict
    // each other where precinct and district lines disagree slightly.
    return {
      county: county.county,
      countyLabel: county.label || county.county + ' County',
      inHome: inHome,
      precinct: precinct,
      house: (precinct && precinct.house) || (first('house') || {}).district || null,
      senate: (precinct && precinct.senate) || (first('senate') || {}).district || null,
      // The whole home county is in one congressional district; the layer's
      // edges have slivers along the county line, so don't trust the point lookup there.
      congress: inHome && cfg.homeCongress ? String(cfg.homeCongress) : (first('congress') || {}).district || null,
    };
  }

  function lookup(point, zoom) {
    var seq = ++lookupSeq;
    lastPoint = point;
    marker.setLngLat(point).addTo(map);
    map.flyTo({ center: point, zoom: Math.max(map.getZoom(), zoom || 0) });
    barEl.innerHTML = '<p class="gcd-dm-hint">Looking up districts…</p>';
    candidatesEl.innerHTML = '';

    tilequery(point[0], point[1]).then(function (features) {
      if (seq !== lookupSeq) return;
      var result = interpret(features);
      setHighlights(result);
      renderBar(result);
      renderCandidates(result);
    }).catch(function (err) {
      if (seq !== lookupSeq) return;
      console.error('[district map]', err);
      barEl.innerHTML = '<p class="gcd-dm-error">Sorry, the district lookup failed. Please try again.</p>';
    });
  }

  // --- Results ---------------------------------------------------------------

  function renderBar(r) {
    if (!r) {
      barEl.innerHTML = '<p class="gcd-dm-hint">That location isn\'t in Montana.</p>';
      return;
    }
    var chips = [
      r.precinct && { group: 'precincts', caption: 'Precinct', value: r.precinct.precinct },
      r.house && { group: 'house', caption: 'State House', value: 'District ' + r.house },
      r.senate && { group: 'senate', caption: 'State Senate', value: 'District ' + r.senate },
      r.congress && { group: 'congress', caption: 'U.S. House', value: 'MT-' + ('0' + r.congress).slice(-2) },
    ].filter(Boolean);

    barEl.innerHTML =
      '<ul class="gcd-dm-chips">' + chips.map(function (c) {
        return '<li><button type="button" data-group="' + c.group + '" title="Show on map">' +
          '<span class="gcd-dm-chip-caption">' + esc(c.caption) + '</span>' +
          '<span class="gcd-dm-chip-value">' + esc(c.value) + '</span></button></li>';
      }).join('') + '</ul>' +
      (r.inHome ? '' : '<p class="gcd-dm-hint">This address is in ' + esc(r.countyLabel) +
        '. County races listed here are for ' + esc(cfg.homeCounty) + ' County only.</p>');

    barEl.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        var group = b.dataset.group;
        if (group === 'precincts') {
          precinctToggle.checked = true;
          setGroupVisible('precincts', true);
        } else {
          showGroup(group);
        }
        map.flyTo({ center: lastPoint, zoom: CHIP_ZOOM[group] });
      });
    });
  }

  function initials(name) {
    return name.split(/\s+/).filter(function (w) { return /^[A-Za-z]/.test(w) && !/\.$/.test(w); })
      .map(function (w) { return w[0]; }).slice(0, 2).join('').toUpperCase();
  }

  // A photo that fails to load (moved, deleted, typo) falls back to initials.
  candidatesEl.addEventListener('error', function (e) {
    var img = e.target;
    if (img.tagName !== 'IMG' || !img.classList.contains('gcd-dm-photo')) return;
    var span = document.createElement('span');
    span.className = 'gcd-dm-photo gcd-dm-initials';
    span.setAttribute('aria-hidden', 'true');
    span.textContent = img.dataset.initials;
    img.replaceWith(span);
  }, true);

  function card(c) {
    var photo = c.photo
      ? '<img class="gcd-dm-photo" src="' + esc(c.photo) + '" alt="" loading="lazy" data-initials="' + esc(initials(c.name)) + '">'
      : '<span class="gcd-dm-photo gcd-dm-initials" aria-hidden="true">' + esc(initials(c.name)) + '</span>';
    var site = c.website
      ? '<a href="' + esc(c.website) + '" target="_blank" rel="noopener">Website</a>'
      : '';
    var next = !c.onBallot && c.nextElectionYear
      ? '<p class="gcd-dm-next">Next election: ' + c.nextElectionYear + '</p>'
      : '';
    var writeIn = c.writeIn && c.onBallot
      ? '<div class="gcd-dm-writein" role="note"><strong>Write-in candidate</strong>' +
        '<p>' + esc(String(cfg.writeInText || '').replace(/\{name\}/g, c.name)) + '</p></div>'
      : '';
    return '<article class="gcd-dm-card' + (writeIn ? ' is-writein' : '') + '">' +
      '<div class="gcd-dm-card-main">' + photo +
      '<div class="gcd-dm-card-body">' +
      '<p class="gcd-dm-office">' + esc(c.officeLabel) + '</p>' +
      '<h3 class="gcd-dm-name">' + esc(c.name) + '</h3>' + site + next +
      '</div></div>' + writeIn + '</article>';
  }

  function section(title, list) {
    if (!list.length) return '';
    var levels = [];
    list.forEach(function (c) { if (levels.indexOf(c.level) === -1) levels.push(c.level); });
    return '<section class="gcd-dm-section"><h2>' + esc(title) + '</h2>' +
      levels.map(function (level) {
        return '<h3 class="gcd-dm-level">' + esc(level) + '</h3><div class="gcd-dm-cards">' +
          list.filter(function (c) { return c.level === level; }).map(card).join('') + '</div>';
      }).join('') + '</section>';
  }

  function renderCandidates(r) {
    if (!r) { candidatesEl.innerHTML = ''; return; }
    var list = GCDCandidates.forResult(sheet.candidates, r);
    candidatesEl.innerHTML =
      section('Democrats on your ' + cfg.electionYear + ' ballot', list.filter(function (c) { return c.onBallot; })) +
      section('Your Democratic officials', list.filter(function (c) { return !c.onBallot; }));
  }

  barEl.innerHTML = '<p class="gcd-dm-hint">Search for an address or tap the map to see your districts and Democratic candidates.</p>';
})();
