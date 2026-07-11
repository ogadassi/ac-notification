import { Client } from 'electra-smart-js-client';
import { env } from '../config/environment.js';

export class ElectraService {
  private client: Client | null = null;

  constructor() {
    if (env.ELECTRA_IMEI && env.ELECTRA_TOKEN) {
      this.client = new Client({
        imei: env.ELECTRA_IMEI,
        token: env.ELECTRA_TOKEN,
      });
    }
  }

  public getIsConfigured(): boolean {
    return this.client !== null;
  }

  public async activateCooling(targetTemperatureCelsius: number = 22): Promise<void> {
    if (!this.client) {
      throw new Error('Electra Service is not authenticated. Please complete the OTP flow first.');
    }

    // Fetch devices
    const devices = await this.client.getDevices();
    if (!devices || devices.length === 0) {
      throw new Error('No AC units found in this Electra account.');
    }

    // Target the first AC device
    const deviceId = devices[0].id;

    // Set mode to COOL
    await this.client.setMode(deviceId, 'COOL');

    // Set target temperature
    await this.client.setTemperature(deviceId, targetTemperatureCelsius);
  }
}
