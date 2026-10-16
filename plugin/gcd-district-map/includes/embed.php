<?php
/**
 * The map page (served at /?gcd_district_map=1) and the [gcd_district_map]
 * shortcode that embeds it in an iframe. The iframe keeps theme CSS and
 * script-optimization plugins away from the map.
 */

defined( 'ABSPATH' ) || exit;

function gcd_dm_embed_url() {
	return add_query_arg( 'gcd_district_map', '1', home_url( '/' ) );
}

add_action(
	'template_redirect',
	function () {
		if ( ! isset( $_GET['gcd_district_map'] ) ) { // phpcs:ignore WordPress.Security.NonceVerification
			return;
		}
		if ( ! defined( 'DONOTCACHEPAGE' ) ) {
			define( 'DONOTCACHEPAGE', true ); // respected by most page-cache plugins
		}
		nocache_headers();
		header( 'Content-Type: text/html; charset=utf-8' );
		gcd_dm_render_embed( gcd_dm_client_config( gcd_dm_published_rows() ) );
		exit;
	}
);

/**
 * @param array $config From gcd_dm_client_config().
 */
function gcd_dm_render_embed( $config ) {
	$asset = function ( $file ) {
		return esc_url( GCD_DM_URL . 'assets/' . $file . '?ver=' . rawurlencode( GCD_DM_VERSION ) );
	};
	?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>District lookup map</title>
<link rel="stylesheet" href="<?php echo esc_url( GCD_DM_MAPBOX_GL_URL . '/mapbox-gl.css' ); ?>">
<link rel="stylesheet" href="<?php echo esc_url( GCD_DM_GEOCODER_URL . '/mapbox-gl-geocoder.css' ); ?>">
<link rel="stylesheet" href="<?php echo $asset( 'map.css' ); // phpcs:ignore WordPress.Security.EscapeOutput ?>">
</head>
<body>
<div id="gcd-dm-root"></div>
<script>window.GCD_DM_CONFIG = <?php echo wp_json_encode( $config, JSON_HEX_TAG | JSON_HEX_AMP | JSON_UNESCAPED_SLASHES ); ?>;</script>
<script src="<?php echo esc_url( GCD_DM_MAPBOX_GL_URL . '/mapbox-gl.js' ); ?>"></script>
<script src="<?php echo esc_url( GCD_DM_GEOCODER_URL . '/mapbox-gl-geocoder.min.js' ); ?>"></script>
<script src="<?php echo $asset( 'candidates.js' ); // phpcs:ignore WordPress.Security.EscapeOutput ?>"></script>
<script src="<?php echo $asset( 'map.js' ); // phpcs:ignore WordPress.Security.EscapeOutput ?>"></script>
</body>
</html>
	<?php
}

add_shortcode(
	'gcd_district_map',
	function ( $atts ) {
		static $count = 0;
		$count++;
		$atts = shortcode_atts( array( 'height' => 1000 ), $atts, 'gcd_district_map' );
		$id   = 'gcd-dm-frame-' . $count;

		// The map page reports its height so the iframe never needs its own scrollbar.
		$resize = '(function(f){window.addEventListener("message",function(e){' .
			'if(e.source===f.contentWindow&&e.data&&e.data.type==="gcd-dm-height"){f.style.height=e.data.height+"px";}' .
			'});})(document.getElementById("' . $id . '"));';

		return sprintf(
			'<iframe id="%1$s" class="gcd-dm-frame" src="%2$s" title="District and candidate lookup map" allow="geolocation" style="display:block;width:100%%;height:%3$dpx;border:0"></iframe><script>%4$s</script>',
			esc_attr( $id ),
			esc_url( gcd_dm_embed_url() ),
			absint( $atts['height'] ),
			$resize
		);
	}
);
