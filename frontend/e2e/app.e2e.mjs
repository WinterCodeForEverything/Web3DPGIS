// Browser end-to-end test of the whole platform: sign up, upload, processing, viewer tools, delete.
// Run it through scripts/e2e.sh, which starts a throwaway server, worker and database.
//
//   E2E_BASE_URL   the running app (default http://127.0.0.1:8799)
//   CHROME_PATH    Chrome/Chromium binary (defaults for macOS and Linux)
//   E2E_ARTIFACTS  folder for screenshots (default ./e2e-artifacts)
//   EXPECT_TILE_HOST  when set, tiles must come from this host (e.g. the S3 bucket)
//   E2E_RECON_PHOTOS  a folder of drone photos: reconstructs E2E_RECON_COUNT (default 8) of them with Preview, which
//                     needs COLMAP and OpenMVS on the worker (scripts/e2e.sh sets it when they and the Aukerman set exist)
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import puppeteer from 'puppeteer-core'

const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8799'
const OUT = path.resolve( process.env.E2E_ARTIFACTS ?? 'e2e-artifacts' )
const CHROME = process.env.CHROME_PATH ?? ( process.platform === 'darwin'
	? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
	: [ '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser' ].find( p => fs.existsSync( p ) ) )
fs.mkdirSync( OUT, { recursive: true } )

const OBJ = path.join( os.tmpdir(), `e2e-cube-${process.pid}.obj` )
fs.writeFileSync( OBJ, [ 'v 0 0 0', 'v 20 0 0', 'v 20 20 0', 'v 0 20 0', 'v 0 0 20', 'v 20 0 20', 'v 20 20 20', 'v 0 20 20',
	'f 1 2 3 4', 'f 5 8 7 6', 'f 1 5 6 2', 'f 2 6 7 3', 'f 3 7 8 4', 'f 4 8 5 1' ].join( '\n' ) )
const USER = `e2e_${Date.now().toString( 36 )}`

const results = []
const errors = []
const check = ( name, ok, extra = '' ) => { results.push( [ name, !!ok ] ); console.log( ( ok ? 'PASS ' : 'FAIL ' ) + name + ( ok ? '' : '  ' + extra ) ) }
const sleep = ms => new Promise( r => setTimeout( r, ms ) )

