import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './style.css'

// ponytail: 全量导入保持 MVP 配置最小；首包影响真实体验时再改为按需导入。
createApp(App).use(ElementPlus).use(router).mount('#app')
