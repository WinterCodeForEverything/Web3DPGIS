import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import type { User } from '@/api/types'

export const useAuth = defineStore( 'auth', () => {
	const user = ref<User | null>( null )
	const loaded = ref( false )

	async function load() {
		// also sets the CSRF cookie that every later write needs
		user.value = await api.me()
		loaded.value = true
	}

	async function login( login: string, password: string ) {
		user.value = await api.login( login, password )
	}

	async function register( username: string, email: string, password: string ) {
		user.value = await api.register( username, email, password )
	}

	async function logout() {
		await api.logout()
		user.value = null
		await api.me()   // fresh CSRF cookie for the next login
	}

	return { user, loaded, load, login, register, logout }
} )
