module.exports = {
    root: true,
    ignorePatterns: [
        'out/**',
        '.vscode-test/**',
        '*.vsix',
    ],
    overrides: [
        {
            files: ['src/**/*.ts'],
            env: {
                es2022: true,
                node: true,
            },
            parser: '@typescript-eslint/parser',
            parserOptions: {
                ecmaVersion: 'latest',
                sourceType: 'module',
            },
            plugins: ['@typescript-eslint'],
            extends: [
                'eslint:recommended',
                'plugin:@typescript-eslint/recommended',
            ],
            rules: {
                'no-undef': 'off',
                '@typescript-eslint/no-explicit-any': 'off',
                '@typescript-eslint/no-require-imports': 'off',
                '@typescript-eslint/no-unused-vars': 'off',
                '@typescript-eslint/no-var-requires': 'off',
            },
        },
        {
            files: ['test/**/*.js', 'scripts/**/*.js'],
            env: {
                es2022: true,
                mocha: true,
                node: true,
            },
            extends: ['eslint:recommended'],
        },
    ],
};
