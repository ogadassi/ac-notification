import Fastify from 'fastify';
import cors from '@fastify/cors';
import { env } from './config/environment.js';
import { webhookRoutes } from './routes/webhook.js';

const fastify = Fastify({ logger: true });

async function main() {
  await fastify.register(cors, { origin: true });
  await fastify.register(webhookRoutes);
  try {
    await fastify.listen({ port: env.PORT, host: env.HOST });
    console.log(`🚀 Proximity Orchestrator running on http://${env.HOST}:${env.PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
}
main();
