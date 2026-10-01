<script setup>
import {ref,onMounted,computed} from 'vue';
import {BookOpen,LayoutDashboard,History,Bookmark,Target,ShieldCheck,Search,ArrowUpRight,GraduationCap,LogOut} from 'lucide-vue-next';
import {api,session,loadSession,go} from './api';
import Catalog from './Catalog.vue';import ExamBrowser from './ExamBrowser.vue';import Exam from './Exam.vue';import Records from './Records.vue';import Admin from './Admin.vue';
let storedTheme;try{storedTheme=localStorage.getItem('pyq-theme')}catch{}
const theme=ref(storedTheme==='dark'?'dark':'light');
document.documentElement.dataset.theme=theme.value;
function toggleTheme(){theme.value=theme.value==='dark'?'light':'dark';document.documentElement.dataset.theme=theme.value;try{localStorage.setItem('pyq-theme',theme.value)}catch{}}
const route=ref(location.hash.slice(1)||'/');window.addEventListener('hashchange',()=>{route.value=location.hash.slice(1)||'/';window.scrollTo(0,0)});
const busy=ref(true),error=ref(''),auth=ref({name:'',email:'',password:''}),authBusy=ref(false),query=ref(''),results=ref(null);
const examPage=computed(()=>route.value.startsWith('/attempt/'));
onMounted(async()=>{try{await loadSession()}catch(e){error.value=e.message}finally{busy.value=false}});
async function authenticate(){authBusy.value=true;error.value='';try{const d=await api('/auth/login',{method:'POST',body:auth.value});session.user=d.user;auth.value.password='';go('/admin')}catch(e){error.value=e.message}finally{authBusy.value=false}}
async function logout(){await api('/auth/logout',{method:'POST'});await loadSession();go('/')}
async function search(){if(query.value.trim().length<2)return;results.value=await api('/search?q='+encodeURIComponent(query.value));}
const nav=[['/','Home',BookOpen],['/progress','My progress',LayoutDashboard],['/bookmarks','Bookmarks',Bookmark]];
</script>
<template>
<div class="theme-toolbar"><button class="theme-toggle btn btn-light btn-sm" @click="toggleTheme" :aria-label="'Switch to '+(theme==='dark'?'light':'dark')+' theme'">{{theme==='dark'?'☀ Light':'☾ Dark'}}</button></div>
<div class="app-shell" :class="{'exam-shell':examPage}">
<aside v-if="!examPage" class="sidebar"><a href="#/" class="brand"><span class="brand-mark"><BookOpen :size="23"/></span><span>PYQ<span class="brand-light">studio</span><small>THE PRACTICE LIBRARY</small></span></a><div class="nav-caption">YOUR WORKSPACE</div><nav><a v-for="[path,label,Icon] in nav" :href="'#'+path" :class="{active:route===path}"><component :is="Icon" :size="19"/>{{label}}</a><a v-if="session.user?.role==='ADMIN'" href="#/admin" :class="{active:route.startsWith('/admin')}"><ShieldCheck :size="19"/>Administration / Upload PYQ</a></nav><div class="sidebar-bottom"><GraduationCap :size="24"/><strong>One paper at a time.</strong><p>Build understanding through deliberate practice.</p><small>Independent learning platform.<br>Not affiliated with IIT Madras.</small></div></aside>
<div class="workspace"><header v-if="!examPage" class="topbar"><span class="top-context">IITM BS <span>/</span> Previous-year papers</span><form class="global-search" @submit.prevent="search"><Search :size="17"/><input v-model="query" aria-label="Global search" placeholder="Search courses, papers, questions…"><button type="submit" class="text-btn">Search</button></form><div class="account" v-if="session.user?.role==='ADMIN'"><span class="avatar">{{session.user.name.slice(0,1)}}</span><span>{{session.user.name}}</span><button @click="logout" aria-label="Log out" class="icon-btn"><LogOut :size="17"/></button></div></header>
<div v-if="results" class="search-results panel"><div class="section-row"><h3>Search results</h3><button @click="results=null" class="btn btn-light">Close</button></div><template v-for="type in ['courses','papers','questions']"><h4>{{type}}</h4><a v-for="r in results[type]" :href="'#/'+(type==='courses'?'course/'+r.id:'paper/'+(r.paper_id||r.id))" @click="results=null">{{r.name||r.text}}</a><p v-if="!results[type].length" class="muted">No matches</p></template></div>
<main :class="{'exam-main':examPage}"><p v-if="session.storageWarning" class="alert alert-warning" role="alert">{{session.storageWarning}}</p><div v-if="error" class="alert alert-danger" role="alert">{{error}}<button class="text-btn float-end" @click="error=''">Dismiss</button></div><p v-if="busy">Loading your workspace…</p>
<section v-else-if="['/admin/login','/login'].includes(route)" class="auth-panel panel"><div class="eyebrow">ADMINISTRATION</div><h1>Admin sign in</h1><p class="muted">Manage papers, source catalog and processing.</p><form @submit.prevent="authenticate"><label>Email<input class="form-control" type="email" v-model="auth.email" required autocomplete="username"></label><label>Password<input class="form-control" type="password" v-model="auth.password" required maxlength="128" autocomplete="current-password"></label><button class="btn btn-primary w-100 mt-4" :disabled="authBusy">{{authBusy?'Please wait…':'Sign in as admin'}}</button></form><a href="#/" class="text-btn mt-4">Back to papers</a></section>
<section v-else-if="route.startsWith('/admin')&&session.user?.role!=='ADMIN'" class="empty panel"><h1>Administrator access</h1><a href="#/admin/login" class="btn btn-primary">Admin sign in</a></section>
<Exam v-else-if="examPage" :id="Number(route.split('/')[2])" :key="route"/>
<Admin v-else-if="route.startsWith('/admin')"/>
<Records v-else-if="['/progress','/history','/dashboard','/bookmarks','/mistakes'].includes(route)||route.startsWith('/result/')" :route="route" :key="route"/>
<ExamBrowser v-else-if="route.startsWith('/exam/')" :route="route" :key="route"/><Catalog v-else :route="route" :key="route"/>
</main><footer v-if="!examPage">PYQ Studio <span>Thoughtful practice. Honest progress.</span></footer></div></div>
</template>
