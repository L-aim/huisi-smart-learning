<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, Cable, Cpu, Gauge, Network, Workflow } from 'lucide-vue-next'
import { apiGet, apiPost } from '@/utils/api'
import type { ApiResponse } from '@/utils/api'
import { useStudent } from '@/composables/useStudent'

type IntegrationItem = {
  key: string
  name: string
  from_teammate?: string
  current_module: string
  entry: string
  status: string
  value: string
}

// 接口返回的是「整份目录对象」，能力项在 capabilities 里；以前直接当数组渲染，
// 结果 v-for 遍历对象属性，页面上只剩一排空骨架。
type IntegrationCatalog = {
  source_folder?: string
  strategy?: string
  capabilities?: IntegrationItem[]
  supporting_mechanisms?: string[]
  not_imported?: string[]
}

type Evidence = {
  total?: number
  exercise_attempts?: number
  knowledge_nodes?: number
  resource_items?: number
  feedback_items?: number
  learning_events?: number
}

type EvaluationOverview = {
  score?: number
  mastery?: number
  accuracy?: number
  engagement?: number
  weak_points?: string[]
  evidence?: Evidence
  confidence?: { level?: string; label?: string; evidence_total?: number }
  dimensions?: Record<string, number>
}

type TraceStep = {
  index: number
  role: string
  tool: string
  handoff?: Record<string, unknown>
  failed?: boolean
}

type LiveCall = {
  at: string
  method: string
  path: string
  role: string
  tool: string
  handoff?: Record<string, unknown>
  status?: number
  ok?: boolean
}

type RuntimeTrace = {
  available: boolean
  hint?: string
  source?: string | null
  generated_at?: string | null
  student_id?: string | null
  role_name?: string | null
  runtime_ok?: boolean | null
  runtime_error?: { tool?: string; code?: string; message?: string } | null
  steps?: TraceStep[]
  live?: LiveCall[]
  live_total?: number
}

type MultiAgentWorker = { pid?: number | null; tools?: string[] }

type MultiAgentStep = {
  index: number
  role: string
  tool: string
  ok: boolean
  pid?: number | null
  elapsed_ms?: number
  handoff?: string
  error?: string
}

type MultiAgentRun = {
  available?: boolean
  runtime?: string
  ok?: boolean
  workers?: Record<string, MultiAgentWorker>
  steps?: MultiAgentStep[]
  stop_reason?: { tool?: string; code?: string; message?: string } | null
  missing_tools?: string[]
  hint?: string
}

const { studentId } = useStudent()

const catalog = ref<IntegrationItem[]>([])
const catalogStrategy = ref('')
const overview = ref<EvaluationOverview | null>(null)
const trace = ref<RuntimeTrace | null>(null)
const multiAgent = ref<MultiAgentRun | null>(null)
const multiAgentError = ref('')
const multiAgentNote = ref('')
const multiAgentLoading = ref(false)
const catalogError = ref('')
const overviewError = ref('')
const traceError = ref('')
const loading = ref(true)

const workerRows = computed(() => {
  const workers = multiAgent.value?.workers || {}
  return Object.entries(workers).map(([role, handle]) => ({ role, pid: handle.pid ?? null }))
})

const multiAgentPids = computed(() =>
  workerRows.value.map((row) => row.pid).filter((pid): pid is number => typeof pid === 'number'),
)

const multiAgentDistinct = computed(() => new Set(multiAgentPids.value).size)

const stages = [
  {
    key: 'intake',
    title: '需求澄清',
    module: 'backend/app/agents/orchestrator.py',
    entry: 'profile_chat',
    desc: '把学生的自然语言目标转成结构化需求单，记录课程、章节与薄弱点。',
  },
  {
    key: 'generate',
    title: '资源生成',
    module: 'backend/app/agents/orchestrator.py',
    entry: 'generate',
    desc: '按资源类型生成讲解文档、思维导图、题库、拓展阅读、代码案例与视频脚本。',
  },
  {
    key: 'practice',
    title: '练习诊断',
    module: 'backend/app/services/exercise_bank.py',
    entry: 'build_exercise_session / submit_exercise_answer',
    desc: '从题库资源出题、判定对错、累计错题与薄弱标签。',
  },
  {
    key: 'evaluate',
    title: '学习评估',
    module: 'backend/app/services/learning_state.py',
    entry: 'evaluation_overview',
    desc: '汇总练习、知识节点、资源、反馈与学习事件五类证据，输出掌握度、正确率与置信度。',
  },
  {
    key: 'path',
    title: '路径调整',
    module: 'backend/app/services/path_progress.py',
    entry: 'record_stage_answer / add_path_branch',
    desc: '按阶段目标判定晋级，必要时在当前阶段下新增知识补充分支。',
  },
]

