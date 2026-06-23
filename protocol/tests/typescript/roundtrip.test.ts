import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";
import { Ajv2020 } from "ajv/dist/2020.js";
import * as addFormatsModule from "ajv-formats";
const addFormats = addFormatsModule.default as unknown as (ajv: InstanceType<typeof Ajv2020>) => void;

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const schema = JSON.parse(readFileSync(join(root, "schema", "protocol.schema.json"), "utf-8"));
const fixturesDir = join(root, "fixtures");

// strict:false so Ajv ignores the OpenAPI-style `discriminator` keyword.
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

const fixtures = readdirSync(fixturesDir).filter((f) => f.endsWith(".json"));

describe("fixtures validate against the protocol schema (Ajv)", () => {
  it("has 20 fixtures", () => {
    expect(fixtures.length).toBe(20);
  });

  for (const file of fixtures) {
    it(`validates ${file}`, () => {
      const data = JSON.parse(readFileSync(join(fixturesDir, file), "utf-8"));
      const ok = validate(data);
      expect(validate.errors ?? []).toEqual([]);
      expect(ok).toBe(true);
    });
  }
});
