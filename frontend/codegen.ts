import { CodegenConfig } from '@graphql-codegen/cli'

const config: CodegenConfig = {
  // CODEGEN_SCHEMA: introspect another backend (e.g. a worktree's on :8013).
  schema: process.env.CODEGEN_SCHEMA ?? 'http://localhost:8000/graphql',
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
