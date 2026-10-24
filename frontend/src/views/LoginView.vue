<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const login = ref( '' )
const password = ref( '' )
const error = ref( '' )
const busy = ref( false )

async function submit() {
	busy.value = true
	error.value = ''
	try {
		await auth.login( login.value.trim(), password.value )
		router.push( typeof route.query.next === 'string' && route.query.next.startsWith( '/' ) ? route.query.next : '/' )
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
	} finally {
		busy.value = false
	}
}
</script>

<template>
	<div class="narrow card">
		<h1>Log in</h1>
		<form @submit.prevent="submit">
			<label class="field">Username or email
				<input v-model="login" autocomplete="username" required autofocus />
			</label>
			<label class="field">Password
				<input v-model="password" type="password" autocomplete="current-password" required />
			</label>
			<p v-if="error" class="error" role="alert">{{ error }}</p>
			<div class="row">
				<button class="primary" :disabled="busy">Log in</button>
				<span class="spacer" />
				<RouterLink to="/register">Create an account</RouterLink>
			</div>
		</form>
	</div>
</template>
