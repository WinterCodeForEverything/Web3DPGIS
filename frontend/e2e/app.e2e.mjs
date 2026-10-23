// Browser end-to-end test of the whole platform: sign up, upload, processing, viewer tools, delete.
// Run it through scripts/e2e.sh, which starts a throwaway server, worker and database.
//
//   E2E_BASE_URL   the running app (default http://127.0.0.1:8799)
//   CHROME_PATH    Chrome/Chromium binary (defaults for macOS and Linux)
//   E2E_ARTIFACTS  folder for screenshots (default ./e2e-artifacts)
//   EXPECT_TILE_HOST  when set, tiles must come from this host (e.g. the S3 bucket)
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

	await page.waitForSelector( '.toolbar', { timeout: 30000 } )
	await sleep( 6000 )
	check( 'viewer shows the model', ( await textOf( '.title' ) ).includes( 'E2E cube' ), await textOf( '.title' ) )
	await shot( '1-viewer.png' )

	// 5. measuring
	await clickText( 'Measure' )
	await clickText( 'Distance' )
	await canvasClick( -30, 0 ); await canvasClick( 30, 10 ); await canvasClick( 30, 10, 'right' )
	check( 'distance measurement', /Distance: [\d.]+ m/.test( await textOf( '.results' ) ), await textOf( '.results' ) )
	await clickText( 'Area' )
	await canvasClick( -40, -20 ); await canvasClick( 40, -20 ); await canvasClick( 40, 30 ); await canvasClick( 40, 30, 'right' )
	check( 'area measurement is non-zero', /Area: (?!0\.00 )[\d.]+ m²/.test( await textOf( '.results' ) ), await textOf( '.results' ) )
	await clickText( 'Coordinates' )
	await canvasClick( 0, 0 )
	check( 'point coordinates near the placement', /Point: 113\.26\d*, 23\.13\d*/.test( await textOf( '.results' ) ), await textOf( '.results' ) )
	await shot( '2-measure.png' )

	// 6. labels
	await clickText( 'Labels' )
	await page.type( 'input[placeholder="e.g. Main entrance"]', 'Front door' )
	await clickText( 'Place labels' )
	await canvasClick( 10, 5 )
	await page.waitForFunction( () => document.body.textContent.includes( '1 labels on this model' ), { timeout: 10000 } ).catch( () => {} )
	check( 'label placed and saved', ( await page.content() ).includes( '1 labels on this model' ) )

	// 7. height offset
	await clickText( 'Height' )
	await page.$eval( '.panel input[type=number]', el => { el.value = '5'; el.dispatchEvent( new Event( 'input' ) ) } )
	await clickText( 'Save' )
	await sleep( 800 )
	const saved = await page.evaluate( async () => ( await ( await fetch( `/api/v1/models/${location.pathname.split( '/' )[2]}/` ) ).json() ).height_offset )
	check( 'height offset saved', saved === 5, saved )

	// 8. flight paths
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
	await clickText( 'Sight line' )
	await canvasClick( -60, 40 ); await canvasClick( 60, -20 )
	check( 'sight line result', /Visible|Blocked/.test( await textOf( '.results' ) ), await textOf( '.results' ) )
	await clickText( 'Viewshed' )
	await page.$eval( '.panel input[type=number][min="8"]', el => { el.value = '12'; el.dispatchEvent( new Event( 'input' ) ) } )
	await canvasClick( -80, 60 ); await canvasClick( 40, -30 )
	await page.waitForFunction( () => /sampled directions/.test( document.body.textContent ), { timeout: 90000 } ).catch( () => {} )
	const viewshed = await page.evaluate( () => [ ...document.querySelectorAll( '.panel p' ) ].map( p => p.textContent ).join( ' ' ) )
	check( 'viewshed analysis completes', /\d+ of \d+ sampled directions/.test( viewshed ), viewshed )
	await shot( '3-viewshed.png' )

	// 10. walk mode, and switching tools restores the normal camera
	await clickText( 'Walk' )
	await canvasClick( 0, 20 )
	check( 'walk mode starts', ( await page.content() ).includes( 'Stop walking' ) )
	await page.keyboard.down( 'w' ); await sleep( 600 ); await page.keyboard.up( 'w' )
	await clickText( 'Measure' )
	check( 'switching tools ends walk mode', !( await page.content() ).includes( 'Stop walking' ) )

	// 11. the list shows the model; deleting it removes it
	await page.goto( BASE + '/', { waitUntil: 'networkidle0' } )
	const card = () => page.evaluate( () => [ ...document.querySelectorAll( '.model' ) ].find( m => m.textContent.includes( 'E2E cube' ) )?.textContent ?? '' )
	check( 'uploaded model listed as ready', ( await card() ).includes( 'ready' ) )
	await shot( '4-list.png' )
	page.once( 'dialog', d => d.accept() )
	await page.evaluate( () => [ ...document.querySelectorAll( '.model' ) ].find( m => m.textContent.includes( 'E2E cube' ) ).querySelector( 'button.danger' ).click() )
	await page.waitForFunction( () => !document.body.textContent.includes( 'E2E cube' ), { timeout: 10000 } ).catch( () => {} )
	check( 'model deleted from the list', ( await card() ) === '' )

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
