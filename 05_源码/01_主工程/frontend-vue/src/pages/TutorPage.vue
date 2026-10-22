<script setup lang="ts">
import { Camera, Mic2, ShieldCheck, Sparkles, Video } from 'lucide-vue-next'
import TutorRealtimeCall from '@/components/TutorRealtimeCall.vue'

const capabilities = [
  { icon: Camera, title: '双向视频课堂', copy: '启用本地摄像头，与数字人辅导老师保持同屏交流。' },
  { icon: Mic2, title: '实时语音交互', copy: '支持连续对话、随时打断与麦克风静音控制。' },
  { icon: ShieldCheck, title: '学习过程留痕', copy: '通话结束后保存对话证据，用于更新画像与后续推荐。' },
]
</script>

<template>
  <div class="competition-page tutor-video-page">
    <header class="tutor-video-hero">
      <div>
        <div class="competition-eyebrow"><Video :size="15" /> REALTIME AI TUTOR</div>
        <h1>实时视频辅导</h1>
        <p>与数字人老师面对面交流。系统会结合当前学习画像与课程证据，进行实时讲解和追问。</p>
      </div>
    </header>

    <section class="tutor-video-shell">
      <TutorRealtimeCall />
    </section>

    <section class="tutor-capability-strip" aria-label="实时辅导能力">
      <article v-for="item in capabilities" :key="item.title">
        <span class="tutor-capability-icon"><component :is="item.icon" :size="20" /></span>
        <div><strong>{{ item.title }}</strong><p>{{ item.copy }}</p></div>
      </article>
      <div class="tutor-capability-note"><Sparkles :size="17" /> 真实音视频与模型响应均由服务端配置驱动</div>
    </section>
  </div>
</template>
