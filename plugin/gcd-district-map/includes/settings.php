<?php
/**
 * Plugin settings: defaults, sanitizing, and the config handed to the map page.
 */

defined( 'ABSPATH' ) || exit;

/** Layers looked up for each address, in the order shown on the settings page. */
function gcd_dm_tileset_fields() {
	return array(
		'counties'  => 'Counties',
		'precincts' => 'Precincts',
		'house'     => 'State House districts',
		'senate'    => 'State Senate districts',
		'congress'  => 'Congressional districts',
	);
}

function gcd_dm_defaults() {
	$defaults = array(
		'token'            => '',
		'style_url'        => '',
		'sheet_url'        => '',
		'election_year'    => (int) gmdate( 'Y' ),
		'home_county'      => 'Gallatin',
		'home_congress'    => '1',
		// Districts with addresses in the home county (from the precinct data); used to flag Sheet typos.
		'house_districts'  => '57, 59-69, 77',
		'senate_districts' => '29-35, 39',
		// Initial map view: west, south, east, north.
		'bounds'           => '-111.81, 44.47, -110.78, 46.20',
		'voter_lookup_url' => 'https://prodvoterportal.mt.gov/',
		'write_in_text'    => '{name} is a write-in candidate, so the name won\'t be printed on your ballot. To vote for {name}, fill in the oval next to the write-in line for this race and write "{name}".',
	);
	foreach ( array_keys( gcd_dm_tileset_fields() ) as $key ) {
		$defaults[ 'tileset_' . $key ] = '';
	}
	return $defaults;
}

function gcd_dm_settings() {
	return wp_parse_args( get_option( GCD_DM_SETTINGS, array() ), gcd_dm_defaults() );
}

function gcd_dm_sanitize_settings( $input ) {
	$input = is_array( $input ) ? $input : array();
	$out   = array();
	foreach ( gcd_dm_defaults() as $key => $default ) {
		$value = isset( $input[ $key ] ) ? wp_unslash( $input[ $key ] ) : $default;
		switch ( $key ) {
			case 'election_year':
				$out[ $key ] = absint( $value ) ?: $default;
				break;
			case 'sheet_url':
			case 'voter_lookup_url':
				$out[ $key ] = esc_url_raw( trim( $value ), array( 'https', 'http' ) );
				break;
			case 'write_in_text':
				$out[ $key ] = sanitize_textarea_field( $value );
				break;
			default:
				// Includes style_url, which is a mapbox:// URL that esc_url_raw would strip.
				$out[ $key ] = sanitize_text_field( $value );
		}
	}
	return $out;
}

add_action(
	'admin_init',
	function () {
		register_setting(
			'gcd_dm',
			GCD_DM_SETTINGS,
			array(
				'type'              => 'array',
				'sanitize_callback' => 'gcd_dm_sanitize_settings',
				'default'           => gcd_dm_defaults(),
			)
		);
	}
);

/**
 * Everything the map page (and the admin preview) needs, as a JSON-able array.
 * The Mapbox token is a public token by design; restrict it to the site's URL in Mapbox.
 *
 * @param array $rows Candidate rows to include.
 */
function gcd_dm_client_config( $rows ) {
	$s = gcd_dm_settings();

	$tilesets = array();
	foreach ( array_keys( gcd_dm_tileset_fields() ) as $key ) {
		$tilesets[ $key ] = $s[ 'tileset_' . $key ];
	}

	$bounds = array_map( 'floatval', array_map( 'trim', explode( ',', $s['bounds'] ) ) );
	if ( count( $bounds ) !== 4 ) {
		$bounds = array_map( 'floatval', explode( ',', gcd_dm_defaults()['bounds'] ) );
	}

	return array(
		'token'          => $s['token'],
		'styleUrl'       => $s['style_url'],
		'tilesets'       => $tilesets,
		'homeCounty'     => $s['home_county'],
		'homeCongress'   => $s['home_congress'],
		'electionYear'   => (int) $s['election_year'],
		'knownDistricts' => array(
			'house'  => $s['house_districts'],
			'senate' => $s['senate_districts'],
		),
		'bounds'         => $bounds,
		'voterLookupUrl' => $s['voter_lookup_url'],
		'writeInText'    => $s['write_in_text'],
		'candidates'     => array( 'rows' => array_values( $rows ) ),
	);
}
