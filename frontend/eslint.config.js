import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  { ignores: ['dist', 'src/modules/graphql/generated'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  // Module-boundary enforcement (see frontend/ARCHITECTURE.md):
  // components are the "dumb" view layer and must reach state / side-effects
  // only through a module's public API (hooks.ts / index.ts), never its slice,
  // sagas or selectors directly.
  {
    files: ['src/components/**/*.{ts,tsx}', 'src/modules/*/components/**/*.{ts,tsx}'],
    ignores: ['**/*.{test,spec}.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/slice', '**/sagas', '**/selectors'],
              message:
                'Components must use a module hook or its index (public API), not slice/sagas/selectors directly. See frontend/ARCHITECTURE.md.',
            },
          ],
        },
      ],
    },
  },
])
