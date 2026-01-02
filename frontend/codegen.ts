import { CodegenConfig } from '@graphql-codegen/cli'

const config: CodegenConfig = {
  schema: 'http://localhost:8000/graphql',
  documents: ['src/**/*.{ts,tsx}'],
  generates: {
    './src/modules/graphql/generated/': {
      preset: 'client',
      plugins: [],
      config: {
        enumsAsTypes: true,
      },
      presetConfig: {
        gqlTagName: 'gql',
      },
    },
  },
  ignoreNoDocuments: true,
}

export default config