const mcpTools = [
  { name: 'get_student_profile', use: '读取六维画像与学习摘要', write: false },
  { name: 'get_role_competency', use: '岗位能力矩阵与达标度', write: false },
  { name: 'get_project_status', use: '学习路径各阶段状态与掌握度', write: false },
  { name: 'search_knowledge', use: '课程资料检索并返回出处与相关度', write: false },
  { name: 'get_exercise_session', use: '按学生绑定的题库生成诊断练习', write: true },
  { name: 'submit_exercise_answer', use: '提交作答并返回判定与阶段进度', write: true },
  { name: 'get_wrong_book', use: '错题分组、能力雷达与薄弱标签', write: false },
  { name: 'get_learning_evaluation', use: '掌握度、正确率、证据构成与置信度', write: false },
  { name: 'add_learning_branch', use: '在路径节点下新增知识补充分支', write: true },
]

function percent(value: number | undefined | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return `${Math.round(value * 10) / 10}%`
}

function plain(value: number | undefined | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return String(Math.round(value * 10) / 10)
}

function evidenceRows(evidence: Evidence | undefined) {
  const source = evidence || {}
  return [
    { label: '练习作答', value: source.exercise_attempts },
    { label: '知识节点', value: source.knowledge_nodes },
    { label: '资源条目', value: source.resource_items },
    { label: '学习反馈', value: source.feedback_items },
    { label: '学习事件', value: source.learning_events },
  ]
}

async function loadCatalog() {
  try {
    const response = await apiGet<IntegrationCatalog>('/api/integration/teammate-catalog')
    const payload = response?.data
    catalog.value = Array.isArray(payload?.capabilities) ? payload.capabilities : []
    catalogStrategy.value = payload?.strategy || ''
    if (!catalog.value.length) {
      catalogError.value = '融合目录接口没有返回能力项（capabilities 为空）。'
    }
  } catch {
    catalogError.value = '融合目录读取失败，请确认后端 /api/integration/teammate-catalog 可访问。'
  }
}

async function loadOverview() {
  try {
    const sid = encodeURIComponent(studentId.value || 'demo')
    const response = await apiGet<EvaluationOverview>(`/api/evaluate/overview?student_id=${sid}`)
    overview.value = response?.data || null
  } catch {
    overviewError.value = '评测指标读取失败，请确认后端 /api/evaluate/overview 可访问。'
  }
}

async function loadTrace() {
  try {
    const response = await apiGet<RuntimeTrace>('/api/orchestration/trace')
    trace.value = response?.data || null
  } catch {
    traceError.value = '运行期记录读取失败，请确认后端 /api/orchestration/trace 可访问。'
  }
}

// 整链步骤与真实调用都只有 handoff 这一个共同字段，所以按结构取参数，不绑死类型。
function handoffText(step: { handoff?: Record<string, unknown> }): string {
  const entries = Object.entries(step.handoff || {})
  if (!entries.length) return '—'
  return entries.map(([key, value]) => `${key}=${String(value)}`).join('，')
}

async function postMultiAgent(sid: string): Promise<ApiResponse<MultiAgentRun>> {
  return apiPost<MultiAgentRun>('/api/orchestration/multi-agent', {
    student_id: sid,
    role_name: '前端开发工程师',
    answer: 'B',
    timeout_seconds: 180,
  })
}

