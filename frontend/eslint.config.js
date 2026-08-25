/**
 * Lint rules for the frontend.
 *
 * The point of this config is not style — Prettier owns that. It is the small
 * set of rules that catch bugs `tsc` cannot see, and the hooks rules are why it
 * exists at all: a missing dependency in a `useMemo` or `useCallback` type-checks
 * perfectly and then re-renders something it should not have.
 *
 * Deliberately narrow. A linter that flags four hundred things gets `--no-verify`d
 * into irrelevance, so anything that is a matter of taste is off.
 */

import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules', 'scripts/**'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // The build defines these; they are real at runtime and absent from the
      // browser globals list.
      'no-undef': 'off',

      // `_next` and friends are how the codebase spells "required by the
      // signature, unused on purpose".
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],

      // `any` is a smell, not a defect, and the codebase has enough of it that
      // making it an error would mean fixing all of it before this config can
      // land. Warn so new ones are visible without blocking a merge.
      '@typescript-eslint/no-explicit-any': 'warn',

      // Fast refresh only works when a module exports components and nothing
      // else. Worth knowing about; not worth failing a build over.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // Tests reach for `any` and non-null assertions to build fixtures, and the
    // fast-refresh rule is meaningless in a file that never renders in the app.
    files: ['src/**/*.test.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'react-refresh/only-export-components': 'off',
    },
  }
);
