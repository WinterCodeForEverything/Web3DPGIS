import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './stores/auth'
import { viewerFromQuery } from './viewers'

export const router = createRouter( {
	history: createWebHistory(),
	routes: [
		{ path: '/', name: 'models', component: () => import( './views/ModelsView.vue' ) },
		{ path: '/login', name: 'login', component: () => import( './views/LoginView.vue' ) },
		{ path: '/register', name: 'register', component: () => import( './views/RegisterView.vue' ) },
		{ path: '/upload', name: 'upload', component: () => import( './views/UploadView.vue' ), meta: { requiresAuth: true } },
		{ path: '/models/:id', name: 'viewer', component: () => import( './views/ModelPage.vue' ), props: route => ( { id: Number( route.params.id ), viewer: viewerFromQuery( route.query.viewer ) } ) },
		{ path: '/:pathMatch(.*)*', redirect: '/' },
	],
} )

router.beforeEach( async to => {
	const auth = useAuth()
	if ( !auth.loaded ) await auth.load()
	if ( to.meta.requiresAuth && !auth.user ) return { name: 'login', query: { next: to.fullPath } }
} )