async function runMultiAgent() {
  multiAgentLoading.value = true
  multiAgentError.value = ''
  multiAgentNote.value = ''
  try {
    const sid = studentId.value || 'demo'
    let response = await postMultiAgent(sid)
    const failCode =
      response?.error?.code || (response?.data?.stop_reason as { code?: string } | undefined)?.code || ''
    // 演示学生 demo 一定有项目数据；其它学生若没有数据，自动改用 demo 重跑一次并把这件事说出来
    if (response?.success === false && failCode === 'STUDENT_NOT_FOUND' && sid !== 'demo') {
      multiAgentNote.value = `学生 ${sid} 在后端没有项目数据，已自动改用 demo 学生重跑。`
      response = await postMultiAgent('demo')
    }
    multiAgent.value = response?.data || null
    if (response?.success === false) {
      const stop = response?.data?.stop_reason as { code?: string; message?: string } | undefined
      const code = response?.error?.code || stop?.code || ''
      const message = response?.error?.message || stop?.message || '接口没有返回失败原因'
      multiAgentError.value = code ? `${code}：${message}` : message
    } else if (response?.data?.available === false) {
      multiAgentError.value =
        response?.data?.hint ||
        `注册表缺工具：${(response?.data?.missing_tools || []).join(', ') || '未知'}`
    }
  } catch {
    multiAgentError.value = '多进程编排接口调用失败，请确认后端 /api/orchestration/multi-agent 已启动。'
  } finally {
    multiAgentLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadCatalog(), loadOverview(), loadTrace()])
  loading.value = false
})
</script>