const browser = await puppeteer.launch( {
	executablePath: CHROME,
	headless: true,
	// software WebGL, so the test runs on machines and CI runners without a GPU
	args: [ '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--window-size=1400,900', '--no-sandbox' ],
	defaultViewport: { width: 1400, height: 900 },
} )
const page = await browser.newPage()
page.on( 'console', m => { if ( m.type() === 'error' ) errors.push( m.text() ) } )
page.on( 'pageerror', e => errors.push( 'pageerror: ' + e.message ) )
const tileHosts = new Set()
page.on( 'response', r => {
	if ( r.status() >= 400 ) errors.push( `HTTP ${r.status()} ${r.url()}` )
	if ( /\/tiles\/\d+\//.test( r.url() ) ) tileHosts.add( new URL( r.url() ).host )
} )
page.on( 'requestfailed', r => { if ( !r.failure()?.errorText.includes( 'ERR_ABORTED' ) ) errors.push( `request failed (${r.failure()?.errorText}) ${r.url()}` ) } )

const textOf = sel => page.$eval( sel, el => el.textContent.trim() ).catch( () => '' )
const clickText = async ( text, sel = 'button' ) => {
	const handle = await page.waitForFunction( ( t, s ) => [ ...document.querySelectorAll( s ) ].find( b => b.textContent.trim() === t ), { timeout: 15000 }, text, sel )
	await handle.asElement().click()
}
const canvasClick = async ( dx, dy, button = 'left' ) => {
	const box = await ( await page.$( '.globe canvas' ) ).boundingBox()
	await page.mouse.click( box.x + box.width / 2 + dx, box.y + box.height / 2 + dy, { button } )
	await sleep( 400 )
}
const shot = name => page.screenshot( { path: path.join( OUT, name ) } )

try {
	// 1. the model list works for visitors
	await page.goto( BASE + '/', { waitUntil: 'networkidle0' } )
	check( 'model list loads for visitors', ( await textOf( 'h1' ) ) === 'Models' )

	// 2. sign up, which also signs in
	await page.goto( BASE + '/register', { waitUntil: 'networkidle0' } )
	await page.type( 'input[autocomplete=username]', USER )
	await page.type( 'input[type=email]', `${USER}@example.com` )
	const [ password, confirm ] = await page.$$( 'input[type=password]' )
	await password.type( 'Orbit-Tulip-947' )
	await confirm.type( 'Orbit-Tulip-947' )
	await Promise.all( [ page.waitForFunction( () => location.pathname === '/' ), page.click( 'button.primary' ) ] )
	check( 'sign up signs the user in', ( await page.content() ).includes( USER ) )

	// 3. log out and back in with the email address
	await clickText( 'Log out' )
	await page.goto( BASE + '/login?next=/upload', { waitUntil: 'networkidle0' } )
	await page.type( 'input[autocomplete=username]', `${USER}@example.com` )
	await page.type( 'input[type=password]', 'Orbit-Tulip-947' )
	await Promise.all( [ page.waitForFunction( () => location.pathname === '/upload' ), page.click( 'button.primary' ) ] )
	check( 'login by email redirects to ?next', true )

	// 4. upload an OBJ and follow processing to the viewer
	const [ fileInput ] = await page.$$( 'input[type=file]' )
	await fileInput.uploadFile( OBJ )
	await page.$eval( 'input[maxlength="128"]', el => { el.value = '' } )
	await page.type( 'input[maxlength="128"]', 'E2E cube' )
	await page.type( 'input[aria-label=Longitude]', '113.26' )
	await page.type( 'input[aria-label=Latitude]', '23.13' )
	await page.click( 'button.primary' )
	await page.waitForFunction( () => location.pathname.startsWith( '/models/' ), { timeout: 120000 } )
	check( 'upload → processing → viewer', true )

	// the three.js model viewer opens by default
	await page.waitForFunction( () => document.querySelector( '.toolbar' ) && !document.querySelector( '.loading' ), { timeout: 30000 } )
	check( 'model viewer shows the model', ( await textOf( '.title' ) ).includes( 'E2E cube' ) && !( await page.$( '.overlay' ) ), await textOf( '.title' ) )
	await shot( '1-model-viewer.png' )
	const modelUrl = page.url()
	const apiLabels = () => page.evaluate( async () => ( await ( await fetch( `/api/v1/labels/?model=${location.pathname.split( '/' )[2]}` ) ).json() ).results )

	// labels in the model viewer use the same editor, popup and API as the map viewer
	// choosing a kind adds one label of it; once added it is saved as "Point 1" and its panel opens for a name
	await clickText( 'Labels' )
	await clickText( 'Point' )
	const stage = await ( await page.$( '.stage canvas' ) ).boundingBox()
	await page.mouse.click( stage.x + stage.width / 2, stage.y + stage.height / 2 )
	const nameInput = '.popup input[aria-label="Label name"]'
	await page.waitForSelector( nameInput, { timeout: 10000 } ).catch( () => {} )
	const [ placed ] = await apiLabels()
	// the cube is 20 m wide and placed at 113.26, 23.13, so a point on it is within ~0.0003° and 0–20 m up
	check( 'model viewer: label placed on the model and saved with its default name', placed?.name === 'Point 1' && Math.abs( placed.position.longitude - 113.26 ) < 0.0005
		&& Math.abs( placed.position.latitude - 23.13 ) < 0.0005 && placed.position.height > -1 && placed.position.height < 21, JSON.stringify( placed ) )
	check( 'model viewer: the chosen kind is cleared after adding', !( await page.$( '.panel .icon-button.on' ) ) )
	await page.click( nameInput, { clickCount: 3 } )
	await page.type( nameInput, 'Lobby' )
	await clickText( 'Add property' )
	await page.type( '.popup input[aria-label="Property name"]', 'floor' )
	await page.type( '.popup input[aria-label="Property value"]', '1' )
	await clickText( 'Save' )
	await page.waitForFunction( () => document.querySelector( '.popup table' )?.textContent.includes( 'floor' ), { timeout: 5000 } ).catch( () => {} )
	const [ lobby ] = await apiLabels()
	check( 'model viewer: label named and its properties saved', lobby?.name === 'Lobby' && lobby?.properties?.floor === '1', JSON.stringify( lobby ) )
	await shot( '1-model-viewer-labels.png' )
	await page.click( '.popup button[aria-label=Close]' )

	// measuring in the model viewer works like the map viewer's and saves to the same place
	await clickText( 'Measurement' )
	await clickText( 'Distance' )
	const savedMeasurements = () => page.evaluate( async () => ( await ( await fetch( `/api/v1/measurements/?model=${location.pathname.split( '/' )[2]}` ) ).json() ).results )
	const stageClick = async ( dx, dy, button = 'left' ) => {
		await page.mouse.click( stage.x + stage.width / 2 + dx, stage.y + stage.height / 2 + dy, { button } )
		await sleep( 300 )
	}
	// below the Lobby label, which sits at the centre and would take the click
	await stageClick( -80, 60 ); await stageClick( 0, 110 ); await stageClick( 80, 60 ); await stageClick( 80, 60, 'right' )
	await page.waitForFunction( () => /Distance: [\d.]+ m/.test( document.querySelector( '.list' )?.textContent ?? '' ), { timeout: 5000 } ).catch( () => {} )
	// the panels show only the total; the segment lengths are drawn in the viewer
	check( 'model viewer: distance panels show only the total', /^Distance: [\d.]+ m$/.test( await textOf( '.list li span' ) ) && /Distance: [\d.]+ m(?! \()/.test( await textOf( '.measure-properties .result' ) ),
		`${await textOf( '.list' )} | ${await textOf( '.measure-properties .result' )}` )
	const segmentLabels = await page.$$eval( '.stage div span', els => els.map( e => e.textContent ).filter( t => /^(Total )?[\d.]+ m$/.test( t ) ) )
	check( 'model viewer: segment labels drawn, without a total', segmentLabels.length === 2 && !segmentLabels.some( t => t.startsWith( 'Total' ) ), segmentLabels.join( ', ' ) )
	// a new measurement opens its property panel; it is saved, with a name and an annotation, only by its Save button
	check( 'model viewer: property panel opens for the new measurement', ( await textOf( '.measure-properties' ) ).includes( 'New distance measurement' ), await textOf( '.measure-properties' ) )
	await sleep( 500 )
	check( 'model viewer: nothing saved before Save', ( await savedMeasurements() ).length === 0, JSON.stringify( await savedMeasurements() ) )
	await page.type( '.measure-properties input', 'Lobby path' )
	await page.type( '.measure-properties textarea', 'From the door to the desk' )
	await clickText( 'Save' )
	await page.waitForFunction( async () => ( await ( await fetch( `/api/v1/measurements/?model=${location.pathname.split( '/' )[2]}` ) ).json() ).results[0]?.name === 'Lobby path', { timeout: 5000 } ).catch( () => {} )
	const modelMeasurements = await savedMeasurements()
	check( 'model viewer: measurement saved with its name and annotation', modelMeasurements.length === 1 && modelMeasurements[0].kind === 'distance'
		&& modelMeasurements[0].points.length === 3 && modelMeasurements[0].name === 'Lobby path' && modelMeasurements[0].annotation === 'From the door to the desk',
		JSON.stringify( modelMeasurements ) )
	await shot( '1-model-viewer-measure.png' )
	await page.click( '.panel button[aria-label="Close tool"]' )

	// the GIS tools live in the map viewer
	await clickText( 'Map (GIS)' )
	await page.waitForFunction( () => location.search === '?viewer=map' && document.querySelector( '.cesium-viewer' ), { timeout: 30000 } )
	await page.waitForSelector( '.toolbar', { timeout: 30000 } )
	await sleep( 6000 )
	check( 'map viewer shows the model', ( await textOf( '.title' ) ).includes( 'E2E cube' ), await textOf( '.title' ) )
	await shot( '1-viewer.png' )

	// 5. measuring
	await clickText( 'Measurement' )
	await clickText( 'Distance' )
	await canvasClick( -60, 20 ); await canvasClick( 0, -20 ); await canvasClick( 60, 20 ); await canvasClick( 60, 20, 'right' )
	check( 'distance measurement', /^Distance: [\d.]+ m$/.test( await textOf( '.list li span' ) ), await textOf( '.list' ) )
	check( 'distance list shows the saved distance from the model viewer too', ( await textOf( '.list' ) ).includes( 'Lobby path' ), await textOf( '.list' ) )
	await clickText( 'Save' )
	await shot( '2-distance.png' )
	await clickText( 'Area' )
	await canvasClick( -40, -20 ); await canvasClick( 40, -20 ); await canvasClick( 40, 30 ); await canvasClick( 40, 30, 'right' )
	check( 'area measurement is non-zero', /Area: (?!0\.00 )[\d.]+ m²/.test( await textOf( '.list' ) ), await textOf( '.list' ) )
	check( 'choosing a kind lists only that kind', !( await textOf( '.list' ) ).includes( 'Distance' ), await textOf( '.list' ) )
	await clickText( 'Save' )
	await clickText( 'Coordinates' )
	await canvasClick( 0, 0 )
	check( 'point coordinates near the placement', /Point: 113\.26° E, 23\.13° N, [\d.]+ m/.test( await textOf( '.list' ) ), await textOf( '.list' ) )
	await clickText( "Don't save" )
	await sleep( 500 )
	check( "Don't save leaves the measurement listed but unsaved", ( await textOf( '.list' ) ).includes( 'Not saved' ) && !( await savedMeasurements() ).some( m => m.kind === 'point' ),
		await textOf( '.list' ) )
	await page.click( '.list button.edit' )
	await clickText( 'Save' )
	await page.waitForFunction( async () => ( await ( await fetch( `/api/v1/measurements/?model=${location.pathname.split( '/' )[2]}` ) ).json() ).results.some( m => m.kind === 'point' ), { timeout: 5000 } ).catch( () => {} )
	// each measurement saved from its panel is stored: a path as one line with its segment lengths, an area as a closed polygon
	const measurements = await savedMeasurements()
	const byKind = Object.fromEntries( measurements.map( m => [ m.kind, m ] ) )
	check( 'measurements saved', measurements.length === 4 && byKind.distance?.points.length === 3 && byKind.distance.results.segment_lengths_m.length === 2
		&& byKind.area?.points.length === 3 && byKind.area.results.area_m2 > 0 && byKind.point?.points.length === 1, JSON.stringify( measurements.map( m => [ m.kind, m.points.length, m.results ] ) ) )
	await page.click( '.panel button[aria-label="Close tool"]' )
	await clickText( 'Measurement' )
	await sleep( 1000 )
	check( 'nothing is loaded until a kind is chosen', ( await page.$$( '.list li' ) ).length === 0, await textOf( '.list' ) )
	await clickText( 'Distance' )
	await page.waitForFunction( () => document.querySelectorAll( '.list li' ).length === 2, { timeout: 10000 } ).catch( () => {} )
	check( 'saved distances come back when the kind is chosen', ( await page.$$( '.list li' ) ).length === 2, await textOf( '.list' ) )
	// clicking one in the list moves the camera to it; only its Edit property button opens the property panel
	await page.click( '.list button.item[aria-label="Show Lobby path"]' )
	await sleep( 1500 )
	check( 'clicking a list item does not open the property panel', !( await page.$( '.measure-properties' ) ) )
	await page.click( '.list button.edit[aria-label="Edit property of Lobby path"]' )
	await sleep( 300 )
	const props = await textOf( '.measure-properties' )
	check( 'Edit property opens the property panel', props.includes( 'Lobby path' ) && await page.$eval( '.measure-properties textarea', t => t.value ) === 'From the door to the desk', props )
	await shot( '2-measure.png' )

	// 6. labels
	await clickText( 'Labels' )
	await clickText( 'Point' )
	await canvasClick( 10, 5 )
	// the label placed in the model viewer is already there, so this is the second
	await page.waitForFunction( () => document.body.textContent.includes( '2 labels on this model' ), { timeout: 10000 } ).catch( () => {} )
	check( 'label placed and saved', ( await page.content() ).includes( '2 labels on this model' ) )
	await page.waitForSelector( nameInput, { timeout: 5000 } ).catch( () => {} )
	await page.click( nameInput, { clickCount: 3 } )
	await page.type( nameInput, 'Front door' )
	await clickText( 'Save' )
	await page.waitForFunction( async () => ( await ( await fetch( `/api/v1/labels/?model=${location.pathname.split( '/' )[2]}` ) ).json() ).results.some( l => l.name === 'Front door' ), { timeout: 5000 } ).catch( () => {} )
	check( 'label named in its panel', ( await apiLabels() ).some( l => l.name === 'Front door' ) )
	await page.click( '.popup button[aria-label=Close]' )

	// 7. height offset
	await clickText( 'Adjust model height' )
	await page.$eval( '.panel input[type=number]', el => { el.value = '5'; el.dispatchEvent( new Event( 'input' ) ) } )
	await clickText( 'Save' )
	await sleep( 800 )
	const saved = await page.evaluate( async () => ( await ( await fetch( `/api/v1/models/${location.pathname.split( '/' )[2]}/` ) ).json() ).height_offset )
	check( 'height offset saved', saved === 5, saved )

	// 8. flight paths
	await clickText( 'Viewer' )
	await clickText( 'Flight' )
	await clickText( 'Add current view' )
	await page.mouse.move( 700, 450 ); await page.mouse.wheel( { deltaY: -400 } ); await sleep( 500 )
	await clickText( 'Add current view' )
	await page.type( 'input[placeholder="Tour name"]', 'Quick tour' )
	await clickText( 'Save' )
	await page.waitForFunction( () => document.body.textContent.includes( 'Quick tour' ), { timeout: 10000 } ).catch( () => {} )
	check( 'flight path saved', ( await page.content() ).includes( 'Quick tour' ) )
	await clickText( 'Play' )
	await sleep( 500 )
	check( 'flight path plays', ( await page.content() ).includes( '>Stop<' ) )
	await sleep( 5000 )

	// 9. analysis tools
	await clickText( 'Analysis' )
	await clickText( 'Sight line' )
	await canvasClick( -60, 40 ); await canvasClick( 60, -20 )
	check( 'sight line result', /Visible|Blocked/.test( await textOf( '.list' ) ), await textOf( '.list' ) )
	await clickText( 'Viewshed' )
	await page.$eval( '.panel input[type=number][min="8"]', el => { el.value = '12'; el.dispatchEvent( new Event( 'input' ) ) } )
	await canvasClick( -80, 60 ); await canvasClick( 40, -30 )
	await page.waitForFunction( () => /\d+ of \d+ rays/.test( document.body.textContent ), { timeout: 90000 } ).catch( () => {} )
	const viewshed = await page.evaluate( () => [ ...document.querySelectorAll( '.panel p' ) ].map( p => p.textContent ).join( ' ' ) )
	check( 'viewshed analysis completes', /\d+ of \d+ rays/.test( viewshed ), viewshed )
	await shot( '3-viewshed.png' )

	// 10. walk mode, and switching tools restores the normal camera
	await clickText( 'Viewer' )
	await clickText( 'Walk' )
	await canvasClick( 0, 20 )
	check( 'walk mode starts', ( await page.content() ).includes( 'Stop walking' ) )
	await page.keyboard.down( 'w' ); await sleep( 600 ); await page.keyboard.up( 'w' )
	await clickText( 'Measurement' )
	check( 'switching tools ends walk mode', !( await page.content() ).includes( 'Stop walking' ) )

	// labels placed in the map viewer show in the model viewer too
	await page.goto( modelUrl, { waitUntil: 'networkidle0' } )
	await page.waitForFunction( () => document.querySelectorAll( '.model-label' ).length === 2, { timeout: 30000 } ).catch( () => {} )
	const shown = await page.$$eval( '.model-label', els => els.map( e => e.textContent.trim() ).sort().join( ', ' ) )
	check( 'model viewer shows labels from both viewers', shown === 'Front door, Lobby', shown )

	// 11. the list shows the model; deleting it removes it
	await page.goto( BASE + '/', { waitUntil: 'networkidle0' } )
	const card = () => page.evaluate( () => [ ...document.querySelectorAll( '.model' ) ].find( m => m.textContent.includes( 'E2E cube' ) )?.textContent ?? '' )
	check( 'uploaded model listed as ready', ( await card() ).includes( 'ready' ) )
	await shot( '4-list.png' )
	page.once( 'dialog', d => d.accept() )
	await page.evaluate( () => [ ...document.querySelectorAll( '.model' ) ].find( m => m.textContent.includes( 'E2E cube' ) ).querySelector( 'button.danger' ).click() )
	await page.waitForFunction( () => !document.body.textContent.includes( 'E2E cube' ), { timeout: 10000 } ).catch( () => {} )
	check( 'model deleted from the list', ( await card() ) === '' )

	// 12. reconstruction from photos: create, upload, start, cancel, try again (resumes), open in both viewers
	const RECON = process.env.E2E_RECON_PHOTOS
	if ( RECON ) {
		const count = Number( process.env.E2E_RECON_COUNT ?? 8 )
		const photos = fs.readdirSync( RECON ).filter( f => /\.jpe?g$/i.test( f ) ).sort().slice( 0, count ).map( f => path.join( RECON, f ) )
		await page.goto( BASE + '/reconstruct', { waitUntil: 'networkidle0' } )
		await page.type( 'input[maxlength="128"]', 'E2E reconstruction' )
		await page.click( 'input[name=preset][value=preview]' )
		await Promise.all( [ page.waitForFunction( () => /^\/reconstructions\/\d+$/.test( location.pathname ), { timeout: 15000 } ), page.click( 'button.primary' ) ] )
		const reconId = Number( page.url().split( '/' ).pop() )
		// the page loads the server's limits and the reconstruction before it shows the photo picker
		const photoInput = await page.waitForSelector( 'input[type=file][multiple][accept^="image/jpeg"]', { timeout: 15000 } )
		await photoInput.uploadFile( ...photos )
		await page.waitForFunction( n => document.body.textContent.includes( `${n} uploaded ·` ), { timeout: 120000 }, photos.length ).catch( () => {} )
		check( `reconstruction: ${photos.length} photos uploaded from the page`, ( await page.content() ).includes( `${photos.length} uploaded ·` ) )
		await shot( '5-reconstruction-photos.png' )

		await clickText( 'Start reconstruction' )
		// cancel once two stages are done, so trying again has checkpoints to skip
		await page.waitForFunction( () => document.querySelectorAll( '.stages li.done' ).length >= 2, { timeout: 300000 } )
		await clickText( 'Cancel' )
		await page.waitForFunction( () => document.querySelector( '[role=alert]' )?.textContent.includes( 'Cancelled.' ), { timeout: 60000 } ).catch( () => {} )
		check( 'reconstruction: cancelled from the page', ( await textOf( '[role=alert]' ) ).includes( 'Cancelled.' ), await textOf( '[role=alert]' ) )
		await clickText( 'Try again' )
		// the cancelled job shows as failed until the page has loaded the new one
		await page.waitForFunction( () => !document.querySelector( '.stages li.failed' ), { timeout: 15000 } )
		await page.waitForFunction( () => [ ...document.querySelectorAll( 'a' ) ].some( a => a.textContent.trim() === 'Open in 3D viewer' )
			|| document.querySelector( '.stages li.failed' ), { timeout: 900000 } ).catch( () => {} )
		const jobs = await page.evaluate( async id => {
			const recon = await ( await fetch( `/api/v1/reconstructions/${id}/` ) ).json()
			const list = ( await ( await fetch( `/api/v1/jobs/?model=${recon.model}` ) ).json() ).results
			return Promise.all( list.map( async j => ( await fetch( `/api/v1/jobs/${j.id}/` ) ).json() ) )
		}, reconId )
		const resumed = jobs.find( j => j.kind === 'reconstruction' && j.status === 'succeeded' )
		check( 'reconstruction: trying again skips the finished stages', /features: done before, skipped/.test( resumed?.log ?? '' ),
			jobs.map( j => `${j.kind} ${j.status} ${j.message}` ).join( '; ' ) )
		await shot( '5-reconstruction-done.png' )
		check( 'reconstruction: results panel shows how it went', ( await page.content() ).includes( 'Photos placed' ) )

		await clickText( 'Open in 3D viewer', 'a' )
		await page.waitForFunction( () => document.querySelector( '.toolbar' ) && !document.querySelector( '.loading' ), { timeout: 60000 } ).catch( () => {} )
		check( 'reconstruction: opens in the model viewer', ( await textOf( '.title' ) ).includes( 'E2E reconstruction' ) && !( await page.$( '.overlay' ) ), await textOf( '.title' ) )
		await shot( '5-reconstruction-model-viewer.png' )
		await clickText( 'Map (GIS)' )
		await page.waitForFunction( () => document.querySelector( '.cesium-viewer' ), { timeout: 30000 } ).catch( () => {} )
		await sleep( 6000 )
		check( 'reconstruction: opens on the map', !!( await page.$( '.cesium-viewer' ) ) )
		await shot( '5-reconstruction-map.png' )
		await page.evaluate( async id => fetch( `/api/v1/reconstructions/${id}/`, { method: 'DELETE',
			headers: { 'X-CSRFToken': document.cookie.match( /csrftoken=([^;]+)/ )?.[1] ?? '' } } ), reconId )
	} else {
		console.log( 'SKIP reconstruction (set E2E_RECON_PHOTOS to a folder of drone photos; needs COLMAP and OpenMVS)' )
	}

	if ( process.env.EXPECT_TILE_HOST ) {
		check( `tiles were loaded from ${process.env.EXPECT_TILE_HOST}`, tileHosts.size === 1 && tileHosts.has( process.env.EXPECT_TILE_HOST ), [ ...tileHosts ].join( ', ' ) )
	}
	check( 'no console, network or server errors', errors.length === 0, errors.slice( 0, 8 ).join( '\n' ) )
} catch ( e ) {
	check( 'test ran to the end', false, e.stack )
	await shot( 'failure.png' ).catch( () => {} )
} finally {
	await browser.close()
	fs.rmSync( OBJ, { force: true } )
}

const failed = results.filter( ( [ , ok ] ) => !ok )
console.log( `\n${results.length - failed.length}/${results.length} passed${failed.length ? '' : ''}  (screenshots in ${OUT})` )
process.exit( failed.length ? 1 : 0 )
