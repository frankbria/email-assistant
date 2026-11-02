import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import { createRequire } from "node:module";

// The installed react, not the range in package.json. eslint-config-next sets
// settings.react.version = "detect", the only path that calls
// context.getFilename() — removed in ESLint 10. Pinning the version skips
// detection and keeps us compatible with a future ESLint 10 bump.
const reactVersion = createRequire(import.meta.url)("react/package.json").version;

// eslint-config-next 16 ships native flat configs; wrapping them in FlatCompat
// crashes ESLint ("Converting circular structure to JSON").
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  { settings: { react: { version: reactVersion } } },
  // `eslint .` walks everything; `next lint` used to skip generated output.
  globalIgnores(["coverage/**", "next-env.d.ts"]),
]);
