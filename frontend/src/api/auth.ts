// Signing up, in and out: /api/v1/auth/…
import { request } from './http'
import type { User } from './types'

export const authApi = {
	me: () => request<User | null>( 'GET', '/auth/me/' ),
	login: ( login: string, password: string ) => request<User>( 'POST', '/auth/login/', { login, password } ),
	register: ( username: string, email: string, password: string ) => request<User>( 'POST', '/auth/register/', { username, email, password } ),
	logout: () => request<void>( 'POST', '/auth/logout/' ),
}
