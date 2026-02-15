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
