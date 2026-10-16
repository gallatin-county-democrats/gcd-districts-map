<?php
/**
 * Settings → District Map: map settings plus the candidate Sync / preview / Publish flow.
 */

defined( 'ABSPATH' ) || exit;

define( 'GCD_DM_PAGE', 'gcd-district-map' );

add_action(
	'admin_menu',
	function () {
		add_options_page( 'District Map', 'District Map', 'manage_options', GCD_DM_PAGE, 'gcd_dm_render_admin_page' );
	}
);

add_filter(
	'plugin_action_links_' . plugin_basename( GCD_DM_DIR . 'gcd-district-map.php' ),
	function ( $links ) {
		array_unshift( $links, '<a href="' . esc_url( admin_url( 'options-general.php?page=' . GCD_DM_PAGE ) ) . '">Settings</a>' );
		return $links;
	}
);

add_action(
	'admin_enqueue_scripts',
	function ( $hook ) {
		if ( 'settings_page_' . GCD_DM_PAGE !== $hook ) {
			return;
		}
		wp_enqueue_style( 'gcd-dm-admin', GCD_DM_URL . 'assets/admin.css', array(), GCD_DM_VERSION );
		wp_enqueue_script( 'gcd-dm-candidates', GCD_DM_URL . 'assets/candidates.js', array(), GCD_DM_VERSION, true );
		wp_enqueue_script( 'gcd-dm-admin', GCD_DM_URL . 'assets/admin.js', array( 'gcd-dm-candidates' ), GCD_DM_VERSION, true );

		$pending = get_option( GCD_DM_PENDING );
		$config  = gcd_dm_client_config( $pending ? $pending['rows'] : gcd_dm_published_rows() );
		unset( $config['token'] );
		wp_add_inline_script( 'gcd-dm-admin', 'window.GCD_DM_ADMIN = ' . wp_json_encode( $config ) . ';', 'before' );
	}
);

/* ---- Candidate actions (admin-post.php) ---------------------------------- */

function gcd_dm_admin_redirect( $notice, $type = 'success' ) {
	wp_safe_redirect(
		add_query_arg(
			array(
				'page'           => GCD_DM_PAGE,
				'gcd_dm_notice'  => rawurlencode( $notice ),
				'gcd_dm_type'    => $type,
			),
			admin_url( 'options-general.php' )
		)
	);
	exit;
}

function gcd_dm_check_action( $action ) {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( 'Not allowed.' );
	}
	check_admin_referer( $action );
}

add_action(
	'admin_post_gcd_dm_fetch',
	function () {
		gcd_dm_check_action( 'gcd_dm_fetch' );
		$rows = gcd_dm_fetch_sheet( gcd_dm_settings()['sheet_url'] );
		if ( is_wp_error( $rows ) ) {
			gcd_dm_admin_redirect( 'Couldn\'t fetch the Sheet: ' . $rows->get_error_message(), 'error' );
		}
		gcd_dm_store_pending( $rows, 'Google Sheet' );
		gcd_dm_admin_redirect( sprintf( 'Fetched %d rows. Review them below, then Publish.', count( $rows ) ), 'info' );
	}
);

add_action(
	'admin_post_gcd_dm_upload',
	function () {
		gcd_dm_check_action( 'gcd_dm_upload' );
		if ( empty( $_FILES['gcd_dm_csv']['tmp_name'] ) || ! is_uploaded_file( $_FILES['gcd_dm_csv']['tmp_name'] ) ) {
			gcd_dm_admin_redirect( 'Choose a CSV file to upload.', 'error' );
		}
		$rows = gcd_dm_parse_csv( file_get_contents( $_FILES['gcd_dm_csv']['tmp_name'] ) ); // phpcs:ignore WordPress.WP.AlternativeFunctions
		if ( is_wp_error( $rows ) ) {
			gcd_dm_admin_redirect( $rows->get_error_message(), 'error' );
		}
		gcd_dm_store_pending( $rows, 'uploaded CSV' );
		gcd_dm_admin_redirect( sprintf( 'Read %d rows. Review them below, then Publish.', count( $rows ) ), 'info' );
	}
);

