#!/usr/bin/env node

/**
 * MyNitor CLI - Quick Verification Utility
 */

const { init } = require('./index');

async function run() {
    const apiKey = process.env.MYNITOR_API_KEY;

    if (!apiKey) {
        console.error('❌ Error: MYNITOR_API_KEY environment variable is not set.');
        process.exit(1);
    }

    const command = process.argv[2];

    if (command === 'doctor') {
        const pkg = require('../package.json');
        console.log(`🩺 MyNitor Doctor (v${pkg.version})`);
        console.log('---------------------------');

        if (!apiKey) {
            console.error('❌ API Key: Missing (MYNITOR_API_KEY not found in env)');
        } else {
            const prefix = apiKey.substring(0, 8);
            const last4 = apiKey.substring(apiKey.length - 4);
            console.log(`✅ API Key: Detected (${prefix}...${last4})`);
        }

        try {
            console.log('📡 Testing Connection...');
            const res = await fetch('https://app.mynitor.ai/api/v1/onboarding/status', {
                headers: { 'Authorization': `Bearer ${apiKey}` }
            });

            if (res.ok) {
                const data = await res.json() as any;
                console.log(`✅ Connection: MyNitor Cloud is reachable`);
                console.log(`✅ Organization: ${data.orgId || 'Verified'}`);
            } else {
                console.error(`❌ Connection: API returned ${res.status} (${res.statusText})`);
            }
        } catch (e) {
            console.error('❌ Connection: Failed to reach app.mynitor.ai');
        }
        return;
    }

    if (command === 'mock') {
        console.log('🎭 MyNitor: Sending mock OpenAI event to Cloud API...');
        try {
            const response = await fetch('https://app.mynitor.ai/api/v1/events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify({
                    event_version: '1.0',
                    timestamp: new Date().toISOString(),
                    agent: 'mynitor-cli-mock',
                    workflow: 'diagnostic-mock',
                    provider: 'openai',
                    model: 'gpt-4o',
                    input_tokens: 150,
                    output_tokens: 450,
                    latency_ms: 1200,
                    status: 'success',
                    metadata: { type: 'diagnostic-mock' }
                })
            });

            if (response.ok) {
                console.log('✅ Mock event sent successfully!');
                console.log('✨ Check your dashboard /events page to see the generated data.');
            } else {
                const text = await response.text();
                console.error(`❌ Failed: ${response.status} ${text}`);
            }
        } catch (error) {
            console.error('❌ Network Error:', error);
        }
        return;
    }

    if (command === 'ping') {
        console.log('🚀 MyNitor: Sending verification signal to Cloud API...');

        try {
            const mn = init({
                apiKey,
                environment: 'onboarding-test'
            });

            // Trigger a manual event to verify connection
            // We use a custom internal method or just a standard track if available
            // In the current SDK, we can use the private sendEvent if it were public, 
            // or just trigger instrument() and a small log.

            // For now, let's just use a fetch directly to verify connectivity 
            // and trigger the onboarding checkmark.
            const endpoint = 'https://app.mynitor.ai/api/v1/events';
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify({
                    event_version: '1.0',
                    timestamp: new Date().toISOString(),
                    agent: 'mynitor-cli',
                    workflow: 'onboarding-ping',
                    model: 'ping-test',
                    input_tokens: 0,
                    output_tokens: 0,
                    status: 'success',
                    metadata: { source: 'cli-ping' }
                })
            });

            if (response.ok) {
                console.log('✅ Connection verified! Event sent to MyNitor Cloud.');
                console.log('✨ Check your onboarding dashboard for the green checkmark.');
            } else {
                const text = await response.text();
                console.error(`❌ Failed to send event: ${response.status} ${response.statusText}`);
                console.error(`Response: ${text}`);
                process.exit(1);
            }
        } catch (error) {
            console.error('❌ Network Error: Could not reach MyNitor Cloud.');
            console.error(error);
            process.exit(1);
        }
    } else {
        console.log('Usage: npx @mynitorai/sdk ping');
    }
}

run();
