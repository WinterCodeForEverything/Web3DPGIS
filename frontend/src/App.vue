<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const fullScreen = computed( () => route.name === 'viewer' )

async function logout() {
	await auth.logout()
	router.push( { name: 'models' } )
}
</script>

<template>
	<div class="app" :class="{ 'app--full': fullScreen }">
		<header class="topbar">
			<RouterLink to="/" class="brand">3DPGIS</RouterLink>
			<nav class="nav">
				<RouterLink to="/">Models</RouterLink>
				<RouterLink v-if="auth.user" to="/upload">Upload</RouterLink>
				<a href="/api/docs/" target="_blank" rel="noopener">API</a>
			</nav>
			<div class="account">
				<template v-if="auth.user">
					<span class="muted">{{ auth.user.username }}</span>
					<button class="link" @click="logout">Log out</button>
				</template>
				<template v-else>
					<RouterLink :to="{ name: 'login', query: { next: route.fullPath } }">Log in</RouterLink>
					<RouterLink to="/register" class="button">Sign up</RouterLink>
				</template>
			</div>
		</header>
		<main class="main">
			<RouterView />
		</main>
	</div>
</template>
