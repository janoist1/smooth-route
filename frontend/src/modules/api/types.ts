
export interface JobState {
    id: string
    status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'unknown'
    progress: number
    total: number
    message: string | null
    error: string | null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    result: any
    startedAt?: string
    completedAt?: string
    step?: string
}
