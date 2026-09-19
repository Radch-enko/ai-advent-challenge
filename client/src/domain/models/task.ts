export type TaskStage = 'planning' | 'execution' | 'validation' | 'report' | 'done'
export type TaskStatus = 'running' | 'pause_requested' | 'paused' | 'completed' | 'failed'
export type TaskPlanStepStatus = 'pending' | 'running' | 'completed' | 'failed'
export type TaskLlmCallStatus = 'running' | 'completed' | 'failed'

export type TaskPlanStep = {
  id: string
  order: number
  title: string
  instruction: string
  success_criteria: string
  status: TaskPlanStepStatus
  result?: string | null
  error?: string | null
}

export type TaskPlan = { steps: TaskPlanStep[] }

export type TaskValidationResult = {
  passed: boolean
  issues: string[]
  checked_step_ids: string[]
}

export type TaskLlmCall = {
  agent_log_id: string
  stage: TaskStage
  kind: string
  step_id?: string | null
  provider: string
  model: string
  status: TaskLlmCallStatus
  duration_seconds: number
  started_at: string
  completed_at?: string | null
  error?: string | null
}

export type TaskState = {
  id: string
  original_instruction: string
  status: TaskStatus
  stage: TaskStage
  current_step?: number | null
  expected_action?: string | null
  plan?: TaskPlan | null
  validation_result?: TaskValidationResult | null
  completion_report?: string | null
  llm_calls: TaskLlmCall[]
  created_at: string
  updated_at: string
  checkpoint_revision: number
  recovered: boolean
}
