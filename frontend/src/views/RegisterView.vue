<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const router = useRouter()
const form = reactive( { username: '', email: '', password: '', confirm: '' } )
const errors = reactive<Record<string, string>>( {} )
const busy = ref( false )

async function submit() {
	for ( const key of Object.keys( errors ) ) delete errors[key]
	if ( form.password !== form.confirm ) {
		errors.confirm = 'Passwords do not match.'
		return
	}
	busy.value = true
	try {
		await auth.register( form.username.trim(), form.email.trim(), form.password )
		router.push( '/' )
	} catch ( e ) {
		if ( e instanceof ApiError ) {
			for ( const key of [ 'username', 'email', 'password' ] ) errors[key] = e.field( key )
			errors.form = e.field( 'non_field_errors' ) || ( errors.username || errors.email || errors.password ? '' : e.message )
		} else {
			errors.form = String( e )
		}
	} finally {
		busy.value = false
	}
}
</script>

<template>
	<div class="narrow card">
		<h1>Create an account</h1>
		<form @submit.prevent="submit">
			<label class="field">Username
				<input v-model="form.username" autocomplete="username" required autofocus />
				<span v-if="errors.username" class="error">{{ errors.username }}</span>
			</label>
			<label class="field">Email
				<input v-model="form.email" type="email" autocomplete="email" required />
				<span v-if="errors.email" class="error">{{ errors.email }}</span>
			</label>
			<label class="field">Password
				<input v-model="form.password" type="password" autocomplete="new-password" required />
				<span v-if="errors.password" class="error">{{ errors.password }}</span>
			</label>
			<label class="field">Confirm password
				<input v-model="form.confirm" type="password" autocomplete="new-password" required />
				<span v-if="errors.confirm" class="error">{{ errors.confirm }}</span>
			</label>
			<p v-if="errors.form" class="error" role="alert">{{ errors.form }}</p>
			<div class="row">
				<button class="primary" :disabled="busy">Sign up</button>
				<span class="spacer" />
				<RouterLink to="/login">I have an account</RouterLink>
			</div>
		</form>
	</div>
</template>