add_action(
	'admin_post_gcd_dm_publish',
	function () {
		gcd_dm_check_action( 'gcd_dm_publish' );
		$pending = get_option( GCD_DM_PENDING );
		if ( ! $pending ) {
			gcd_dm_admin_redirect( 'Nothing to publish.', 'error' );
		}
		update_option(
			GCD_DM_PUBLISHED,
			array(
				'rows'         => $pending['rows'],
				'source'       => $pending['source'],
				'published_at' => time(),
			),
			false
		);
		delete_option( GCD_DM_PENDING );
		gcd_dm_admin_redirect( 'Published. The map now shows these candidates.' );
	}
);

add_action(
	'admin_post_gcd_dm_discard',
	function () {
		gcd_dm_check_action( 'gcd_dm_discard' );
		delete_option( GCD_DM_PENDING );
		gcd_dm_admin_redirect( 'Discarded. The map still shows the previously published candidates.', 'info' );
	}
);

/* ---- Page ---------------------------------------------------------------- */

function gcd_dm_action_form( $action, $label, $class = 'button', $extra = '' ) {
	?>
	<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" class="gcd-dm-inline-form" <?php echo $extra; // phpcs:ignore WordPress.Security.EscapeOutput ?>>
		<input type="hidden" name="action" value="<?php echo esc_attr( $action ); ?>">
		<?php wp_nonce_field( $action ); ?>
		<?php if ( 'gcd_dm_upload' === $action ) : ?>
			<input type="file" name="gcd_dm_csv" accept=".csv,text/csv" required>
		<?php endif; ?>
		<button type="submit" class="<?php echo esc_attr( $class ); ?>"><?php echo esc_html( $label ); ?></button>
	</form>
	<?php
}

function gcd_dm_text_field( $s, $key, $label, $help = '', $type = 'text' ) {
	$name = GCD_DM_SETTINGS . '[' . $key . ']';
	?>
	<tr>
		<th scope="row"><label for="gcd-dm-<?php echo esc_attr( $key ); ?>"><?php echo esc_html( $label ); ?></label></th>
		<td>
			<?php if ( 'textarea' === $type ) : ?>
				<textarea id="gcd-dm-<?php echo esc_attr( $key ); ?>" name="<?php echo esc_attr( $name ); ?>" rows="3" class="large-text"><?php echo esc_textarea( $s[ $key ] ); ?></textarea>
			<?php else : ?>
				<input id="gcd-dm-<?php echo esc_attr( $key ); ?>" name="<?php echo esc_attr( $name ); ?>" type="<?php echo esc_attr( $type ); ?>" value="<?php echo esc_attr( $s[ $key ] ); ?>" class="<?php echo 'number' === $type ? 'small-text' : 'regular-text'; ?>">
			<?php endif; ?>
			<?php if ( $help ) : ?>
				<p class="description"><?php echo wp_kses( $help, array( 'code' => array(), 'strong' => array() ) ); ?></p>
			<?php endif; ?>
		</td>
	</tr>
	<?php
}

