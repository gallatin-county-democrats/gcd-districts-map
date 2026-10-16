<?php
/**
 * Fetching and parsing the candidate Sheet.
 *
 * PHP only turns the CSV into rows and stores them. The rules for what each
 * row means (race types, districts, warnings) live in assets/candidates.js,
 * which both the map and the admin preview use, so they can't drift apart.
 */

defined( 'ABSPATH' ) || exit;

/**
 * @return array|WP_Error List of rows keyed by lowercase column header.
 */
function gcd_dm_parse_csv( $text ) {
	$text = preg_replace( '/^\xEF\xBB\xBF/', '', (string) $text ); // UTF-8 BOM

	$fh = fopen( 'php://temp', 'r+' );
	fwrite( $fh, $text );
	rewind( $fh );

	$header = fgetcsv( $fh, 0, ',', '"', '\\' );
	if ( ! $header ) {
		fclose( $fh );
		return new WP_Error( 'gcd_dm_csv', 'The file is empty.' );
	}
	$header = array_map(
		function ( $h ) {
			return strtolower( trim( (string) $h ) );
		},
		$header
	);
	foreach ( array( 'candidate', 'race_type' ) as $required ) {
		if ( ! in_array( $required, $header, true ) ) {
			fclose( $fh );
			return new WP_Error( 'gcd_dm_csv', sprintf( 'The file has no "%s" column. Is this the candidate sheet?', $required ) );
		}
	}

	$rows = array();
	while ( ( $cells = fgetcsv( $fh, 0, ',', '"', '\\' ) ) !== false ) {
		$row = array();
		foreach ( $header as $i => $name ) {
			if ( '' !== $name ) {
				$row[ $name ] = isset( $cells[ $i ] ) ? sanitize_text_field( $cells[ $i ] ) : '';
			}
		}
		$rows[] = $row; // keep blank rows so row numbers match the Sheet
	}
	fclose( $fh );

	while ( $rows && '' === implode( '', end( $rows ) ) ) {
		array_pop( $rows );
	}
	return $rows;
}

/**
 * @return array|WP_Error
 */
function gcd_dm_fetch_sheet( $url ) {
	if ( ! $url ) {
		return new WP_Error( 'gcd_dm_fetch', 'Add the published Sheet CSV link in the settings first.' );
	}
	$res = wp_remote_get( $url, array( 'timeout' => 20 ) );
	if ( is_wp_error( $res ) ) {
		return $res;
	}
	$code = wp_remote_retrieve_response_code( $res );
	$type = (string) wp_remote_retrieve_header( $res, 'content-type' );
	if ( 200 !== $code ) {
		return new WP_Error( 'gcd_dm_fetch', sprintf( 'Google returned HTTP %d.', $code ) );
	}
	if ( false !== stripos( $type, 'html' ) ) {
		return new WP_Error( 'gcd_dm_fetch', 'The link returned a web page, not CSV. In the Sheet use File → Share → Publish to web, choose "Comma-separated values (.csv)", and copy that link.' );
	}
	return gcd_dm_parse_csv( wp_remote_retrieve_body( $res ) );
}

function gcd_dm_store_pending( $rows, $source ) {
	update_option(
		GCD_DM_PENDING,
		array(
			'rows'       => $rows,
			'source'     => $source,
			'fetched_at' => time(),
		),
		false
	);
}

function gcd_dm_published_rows() {
	$published = get_option( GCD_DM_PUBLISHED, array() );
	return isset( $published['rows'] ) ? $published['rows'] : array();
}
