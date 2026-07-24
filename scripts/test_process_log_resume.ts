/**
 * Run: npx --yes tsx scripts/test_process_log_resume.ts
 */
import {
  extractReplyFromSnapshot,
  shouldResumeInProgress,
} from '../frontend/src/utils/processLogResume'
import type { ProcessLogSnapshot } from '../frontend/src/api/client'

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const inProgress: ProcessLogSnapshot = {
  in_progress: true,
  done: false,
  content: '正在分析…',
  steps: [{ kind: 'tool', title: '口袋预测', status: 'running', name: '口袋预测' }],
  reply: '',
  log_offset: 0,
}

assert(shouldResumeInProgress(inProgress, true), 'awaiting reply + in progress resumes')

const doneSnap: ProcessLogSnapshot = {
  in_progress: false,
  done: true,
  content: '## 最终回答\n\n结果完整',
  steps: [],
  reply: '## 最终回答\n\n结果完整',
  log_offset: 0,
}
assert(
  extractReplyFromSnapshot(doneSnap) === '## 最终回答\n\n结果完整',
  'done snapshot extracts reply',
)

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: process log resume')