<template>
  <div class="competition-page orchestration-page">
    <header class="orchestration-hero">
      <div>
        <div class="competition-eyebrow"><Workflow :size="15" /> AGENTARTS × MCP RUNTIME</div>
        <h1>编排可视化</h1>
        <p>
          本页把「多智能体协同」从文案变成可核对的模块与调用链：每个阶段都对应仓库里的真实模块与入口函数，
          MCP 工具与华为云运行时同样给出契约级信息，不展示任何未经接口返回的数字。
        </p>
      </div>
    </header>

    <section class="orchestration-section" aria-label="Agent 拓扑">
      <div class="orchestration-section-head">
        <h2><Cpu :size="18" /> Agent 拓扑</h2>
        <span>五个阶段，模块路径与入口函数均可直接检索</span>
      </div>
      <ol class="orchestration-flow">
        <li v-for="(stage, index) in stages" :key="stage.key">
          <span class="orchestration-step">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="orchestration-stage-body">
            <strong>{{ stage.title }}</strong>
            <p>{{ stage.desc }}</p>
            <code>{{ stage.module }}</code>
            <code>{{ stage.entry }}</code>
          </div>
        </li>
      </ol>
    </section>

    <section class="orchestration-section" aria-label="MCP 工具契约">
      <div class="orchestration-section-head">
        <h2><Cable :size="18" /> MCP 工具契约</h2>
        <span>9 个工具，云端运行时统一以 Streamable HTTP 暴露 /mcp</span>
      </div>
      <div class="orchestration-tool-grid">
        <article v-for="tool in mcpTools" :key="tool.name" :class="{ 'is-write': tool.write }">
          <code>{{ tool.name }}</code>
          <p>{{ tool.use }}</p>
          <span>{{ tool.write ? '写操作' : '读操作' }}</span>
        </article>
      </div>
      <p class="orchestration-note">
        以上为契约定义（见 API_CONTRACT_AGENTARTS.md v1.1），不是实时调用记录。健康检查端点 <code>/healthz</code>
        在运行时内返回服务版本、鉴权方式与限流配置，平台网关仅转发 <code>/mcp</code>。
      </p>
    </section>

    <section class="orchestration-section" aria-label="评测指标">
      <div class="orchestration-section-head">
        <h2><Gauge :size="18" /> 评测指标</h2>
        <span>数据来源 /api/evaluate/overview，学生 {{ studentId || 'demo' }}</span>
      </div>

      <p v-if="loading" class="orchestration-note">正在读取指标…</p>
      <p v-else-if="overviewError" class="orchestration-error">{{ overviewError }}</p>

      <div v-else class="orchestration-metrics">
        <article>
          <span>综合评分</span>
          <strong>{{ plain(overview?.score) }}</strong>
        </article>
        <article>
          <span>知识掌握</span>
          <strong>{{ percent(overview?.mastery) }}</strong>
        </article>
        <article>
          <span>练习正确率</span>
          <strong>{{ percent(overview?.accuracy) }}</strong>
        </article>
        <article>
          <span>学习投入</span>
          <strong>{{ plain(overview?.engagement) }}</strong>
        </article>
        <article>
          <span>结论置信度</span>
          <strong>{{ overview?.confidence?.label || '—' }}</strong>
        </article>
        <article>
          <span>证据总数</span>
          <strong>{{ overview?.evidence?.total ?? '—' }}</strong>
        </article>
      </div>

      <div v-if="!loading && !overviewError" class="orchestration-evidence">
        <div v-for="row in evidenceRows(overview?.evidence)" :key="row.label">
          <span>{{ row.label }}</span>
          <strong>{{ row.value ?? 0 }}</strong>
        </div>
      </div>

      <p v-if="!loading && !overviewError && overview?.weak_points?.length" class="orchestration-note">
        薄弱标签：{{ overview?.weak_points?.join('、') }}
      </p>
    </section>

    <section class="orchestration-section" aria-label="能力融合目录">
      <div class="orchestration-section-head">
        <h2><Network :size="18" /> 能力融合目录</h2>
        <span>数据来源 /api/integration/teammate-catalog</span>
      </div>
      <p v-if="catalogStrategy" class="orchestration-note">{{ catalogStrategy }}</p>
      <p v-if="catalogError" class="orchestration-error">{{ catalogError }}</p>
      <ul v-else class="orchestration-catalog">
        <li v-for="item in catalog" :key="item.key">
          <div>
            <strong>{{ item.name }}</strong>
            <span>{{ item.status }}</span>
          </div>
          <p>{{ item.value }}</p>
          <code>{{ item.current_module }}</code>
        </li>
      </ul>
    </section>

    <section class="orchestration-section" aria-label="运行期编排记录">
      <div class="orchestration-section-head">
        <h2><Workflow :size="18" /> 最近一次九步编排（运行期记录）</h2>
        <span>数据来源 /api/orchestration/trace</span>
      </div>
      <p v-if="traceError" class="orchestration-error">{{ traceError }}</p>
      <template v-else-if="trace && !trace.available">
        <p class="orchestration-note">{{ trace.hint }}</p>
      </template>
      <template v-else-if="trace && trace.available">
        <p class="orchestration-note">
          生成时间 {{ trace.generated_at || '—' }} · 学生 {{ trace.student_id || '—' }} ·
          岗位 {{ trace.role_name || '未指定（第 0 步按设计跳过）' }} ·
          结果
          <strong :class="trace.runtime_ok ? 'is-ok' : 'is-fail'">
            {{ trace.runtime_ok ? '全步通过' : '中途中止' }}
          </strong>
        </p>
        <p v-if="trace.runtime_error" class="orchestration-error">
          中止于 {{ trace.runtime_error.tool }} —— {{ trace.runtime_error.code }}：{{ trace.runtime_error.message }}
        </p>
        <ol class="orchestration-trace">
          <li v-for="step in trace.steps" :key="step.index" :class="{ 'is-failed': step.failed }">
            <span class="orchestration-trace-index">{{ step.index }}</span>
            <div>
              <strong>{{ step.role }}</strong>
              <code>{{ step.tool }}</code>
              <p>{{ handoffText(step) }}</p>
            </div>
          </li>
        </ol>
      </template>
      <p v-else class="orchestration-note">正在读取运行期记录…</p>
    </section>

    <section class="orchestration-section" aria-label="真实操作留痕">
      <div class="orchestration-section-head">
        <h2><Workflow :size="18" /> 真实操作留痕（自动记录）</h2>
        <span>数据来源 /api/orchestration/trace 的 live 段</span>
      </div>
      <p class="orchestration-note">
        每次真实接口操作命中「后端路由 → MCP 工具」映射都会被记下来，环形保留最近
        {{ trace?.live_total ?? 0 }} 条，这里显示最新的 {{ trace?.live?.length ?? 0 }} 条。
      </p>
      <ol v-if="trace?.live?.length" class="orchestration-trace">
        <li
          v-for="(call, index) in trace.live"
          :key="`${call.at}-${index}`"
          :class="{ 'is-failed': call.ok === false }"
        >
          <span class="orchestration-trace-index">{{ index + 1 }}</span>
          <div>
            <strong>{{ call.role }}</strong>
            <code>{{ call.tool }}</code>
            <p>
              {{ call.method }} {{ call.path }} · HTTP {{ call.status }} ·
              {{ handoffText(call) }}
            </p>
          </div>
        </li>
      </ol>
      <p v-else class="orchestration-note">
        还没有真实操作记录。在本站点做一次「出题 / 提交答案 / 查看评估 / 加分支」，这里就会出现对应的工具与传值。
      </p>
    </section>

    <section class="orchestration-section" aria-label="真实多进程角色编排">
      <div class="orchestration-section-head">
        <h2><Network :size="18" /> 真实多进程角色编排</h2>
        <span>数据来源 POST /api/orchestration/multi-agent</span>
      </div>
      <p class="orchestration-note">
        点下去会真的起 7 个操作系统进程：一个角色一个进程，主控只做调度与跨步传值，工具经队列消息调用。
        下面的 pid 是子进程自己上报的——如果几个角色 pid 相同，就说明它们是同一个执行体，分工不成立。
      </p>
      <button type="button" class="orchestration-run" :disabled="multiAgentLoading" @click="runMultiAgent">
        {{ multiAgentLoading ? '正在起进程…' : '跑一次多进程编排' }}
      </button>
      <p v-if="multiAgentNote" class="orchestration-note">{{ multiAgentNote }}</p>
      <p v-if="multiAgentError" class="orchestration-error">{{ multiAgentError }}</p>
      <template v-if="multiAgent">
        <p class="orchestration-note">
          结果
          <strong :class="multiAgent.ok ? 'is-ok' : 'is-fail'">
            {{ multiAgent.ok ? '九步全通' : '中途中止' }}
          </strong>
          · 角色进程 {{ workerRows.length }} 个（互不相同的 pid {{ multiAgentDistinct }} 个）
          · 步骤 {{ (multiAgent.steps || []).filter((step) => step.ok).length }}/{{ (multiAgent.steps || []).length }}
        </p>
        <ul class="orchestration-workers">
          <li v-for="row in workerRows" :key="row.role">
            <strong>{{ row.role }}</strong>
            <code>pid {{ row.pid ?? '—' }}</code>
          </li>
        </ul>
        <p v-if="multiAgent.stop_reason?.code" class="orchestration-error">
          中止于 {{ multiAgent.stop_reason?.tool }} —— {{ multiAgent.stop_reason?.code }}：{{ multiAgent.stop_reason?.message }}
        </p>
        <ol class="orchestration-trace">
          <li v-for="step in multiAgent.steps" :key="step.index" :class="{ 'is-failed': !step.ok }">
            <span class="orchestration-trace-index">{{ step.index + 1 }}</span>
            <div>
              <strong>{{ step.role }}</strong>
              <code>{{ step.tool }}</code>
              <p>pid {{ step.pid ?? '—' }} · {{ step.handoff || step.error || '—' }}</p>
            </div>
          </li>
        </ol>
      </template>
      <p v-if="!multiAgent && !multiAgentError" class="orchestration-note">尚未运行。这一步不做缓存，每次点击都是一次真实的进程编排。</p>
    </section>

    <footer class="orchestration-footer">
      <Activity :size="16" />
      <span>页面只读取后端真实接口；接口不可用时会直接显示错误，不用占位数据掩盖。</span>
    </footer>
  </div>
