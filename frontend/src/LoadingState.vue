<script setup>
defineProps({title:{type:String,default:'Preparing your exam…'},description:{type:String,default:'Loading questions and setting up your session.'}});
</script>
<template><section class="loading-state panel" role="status" aria-live="polite" aria-busy="true"><span class="loading-spinner" aria-hidden="true"></span><h2>{{title}}</h2><p class="muted">{{description}}</p><progress aria-label="Loading content"></progress><div class="loading-skeleton" aria-hidden="true"><span></span><span></span><span></span></div></section></template>
