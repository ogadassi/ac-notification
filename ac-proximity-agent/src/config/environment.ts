import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config();

const envSchema = z.object({
  PORT: z.string().transform((val) => parseInt(val, 10)).default('3000'),
  HOST: z.string().default('0.0.0.0'),
  ELECTRA_IMEI: z.string().optional(),
  ELECTRA_TOKEN: z.string().optional(),
});

const parsed = envSchema.safeParse(process.env);
if (!parsed.success) {
  console.error('❌ Invalid Environment Configuration:', JSON.stringify(parsed.error.format(), null, 2));
  process.exit(1);
}
export const env = parsed.data;
