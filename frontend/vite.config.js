import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({plugins:[vue()],build:{manifest:true,rollupOptions:{input:{app:'index.html',study:'src/study.js'}}},server:{proxy:{'/api':'http://127.0.0.1:5000'}}});
