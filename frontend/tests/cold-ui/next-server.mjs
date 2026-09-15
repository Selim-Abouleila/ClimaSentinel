import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';
import next from 'next';

// Separate build output and TS config keep the regular dev/build workflow intact.
// Next may append its generated-type globs; all such changes stay in ignored output.
await mkdir('.next-cold-ui', { recursive: true });
await writeFile('.next-cold-ui/tsconfig.json', JSON.stringify({
  extends: '../tsconfig.json',
  include: ['../next-env.d.ts', '../src/**/*.ts', '../src/**/*.tsx', './types/**/*.ts', './dev/types/**/*.ts'],
  exclude: ['../node_modules'],
}, null, 2));

const app = next({
  dev: true,
  webpack: true,
  hostname: '127.0.0.1',
  port: 4318,
  conf: {
    distDir: '.next-cold-ui',
    typescript: { tsconfigPath: '.next-cold-ui/tsconfig.json' },
    devIndicators: false,
  },
});
await app.prepare();
const handler = app.getRequestHandler();
const server = createServer((request, response) => handler(request, response));
server.listen(4318, '127.0.0.1');

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server.close(async () => {
      await app.close();
      process.exit(0);
    });
    server.closeAllConnections();
  });
}
