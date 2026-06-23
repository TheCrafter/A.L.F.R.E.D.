import { Ajv2020 } from "ajv/dist/2020.js";
import * as addFormatsModule from "ajv-formats";
import schema from "@alfred/protocol-schema";

const addFormats = addFormatsModule.default as unknown as (
  ajv: InstanceType<typeof Ajv2020>,
) => void;

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

export interface ValidationResult {
  valid: boolean;
  errors?: string;
}

export function validateMessage(data: unknown): ValidationResult {
  const ok = validate(data) as boolean;
  if (ok) return { valid: true };
  return { valid: false, errors: ajv.errorsText(validate.errors) };
}
