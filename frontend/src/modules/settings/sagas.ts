import { call } from 'redux-saga/effects'
import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { fetchSettings, updateSetting, applyPreset } from './slice'
import type { SystemSetting } from './types'
import { client, gql } from '../graphql'

const GET_SETTINGS = gql`
  query GetSettings {
    settings {
      key
      value
      description
      example
      category
      explanation
    }
  }
`

const UPDATE_SETTING = gql`
  mutation UpdateSetting($input: UpdateSettingInput!) {
    updateSetting(input: $input) {
      key
      value
      description
      example
      category
      explanation
    }
  }
`

const APPLY_PRESET = gql`
  mutation ApplyPreset($values: JSON!) {
    applyPreset(values: $values) {
      key
      value
      description
      example
      category
      explanation
    }
  }
`

function* fetchSettingsWorker(): Generator<
  unknown,
  SystemSetting[],
  { data: { settings: SystemSetting[] } }
> {
  const response = (yield call([client, client.query], {
    query: GET_SETTINGS,
    fetchPolicy: 'network-only',
  })) as { data: { settings: SystemSetting[] } }
  return response.data.settings
}

function* updateSettingWorker(
  action: SagaActionFromCreator<typeof updateSetting>,
): Generator<unknown, SystemSetting, { data: { updateSetting: SystemSetting } }> {
  const { key, value } = action.meta.arg
  const response = (yield call([client, client.mutate], {
    mutation: UPDATE_SETTING,
    variables: { input: { key, value } },
  })) as { data: { updateSetting: SystemSetting } }
  return response.data.updateSetting
}

function* applyPresetWorker(
  action: SagaActionFromCreator<typeof applyPreset>,
): Generator<unknown, SystemSetting[], { data: { applyPreset: SystemSetting[] } }> {
  const response = (yield call([client, client.mutate], {
    mutation: APPLY_PRESET,
    variables: { values: action.meta.arg },
  })) as { data: { applyPreset: SystemSetting[] } }
  return response.data.applyPreset
}

export default [
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchSettings as any).type, fetchSettingsWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((updateSetting as any).type, updateSettingWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((applyPreset as any).type, applyPresetWorker),
]
