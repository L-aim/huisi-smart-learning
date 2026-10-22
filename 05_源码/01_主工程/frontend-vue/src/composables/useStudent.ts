import { computed, ref, watch } from 'vue'

const key = 'las_student_id'
const majorKey = 'las_major'
const goalsKey = 'las_goals'

function createLearnerId() {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `learner-${suffix}`
}

const storedStudentId = localStorage.getItem(key)
// 默认给每位访客一个独立学号（不共享数据）；但允许显式切到演示学生 demo——
// 以前这里会把 'demo' 直接换掉，导致演示数据在界面上永远够不着。
const initialStudentId = storedStudentId || createLearnerId()
localStorage.setItem(key, initialStudentId)

const studentId = ref(initialStudentId)
const major = ref(localStorage.getItem(majorKey) || '')
const goals = ref(localStorage.getItem(goalsKey) || '')

watch(studentId, (v) => localStorage.setItem(key, v))
watch(major, (v) => localStorage.setItem(majorKey, v))
watch(goals, (v) => localStorage.setItem(goalsKey, v))

export function useStudent() {
  return {
    studentId,
    major,
    goals,
    ready: computed(() => Boolean(studentId.value.trim())),
  }
}

export const DEMO_STUDENT_ID = 'demo'

/** 切到演示学生（后端有完整项目/路径/错题数据），切完刷新页面让各页重新取数。 */
export function switchToDemoStudent() {
  studentId.value = DEMO_STUDENT_ID
  localStorage.setItem(key, DEMO_STUDENT_ID)
}

/** 切回一个全新的个人学号（恢复“每个访客独立数据”的默认行为）。 */
export function switchToOwnStudent() {
  const next = createLearnerId()
  studentId.value = next
  localStorage.setItem(key, next)
}

