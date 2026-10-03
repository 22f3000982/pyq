<script setup>
import {ref,onMounted,computed} from 'vue';
import {BookOpen,LayoutDashboard,History,Bookmark,Target,ShieldCheck,Search,ArrowUpRight,GraduationCap,LogOut} from 'lucide-vue-next';
import {api,session,loadSession,go} from './api';
import About from './About.vue';
import Catalog from './Catalog.vue';import ExamBrowser from './ExamBrowser.vue';import Exam from './Exam.vue';import Records from './Records.vue';import Admin from './Admin.vue';
const theme=ref(localStorage.getItem('pyq-theme')||'light');
document.documentElement.dataset.theme=theme.value;
function toggleTheme(){theme.value=theme.value==='dark'?'light':'dark';document.documentElement.dataset.theme=theme.value;localStorage.setItem('pyq-theme',theme.value)}
const route=ref(location.hash.slice(1)||'/');window.addEventListener('hashchange',()=>{route.value=location.hash.slice(1)||'/';window.scrollTo(0,0)});
const busy=ref(true),error=ref(''),auth=ref({name:'',email:'',password:''}),authBusy=ref(false);
const examPage=computed(()=>route.value.startsWith('/attempt/'));
onMounted(async()=>{try{await loadSession()}catch(e){error.value=e.message}finally{busy.value=false}});
async function authenticate(){authBusy.value=true;error.value='';try{const d=await api('/auth/login',{method:'POST',body:auth.value});session.user=d.user;auth.value.password='';go('/admin')}catch(e){error.value=e.message}finally{authBusy.value=false}}
async function logout(){await api('/auth/logout',{method:'POST'});await loadSession();go('/')}
const nav=[['/','Home',BookOpen],['/progress','My progress',LayoutDashboard],['/bookmarks','Bookmarks',Bookmark],['/about','About MauryaHub',BookOpen]];
</script>
<template>
<button class="theme-toggle btn btn-light btn-sm" @click="toggleTheme" :aria-label="'Switch to '+(theme==='dark'?'light':'dark')+' theme'">{{theme==='dark'?'☀ Light':'☾ Dark'}}</button>
<div class="app-shell" :class="{'exam-shell':examPage}">
<aside v-if="!examPage" class="sidebar"><a href="#/" class="brand"><span class="brand-mark"><BookOpen :size="23"/></span><span>Maurya<span class="brand-light">Hub</span><small>PYQ PRACTICE</small></span></a><div class="nav-caption">YOUR WORKSPACE</div><nav><a v-for="[path,label,Icon] in nav" :href="'#'+path" :class="{active:route===path}"><component :is="Icon" :size="19"/>{{label}}</a><a v-if="session.user?.role==='ADMIN'" href="#/admin" :class="{active:route.startsWith('/admin')}"><ShieldCheck :size="19"/>Administration / Upload PYQ</a></nav><div class="sidebar-bottom"><a href="https://mauryahub.onrender.com/">← Back to MauryaHub</a></div></aside>
<div class="workspace"><header v-if="!examPage" class="topbar"><span class="top-context">IITM BS <span>/</span> Previous-year papers</span><div class="account" v-if="session.user?.role==='ADMIN'"><span class="avatar">{{session.user.name.slice(0,1)}}</span><span>{{session.user.name}}</span><button @click="logout" aria-label="Log out" class="icon-btn"><LogOut :size="17"/></button></div></header>
<main :class="{'exam-main':examPage}"><p v-if="session.storageWarning" class="alert alert-warning" role="alert">{{session.storageWarning}}</p><div v-if="error" class="alert alert-danger" role="alert">{{error}}<button class="text-btn float-end" @click="error=''">Dismiss</button></div><p v-if="busy">Loading your workspace…</p>
<section v-else-if="['/admin/login','/login'].includes(route)" class="auth-panel panel"><div class="eyebrow">ADMINISTRATION</div><h1>Admin sign in</h1><p class="muted">Manage papers, source catalog and processing.</p><form @submit.prevent="authenticate"><label>Email<input class="form-control" type="email" v-model="auth.email" required autocomplete="username"></label><label>Password<input class="form-control" type="password" v-model="auth.password" required maxlength="128" autocomplete="current-password"></label><button class="btn btn-primary w-100 mt-4" :disabled="authBusy">{{authBusy?'Please wait…':'Sign in as admin'}}</button></form><a href="#/" class="text-btn mt-4">Back to papers</a></section>
<section v-else-if="route.startsWith('/admin')&&session.user?.role!=='ADMIN'" class="empty panel"><h1>Administrator access</h1><a href="#/admin/login" class="btn btn-primary">Admin sign in</a></section>
<Exam v-else-if="examPage" :id="Number(route.split('/')[2])" :key="route"/>
<About v-else-if="route==='/about'"/>
<Admin v-else-if="route.startsWith('/admin')"/>
<Records v-else-if="['/progress','/history','/dashboard','/bookmarks','/mistakes'].includes(route)||route.startsWith('/result/')" :route="route" :key="route"/>
<ExamBrowser v-else-if="route.startsWith('/exam/')" :route="route" :key="route"/><Catalog v-else :route="route" :key="route"/>
</main><footer v-if="!examPage">MauryaHub · PYQ Practice <a href="#/about">About</a></footer></div></div>
</template>
