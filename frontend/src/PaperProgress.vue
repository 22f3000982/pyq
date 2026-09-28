<script setup>
defineProps({progress:Object});
</script>
<template><p v-if="progress?.attempted" class="paper-progress small" role="status"><template v-if="progress.last_score!==null&&progress.last_score!==undefined">You already attempted this QP and scored {{Number(progress.last_score).toFixed(1)}}%.</template><template v-else>You already attempted this QP. Score unavailable because source grading is incomplete.</template></p></template>
