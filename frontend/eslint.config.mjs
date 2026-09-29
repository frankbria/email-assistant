import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

// The installed react, not the range in package.json. eslint-config-next sets
// settings.react.version = "detect", the only path that calls
// context.getFilename() — removed in ESLint 10. Pinning the version skips
// detection and keeps us compatible with a future ESLint 10 bump.
const reactVersion = createRequire(import.meta.url)("react/package.json").version;

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  { settings: { react: { version: reactVersion } } },
];

export default eslintConfig;
