<script setup>
defineProps({label:{type:String,default:'Loading…'}});
</script>
<template><span class="busy-feedback" role="status" aria-live="polite"><span class="busy-dot" aria-hidden="true"></span>{{label}}</span></template>
