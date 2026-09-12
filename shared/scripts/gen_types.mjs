import { compileFromFile } from "../../frontend/node_modules/json-schema-to-typescript/dist/src/index.js";
import { fileURLToPath } from "node:url";
import { writeFile } from "node:fs/promises";
const root = new URL("../../", import.meta.url);
const code = await compileFromFile(
  fileURLToPath(new URL("shared/schemas/schema.json", root)),
  {
    bannerComment:
      "/* Generated from shared/schemas. Run npm run types. Do not edit. */",
    additionalProperties: false,
  },
);
await writeFile(new URL("frontend/src/contracts.ts", root), code);
