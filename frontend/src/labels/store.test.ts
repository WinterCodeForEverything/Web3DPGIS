import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Label } from '@/api/types'

const server = vi.hoisted( () => ( { labels: [] as Label[], nextId: 1 } ) )

vi.mock( '@/api/client', () => ( {
	api: {
		labels: vi.fn( async () => ( { count: server.labels.length, next: null, previous: null, results: [ ...server.labels ] } ) ),
		createLabel: vi.fn( async ( input: { model: number; name: string; icon: number | null; position: Label['position'] } ) => {
			const label: Label = { id: server.nextId++, icon_url: null, properties: {}, ...input }
			server.labels.push( label )
			return label
		} ),
		updateLabel: vi.fn( async ( id: number, changes: Partial<Label> ) => {
			const label = server.labels.find( l => l.id === id )!
			Object.assign( label, changes )
			return label
		} ),
		deleteLabel: vi.fn( async ( id: number ) => { server.labels = server.labels.filter( l => l.id !== id ) } ),
	},
} ) )

const { api } = await import( '@/api/client' )
const { createLabelStore } = await import( './store' )

const here = { longitude: 113.26, latitude: 23.13, height: 5 }

describe( 'label store', () => {
	beforeEach( () => {
		server.labels = []
		server.nextId = 1
		vi.clearAllMocks()
	} )

	it( 'saves a new label for its model and reloads the list', async () => {
		const store = createLabelStore( 7 )
		await store.create( { name: '  Front door ', icon: null, position: here } )
		expect( api.createLabel ).toHaveBeenCalledWith( { model: 7, name: 'Front door', icon: null, position: here } )
		expect( store.labels.value.map( l => l.name ) ).toEqual( [ 'Front door' ] )
	} )

	it( 'names unnamed labels "Label"', async () => {
		const store = createLabelStore( 7 )
		await store.create( { name: ' ', icon: 3, position: here } )
		expect( store.labels.value[0].name ).toBe( 'Label' )
	} )

	it( 'keeps the selected label in step with the server after editing its properties', async () => {
		const store = createLabelStore( 7 )
		const label = await store.create( { name: 'Door', icon: null, position: here } )
		store.selected.value = store.labels.value[0]
		await store.updateProperties( label.id, { floor: '1' } )
		expect( store.selected.value?.properties ).toEqual( { floor: '1' } )
	} )

	it( 'clears the selection when the selected label is deleted', async () => {
		const store = createLabelStore( 7 )
		await store.create( { name: 'A', icon: null, position: here } )
		await store.create( { name: 'B', icon: null, position: here } )
		store.selected.value = store.labels.value[0]
		await store.remove( store.labels.value[0].id )
		expect( store.selected.value ).toBeNull()
		expect( store.labels.value.map( l => l.name ) ).toEqual( [ 'B' ] )
		await store.removeAll()
		expect( store.labels.value ).toEqual( [] )
	} )
} )
