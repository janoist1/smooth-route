import { call, select } from 'redux-saga/effects'
import { actions, fetchImage } from './slice'
import { takeLatestAsync } from 'saga-toolkit'
import { client, gql } from '../graphql'
import type { GetTrainingDataQuery } from '../graphql/generated/graphql'
import { selectTrainingState } from './selectors'

const GET_TRAINING_DATA = gql(`
    query GetTrainingData($id: Int!) {
        point(id: $id) {
            imageUrl
            manualRqi
            manualTags
            manualAnnotations
            manualComment
        }
    }
`)

const SAVE_TRAINING_DATA = gql(`
    mutation SaveTrainingData($input: TrainingDataInput!) {
        saveTrainingData(input: $input)
    }
`)

// Logic to fetch image from API
// Note: saga-toolkit 'pending' action puts the argument in meta.arg
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* fetchImageWorker(action: any) {
  const pointId = action.meta.arg

  // FETCH via GraphQL
  const result: { data: GetTrainingDataQuery } = yield call([client, client.query], {
    query: GET_TRAINING_DATA,
    variables: { id: pointId },
    fetchPolicy: 'network-only', // Ensure freshness
  })
  
  console.log('fetchImageWorker', { pointId, result })

  const pt = result.data.point

  if (!pt || !pt.imageUrl) {
    throw new Error('No image found for this point')
  }

  return {
    url: pt.imageUrl.startsWith('/') ? pt.imageUrl : `/${pt.imageUrl}`,
    manualRqi: pt.manualRqi || null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    annotations: (pt.manualAnnotations || []) as any[],
    tags: pt.manualTags || [],
    manualComment: pt.manualComment || '',
  }
}

function* saveAnnotationsWorker() {
  try {
    const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)

    const imageUrl = state.imageUrl
    let filename = ''
    if (imageUrl) {
      // Need robust logic or just store filename in state.
      // For now, reuse split logic
      const parts = imageUrl.split('/')
      filename = parts[parts.length - 1]
    }

    if (!filename) {
      throw new Error('Cannot determine filename to save.')
    }

    const input = {
      imageFilename: filename, // CamelCase for GraphQL input
      manualRqi: state.manualRqi,
      annotations: state.annotations,
      tags: state.tags,
      manualComment: state.manualComment,
      metaData: {
        agent: 'antigravity-web-client',
        timestamp: new Date().toISOString(),
      },
    }

    yield call([client, client.mutate], {
      mutation: SAVE_TRAINING_DATA,
      variables: { input },
    })

    console.log('Training Data Saved Successfully')
    // We don't need to dispatch success manually, saga-toolkit handles .fulfilled
  } catch (error) {
    console.error('Failed to save training data:', error)
    throw error // This triggers .rejected
  }
}

export default [
  takeLatestAsync(fetchImage.type, fetchImageWorker),
  takeLatestAsync(actions.saveAnnotations.type, saveAnnotationsWorker),
]