function gcd_dm_render_admin_page() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}
	$s         = gcd_dm_settings();
	$pending   = get_option( GCD_DM_PENDING );
	$published = get_option( GCD_DM_PUBLISHED );
	$date_fmt  = get_option( 'date_format' ) . ' ' . get_option( 'time_format' );
	// phpcs:disable WordPress.Security.NonceVerification
	$notice      = isset( $_GET['gcd_dm_notice'] ) ? sanitize_text_field( wp_unslash( $_GET['gcd_dm_notice'] ) ) : '';
	$notice_type = isset( $_GET['gcd_dm_type'] ) && in_array( $_GET['gcd_dm_type'], array( 'success', 'error', 'info' ), true ) ? $_GET['gcd_dm_type'] : 'success';
	// phpcs:enable
	?>
	<div class="wrap gcd-dm-admin">
		<h1>District Map</h1>
		<?php if ( $notice ) : ?>
			<div class="notice notice-<?php echo esc_attr( $notice_type ); ?> is-dismissible"><p><?php echo esc_html( $notice ); ?></p></div>
		<?php endif; ?>

		<p>Add the map to any page with the shortcode <code>[gcd_district_map]</code>. <a href="<?php echo esc_url( gcd_dm_embed_url() ); ?>" target="_blank" rel="noopener">Open the map page on its own</a>.</p>

		<h2>Candidates</h2>
		<p>
			<?php if ( $published ) : ?>
				The map shows <strong><?php echo count( $published['rows'] ); ?> rows</strong> from the <?php echo esc_html( $published['source'] ); ?>, published <?php echo esc_html( wp_date( $date_fmt, $published['published_at'] ) ); ?>.
			<?php else : ?>
				No candidates published yet.
			<?php endif; ?>
		</p>
		<div class="gcd-dm-actions">
			<?php gcd_dm_action_form( 'gcd_dm_fetch', 'Sync from Google Sheet', 'button button-primary' ); ?>
			<span class="gcd-dm-or">or</span>
			<?php gcd_dm_action_form( 'gcd_dm_upload', 'Upload CSV', 'button', 'enctype="multipart/form-data"' ); ?>
		</div>

		<?php if ( $pending ) : ?>
			<div class="gcd-dm-pending">
				<h3>Review before publishing</h3>
				<p><?php echo count( $pending['rows'] ); ?> rows from the <?php echo esc_html( $pending['source'] ); ?>, fetched <?php echo esc_html( wp_date( $date_fmt, $pending['fetched_at'] ) ); ?>. Nothing changes on the map until you publish.</p>
				<div id="gcd-dm-preview"><p>Loading preview…</p></div>
				<div class="gcd-dm-actions">
					<?php gcd_dm_action_form( 'gcd_dm_publish', 'Publish to map', 'button button-primary' ); ?>
					<?php gcd_dm_action_form( 'gcd_dm_discard', 'Discard', 'button' ); ?>
				</div>
			</div>
		<?php elseif ( $published ) : ?>
			<details>
				<summary>Check the published candidates</summary>
				<div id="gcd-dm-preview"></div>
			</details>
		<?php endif; ?>

		<form method="post" action="options.php">
			<?php settings_fields( 'gcd_dm' ); ?>

			<h2>Mapbox</h2>
			<table class="form-table" role="presentation">
				<?php
				gcd_dm_text_field( $s, 'token', 'Public access token', 'A <code>pk.</code> token. In Mapbox, restrict it to this site\'s URL.' );
				gcd_dm_text_field( $s, 'style_url', 'Style URL', 'From Mapbox Studio → Share, e.g. <code>mapbox://styles/yourname/abc123</code>. All map colors and zoom rules live in this style.' );
				foreach ( gcd_dm_tileset_fields() as $key => $label ) {
					gcd_dm_text_field( $s, 'tileset_' . $key, $label . ' tileset ID', 'counties' === $key ? 'Used for the address lookup, e.g. <code>yourname.abc123xy</code>.' : '' );
				}
				gcd_dm_text_field( $s, 'bounds', 'Initial map view', 'West, south, east, north.' );
				?>
			</table>

			<h2>Candidate Sheet</h2>
			<table class="form-table" role="presentation">
				<?php
				gcd_dm_text_field( $s, 'sheet_url', 'Published CSV link', 'In the Sheet: File → Share → Publish to web → Comma-separated values (.csv).', 'url' );
				gcd_dm_text_field( $s, 'election_year', 'Current election year', 'Candidates whose <code>next_election_year</code> matches are shown as on the ballot; everyone else as current officials.', 'number' );
				gcd_dm_text_field( $s, 'write_in_text', 'Write-in callout text', 'Shown for rows with <code>write_in</code> = TRUE. <code>{name}</code> is replaced with the candidate\'s name.', 'textarea' );
				?>
			</table>

			<h2>Area</h2>
			<table class="form-table" role="presentation">
				<?php
				gcd_dm_text_field( $s, 'home_county', 'Home county', 'County races are shown only for addresses in this county.' );
				gcd_dm_text_field( $s, 'home_congress', 'Congressional district', 'The whole home county is in this district.' );
				gcd_dm_text_field( $s, 'house_districts', 'House districts in the county', 'Used to flag Sheet typos. Ranges allowed, e.g. <code>57, 59-69, 77</code>.' );
				gcd_dm_text_field( $s, 'senate_districts', 'Senate districts in the county' );
				gcd_dm_text_field( $s, 'voter_lookup_url', 'Official voter lookup link', '', 'url' );
				?>
			</table>

			<?php submit_button(); ?>
		</form>
	</div>
	<?php
}
