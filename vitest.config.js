import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{js,ts}'],
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      reportsDirectory: 'coverage',
      include: ['www/**/*.js'],
      exclude: ['www/assets/**'],
    },
    reporters: ['default', 'junit'],
    outputFile: {
      junit: 'test-results/unit-results.xml',
    },
  },
});
