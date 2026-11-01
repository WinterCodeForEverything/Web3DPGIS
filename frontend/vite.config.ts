/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// Built files are served by Django under /static/app/ (STATICFILES_DIRS); `npm run dev` serves them from /.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'
const cesiumSource = 'node_modules/cesium/Build/Cesium'

export default defineConfig( ( { command } ) => {
	const base = command === 'build' ? '/static/app/' : '/'
	return {
		base,
		plugins: [
			vue(),
			// Cesium loads its workers, assets and widget CSS at runtime from CESIUM_BASE_URL
			viteStaticCopy( {
				targets: [
					...[ 'Workers', 'ThirdParty', 'Assets', 'Widgets' ].map( dir => ( { src: `${cesiumSource}/${dir}`, dest: 'cesium', rename: { stripBase: 4 } } ) ),
					// Draco decoder for compressed glTF tiles in the three.js viewer
					{ src: 'node_modules/three/examples/jsm/libs/draco/gltf/*', dest: 'draco', rename: { stripBase: 7 } },
				],
			} ),
		],
		define: {
			CESIUM_BASE_URL: JSON.stringify( `${base}cesium` ),
		},
		resolve: {
			alias: { '@': fileURLToPath( new URL( './src', import.meta.url ) ) },
		},
		server: {
			proxy: {
				'/api': backend,
				'/media': backend,
				'/label-icons': backend,
				'/admin': backend,
				'/static': backend,
			},
		},
		build: {
			outDir: 'dist',
			chunkSizeWarningLimit: 6000,
		},
		test: {
			environment: 'jsdom',
		},
	}
} )