</template>

<style scoped>
.orchestration-page {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.orchestration-hero h1 {
  margin: 6px 0 8px;
  font-size: 28px;
}

.orchestration-hero p {
  max-width: 780px;
  color: var(--text-muted, #55637a);
  line-height: 1.7;
}

.orchestration-section {
  border: 1px solid var(--border-soft, rgba(15, 32, 68, 0.12));
  border-radius: 18px;
  padding: 18px 20px;
  background: var(--surface, #fff);
}

.orchestration-section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}

.orchestration-section-head h2 {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 17px;
}

.orchestration-section-head span {
  font-size: 12px;
  color: var(--text-muted, #6b7891);
}

.orchestration-flow {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.orchestration-flow li {
  display: flex;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--surface-soft, #f6f8fc);
}

.orchestration-step {
  flex: 0 0 auto;
  font-weight: 700;
  color: var(--accent, #1f6feb);
}

.orchestration-stage-body {
  display: grid;
  gap: 4px;
}

.orchestration-stage-body p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted, #55637a);
}

.orchestration-stage-body code {
  font-size: 12px;
  color: var(--text-muted, #6b7891);
}

.orchestration-tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(228px, 1fr));
  gap: 10px;
}

.orchestration-tool-grid article {
  border: 1px solid var(--border-soft, rgba(15, 32, 68, 0.12));
  border-radius: 12px;
  padding: 10px 12px;
  display: grid;
  gap: 6px;
}

.orchestration-tool-grid article.is-write {
  border-color: rgba(31, 111, 235, 0.35);
}

.orchestration-tool-grid p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted, #55637a);
}

.orchestration-tool-grid span {
  font-size: 11.5px;
  color: var(--text-muted, #6b7891);
}

.orchestration-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.orchestration-metrics article {
  border-radius: 12px;
  padding: 12px;
  background: var(--surface-soft, #f6f8fc);
  display: grid;
  gap: 6px;
}

.orchestration-metrics span {
  font-size: 12px;
  color: var(--text-muted, #6b7891);
}

.orchestration-metrics strong {
  font-size: 20px;
}

.orchestration-evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.orchestration-evidence div {
  border-radius: 999px;
  padding: 6px 12px;
  background: var(--surface-soft, #f1f4fa);
  font-size: 12px;
  display: inline-flex;
  gap: 6px;
}

.orchestration-catalog {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.orchestration-catalog li {
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--surface-soft, #f6f8fc);
  display: grid;
  gap: 5px;
}

.orchestration-catalog div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.orchestration-catalog span {
  font-size: 12px;
  color: var(--accent, #1f6feb);
}

.orchestration-catalog p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-muted, #55637a);
}

.orchestration-catalog code {
  font-size: 11.5px;
  color: var(--text-muted, #6b7891);
}

.orchestration-note {
  margin: 12px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-muted, #6b7891);
}

.orchestration-error {
  margin: 0;
  font-size: 13px;
  color: #b42318;
}

.orchestration-trace {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.orchestration-trace li {
  display: flex;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle, #e6eaf2);
  background: var(--surface-muted, #f8fafc);
}

.orchestration-trace li.is-failed {
  border-color: #f3c1bb;
  background: #fff6f5;
}

.orchestration-trace-index {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11.5px;
  font-weight: 600;
  color: #fff;
  background: var(--accent, #3b6ef5);
}

.orchestration-trace li.is-failed .orchestration-trace-index {
  background: #b42318;
}

.orchestration-trace div {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}

.orchestration-trace strong {
  font-size: 13px;
}

.orchestration-trace code {
  font-size: 11.5px;
  padding: 2px 6px;
  border-radius: 6px;
  background: #eef2fb;
  color: #2f4a80;
}

.orchestration-trace p {
  flex-basis: 100%;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted, #6b7891);
}

.orchestration-note .is-ok {
  color: #0f7b3f;
}

.orchestration-note .is-fail {
  color: #b42318;
}

.orchestration-run {
  align-self: flex-start;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid var(--border-strong, #cdd5e3);
  background: var(--surface-raised, #fff);
  color: inherit;
  font-size: 13px;
  cursor: pointer;
}

.orchestration-run:disabled {
  cursor: progress;
  opacity: 0.6;
}

.orchestration-workers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
  padding: 0;
  list-style: none;
}

.orchestration-workers li {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-sunken, #f4f6fa);
  font-size: 12px;
}

.orchestration-workers code {
  color: var(--text-muted, #6b7891);
}

.orchestration-footer {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-muted, #6b7891);
}
</style>
