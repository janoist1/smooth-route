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
        // tsconfig has verbatimModuleSyntax: without this the generated files
        // use value imports for types and `tsc -b` (typecheck/build) fails.
        useTypeImports: true,
      },
      presetConfig: {
        gqlTagName: 'gql',
      },
    },
  },
  ignoreNoDocuments: true,
}

export default config
