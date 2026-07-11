import { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { Client } from 'electra-smart-js-client';
import { ElectraService } from '../services/electraService.js';

const electraService = new ElectraService();

export async function webhookRoutes(fastify: FastifyInstance) {
  // Webhook trigger endpoint
  fastify.post('/api/v1/ac/trigger', async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      if (!electraService.getIsConfigured()) {
        return reply.code(400).send({
          success: false,
          error: 'Electra Service is not authenticated. Please complete the OTP flow first.',
        });
      }
      await electraService.activateCooling(22);
      return reply.code(200).send({ success: true, message: 'Electra AC successfully triggered.' });
    } catch (error: any) {
      fastify.log.error(`Electra Execution Error: ${error.message}`);
      return reply.code(500).send({ success: false, error: error.message || 'Failed to communicate with Electra cloud.' });
    }
  });

  // Step 1: Request OTP SMS
  fastify.post('/api/v1/ac/otp/request', async (request: FastifyRequest<{ Body: { phone: string } }>, reply: FastifyReply) => {
    const { phone } = request.body || {};
    if (!phone) {
      return reply.code(400).send({ success: false, error: 'Phone number is required.' });
    }

    try {
      const imei = await Client.sendOTPRequest(phone);
      return reply.code(200).send({
        success: true,
        message: 'OTP request sent successfully.',
        imei,
      });
    } catch (error: any) {
      fastify.log.error(`OTP Request Error: ${error.message}`);
      return reply.code(500).send({ success: false, error: error.message });
    }
  });

  // Step 2: Confirm OTP and get permanent token
  fastify.post('/api/v1/ac/otp/confirm', async (
    request: FastifyRequest<{ Body: { phone: string; otp: string; imei: string } }>,
    reply: FastifyReply
  ) => {
    const { phone, otp, imei } = request.body || {};
    if (!phone || !otp || !imei) {
      return reply.code(400).send({ success: false, error: 'phone, otp, and imei are required.' });
    }

    try {
      const result = await Client.getOTPToken({ imei, phone, otp });
      return reply.code(200).send({
        success: true,
        message: 'Authentication successful. Please add these credentials to your .env file.',
        credentials: {
          ELECTRA_IMEI: result.imei,
          ELECTRA_TOKEN: result.token,
        },
      });
    } catch (error: any) {
      fastify.log.error(`OTP Confirm Error: ${error.message}`);
      return reply.code(500).send({ success: false, error: error.message });
    }
  });
}
