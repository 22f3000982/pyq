<script setup>
import {ref,onMounted} from 'vue';
import {api,session} from './api';
const page=ref(null),draft=ref({}),editing=ref(false),busy=ref(false),loading=ref(true),error=ref(''),message=ref(''),version=ref(Date.now());
async function load(){loading.value=true;error.value='';try{page.value=await api('/about')}catch(e){error.value=e.message}finally{loading.value=false}}onMounted(load);
function edit(){draft.value=Object.fromEntries(['headline','description','name','bio','contact_email'].map(k=>[k,page.value[k]]));editing.value=true;message.value=''}
async function save(){busy.value=true;error.value='';message.value='';try{page.value=await api('/admin/about',{method:'PUT',body:draft.value});editing.value=false;message.value='About page saved.'}catch(e){error.value=e.message}finally{busy.value=false}}
async function photo(e){const f=e.target.files?.[0];if(!f)return;if(f.size>5*1024*1024){error.value='Photo must be 5 MB or smaller.';e.target.value='';return}const form=new FormData();form.append('photo',f);await changePhoto('POST',form);e.target.value=''}
async function changePhoto(method,form){busy.value=true;error.value='';message.value='';try{page.value=await api('/admin/about/photo',{method,form});version.value=Date.now();message.value=method==='DELETE'?'Photo removed.':'Photo updated.'}catch(e){error.value=e.message}finally{busy.value=false}}
</script>
<template>
<section class="about-page" :aria-busy="busy||loading">
<div class="eyebrow">ABOUT MAURYAHUB</div>
<p v-if="error" class="alert alert-danger" role="alert">{{error}} <button v-if="!page&&!loading" class="text-btn" @click="load">Retry</button></p>
<p v-if="message" class="alert alert-success" role="status">{{message}}</p><p v-if="loading" role="status">Loading About…</p>
<template v-if="page">
<div class="section-row"><h1>MauryaHub <span class="muted">/ PYQ Practice</span></h1><button v-if="session.user?.role==='ADMIN'&&!editing" class="btn btn-primary" @click="edit">Edit About</button></div>
<form v-if="editing&&session.user?.role==='ADMIN'" class="panel about-editor" @submit.prevent="save"><h2>Edit About</h2><fieldset :disabled="busy">
<label>Headline<input class="form-control" v-model="draft.headline" maxlength="160" required></label>
<label>About this platform<textarea class="form-control" v-model="draft.description" maxlength="4000" rows="5" required></textarea></label>
<label>Public contact email<input class="form-control" type="email" v-model="draft.contact_email" maxlength="254" placeholder="For support and content removal requests"></label>
<label>Your name<input class="form-control" v-model="draft.name" maxlength="100" placeholder="Your public name"></label>
<label>Your introduction<textarea class="form-control" v-model="draft.bio" maxlength="2000" rows="4"></textarea></label>
<label>Profile photo<input class="form-control" type="file" accept="image/jpeg,image/png,image/webp" @change="photo"></label>
<p class="muted">JPG, PNG or WebP · up to 5 MB. Photo changes publish immediately; text publishes when you save.</p>
<button v-if="page.photo_url" class="btn btn-light" type="button" @click="changePhoto('DELETE')">Remove photo</button>
<div class="about-actions"><button class="btn btn-primary" type="submit">Save details</button><button class="btn btn-light" type="button" @click="editing=false">Cancel text changes</button></div></fieldset><p v-if="busy" role="status">Saving…</p></form>
<article v-else class="panel about-story"><h2>{{page.headline}}</h2><p class="about-copy">{{page.description}}</p><a class="btn btn-primary" href="#/">Explore papers →</a></article>
<section class="panel about-person"><img v-if="page.photo_url" :src="page.photo_url+'?v='+version" :alt="page.name||'MauryaHub creator'" width="160" height="160"><div><div class="eyebrow">BEHIND MAURYAHUB</div><h2>{{page.name||'A student initiative'}}</h2><p class="about-copy">{{page.bio}}</p><a href="https://mauryahub.onrender.com/">Visit MauryaHub ↗</a></div></section>
<div class="about-notes"><p><a href="/contact">Contact &amp; content removal requests</a></p><p>Found a formatting issue? Use <strong>Report Broken Format</strong> next to the question’s Bookmark button.</p><p>Independent student-built platform. Not affiliated with IIT Madras.</p></div>
</template></section>
</template>
<style scoped>
.about-page{max-width:980px;margin:auto}.about-page h1{font-size:clamp(1.6rem,4vw,2.3rem)}.about-page h1 span{font-weight:400}.about-story,.about-person,.about-editor{padding:clamp(20px,4vw,40px);margin-top:26px}.about-story h2{font-size:clamp(1.6rem,4vw,2.5rem);margin-bottom:20px}.about-copy{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}.about-story .btn{margin-top:12px}.about-person{display:flex;gap:30px;align-items:center}.about-person img{object-fit:cover;border-radius:24px;flex-shrink:0}.about-person h2{margin:12px 0}.about-notes{margin-top:30px;line-height:1.7}.about-editor label{display:block;margin:18px 0}.about-editor input,.about-editor textarea{margin-top:8px}.about-editor fieldset{border:0;padding:0;min-width:0}.about-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}@media(max-width:600px){.about-person{flex-direction:column;align-items:flex-start}.section-row{align-items:flex-start;gap:15px;flex-wrap:wrap}}
</style>
