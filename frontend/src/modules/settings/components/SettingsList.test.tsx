import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import SettingsList from './SettingsList'

vi.mock('../../graphql', () => ({
  gql: (source: string) => source,
  client: {
    query: vi.fn(async () => ({
      data: { availableModels: ['yolov8m-seg.pt', 'yolov8s-seg-best-20260105.pt'] },
    })),
  },
}))

const setting = (key: string, value: string) => ({
  key,
  value,
  description: key,
  category: 'YOLO',
})

describe('SettingsList model settings', () => {
  afterEach(cleanup)

  it('renders the YOLO model settings as dropdowns of the available models', async () => {
    render(
      <SettingsList
        items={[setting('yolo_model', 'yolov8m-seg.pt'), setting('yolo_cleaner_model', 'yolov8m-seg.pt')]}
        categories={['YOLO']}
        saveLoading={false}
        onUpdate={() => {}}
      />,
    )

    // The option list arrives asynchronously from availableModels.
    const options = await screen.findAllByRole('option', { name: /Saját Tanított/ })
    expect(options).toHaveLength(2) // one per dropdown
    expect(screen.getAllByRole('combobox')).toHaveLength(2)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
