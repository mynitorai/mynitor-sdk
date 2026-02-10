import { MyNitor } from './index';

// Mock the config
const config = { apiKey: 'test-key' };
// @ts-ignore - access private static init for testing
const sdk = MyNitor.init(config);

// @ts-ignore - access private method for testing
const callsite = sdk.getCallSite();
console.log('Callsite Info:', callsite);

if (!callsite.workflowGuess.includes(':')) {
    console.log('✅ PASS: Workflow guess does not contain function name.');
} else {
    console.error('❌ FAIL: Workflow guess still contains function name.');
}

const config2 = { apiKey: 'test-key', workflowId: 'explicit-wf' };
// @ts-ignore
const sdk2 = MyNitor.init(config2);

// Since we can't easily trigger a patched event in this tiny test, 
// we'll just check if the config saved it.
// @ts-ignore
if (sdk2.config.workflowId === 'explicit-wf') {
    console.log('✅ PASS: Config correctly stores explicit workflowId.');
} else {
    console.error('❌ FAIL: Config failed to store explicit workflowId.');
}
