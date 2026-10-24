// 3D models and their processing jobs: /api/v1/models/, /api/v1/jobs/
import { query, request, upload } from './http'
import type { Job, Model3D, Page } from './types'

export const modelsApi = {
	models: ( params: { search?: string; mine?: boolean; near?: string; radius?: number; bbox?: string; page?: number } = {} ) =>
		request<Page<Model3D>>( 'GET', '/models/' + query( params ) ),
	model: ( id: number ) => request<Model3D>( 'GET', `/models/${id}/` ),
	updateModel: ( id: number, changes: Partial<Pick<Model3D, 'name' | 'is_public' | 'is_visible' | 'height_offset'>> ) =>
		request<Model3D>( 'PATCH', `/models/${id}/`, changes ),
	deleteModel: ( id: number ) => request<void>( 'DELETE', `/models/${id}/` ),
	reprocess: ( id: number ) => request<Job>( 'POST', `/models/${id}/reprocess/` ),
	uploadModel: ( form: FormData, onProgress: ( f: number ) => void ) => upload<Model3D>( '/models/', form, onProgress ),
	job: ( id: number ) => request<Job>( 'GET', `/jobs/${id}/` ),
}
