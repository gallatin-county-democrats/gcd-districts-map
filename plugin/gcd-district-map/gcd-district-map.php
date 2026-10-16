<?php
/**
 * Plugin Name: GCD District Map
 * Description: Address lookup map showing a voter's county, precinct, legislative and congressional districts, and the Democratic candidates on their ballot. Add it to a page with the [gcd_district_map] shortcode; configure under Settings → District Map.
 * Version: 0.1.1
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * Author: Gallatin County Democrats
 * License: GPL-2.0-or-later
 */

defined( 'ABSPATH' ) || exit;

define( 'GCD_DM_VERSION', '0.1.1' );
define( 'GCD_DM_URL', plugin_dir_url( __FILE__ ) );
define( 'GCD_DM_DIR', plugin_dir_path( __FILE__ ) );

define( 'GCD_DM_MAPBOX_GL_URL', 'https://api.mapbox.com/mapbox-gl-js/v3.9.0' );
define( 'GCD_DM_GEOCODER_URL', 'https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-geocoder/v5.0.3' );

/** Option names. */
define( 'GCD_DM_SETTINGS', 'gcd_dm_settings' );
define( 'GCD_DM_PENDING', 'gcd_dm_pending' );     // fetched but not yet published candidate rows
define( 'GCD_DM_PUBLISHED', 'gcd_dm_published' ); // candidate rows the map shows

require GCD_DM_DIR . 'includes/settings.php';
require GCD_DM_DIR . 'includes/candidates.php';
require GCD_DM_DIR . 'includes/admin-page.php';
require GCD_DM_DIR . 'includes/embed.php';
