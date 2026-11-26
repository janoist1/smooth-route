import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { fetchModelInfo, fetchSettings, updateSetting } from './slice'
import { gql, gqlMutate, gqlQuery } from '../graphql'

const GET_SETTINGS = gql(`
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
`)

const UPDATE_SETTING = gql(`
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
`)

const GET_MODEL_INFO = gql(`
  query GetRqiModelInfo {
    rqiModelInfo {
      available
      version
      backbone
      recipe
      head
      nTrain
      qwk
      mae
      exactAcc
      badRoadAcc
      badRoadAuc
      scaleMeaning
    }
  }
`)

function* fetchSettingsWorker() {
  const data = yield* gqlQuery({ query: GET_SETTINGS, fetchPolicy: 'network-only' })
  return data.settings
}

function* updateSettingWorker(action: SagaActionFromCreator<typeof updateSetting>) {
  const { key, value } = action.meta.arg
  const data = yield* gqlMutate({
    mutation: UPDATE_SETTING,
    variables: { input: { key, value } },
  })
  return data.updateSetting
}

function* fetchModelInfoWorker() {
  const data = yield* gqlQuery({ query: GET_MODEL_INFO, fetchPolicy: 'network-only' })
  return data.rqiModelInfo
}

export default [
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchSettings as any).type, fetchSettingsWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((updateSetting as any).type, updateSettingWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchModelInfo as any).type, fetchModelInfoWorker),
]
