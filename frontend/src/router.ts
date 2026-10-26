import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './stores/auth'
import { viewerFromQuery } from './viewerChoice'

export const router = createRouter( {
	history: createWebHistory(),
	routes: [
		{ path: '/', name: 'models', component: () => import( './views/ModelListView.vue' ) },
		{ path: '/login', name: 'login', component: () => import( './views/LoginView.vue' ) },
		{ path: '/register', name: 'register', component: () => import( './views/RegisterView.vue' ) },
		{ path: '/upload', name: 'upload', component: () => import( './views/UploadView.vue' ), meta: { requiresAuth: true } },
		{ path: '/reconstruct', name: 'reconstruct', component: () => import( './reconstruction/NewReconstructionView.vue' ), meta: { requiresAuth: true } },
		{ path: '/reconstructions/:id', name: 'reconstruction', component: () => import( './reconstruction/ReconstructionView.vue' ), meta: { requiresAuth: true },
			props: route => ( { id: Number( route.params.id ) } ) },
		{ path: '/models/:id', name: 'viewer', component: () => import( './views/ViewerSwitchPage.vue' ), props: route => ( { id: Number( route.params.id ), viewer: viewerFromQuery( route.query.viewer ) } ) },
		{ path: '/:pathMatch(.*)*', redirect: '/' },
	],
} )

router.beforeEach( async to => {
	const auth = useAuth()
	if ( !auth.loaded ) await auth.load()
	if ( to.meta.requiresAuth && !auth.user ) return { name: 'login', query: { next: to.fullPath } }
} )
