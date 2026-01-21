
/**
 * MyNitor AI TypeScript SDK
 * The "One-Line Magic" for AI Production Safety.
 */

export interface MyNitorConfig {
    apiKey: string;
    endpoint?: string;
}

export class MyNitor {
    private static instance: MyNitor;
    private config: MyNitorConfig;
    private isInstrumented: boolean = false;

    private constructor(config: MyNitorConfig) {
        this.config = {
            endpoint: 'https://app.mynitor.ai/api/v1/events',
            ...config
        };
    }

    public static init(config: MyNitorConfig): MyNitor {
        if (!MyNitor.instance) {
            MyNitor.instance = new MyNitor(config);
        }
        return MyNitor.instance;
    }

    /**
     * Automatically detect and wrap AI libraries like OpenAI
     */
    public instrument(): void {
        if (this.isInstrumented) return;

        this.wrapOpenAI();
        this.isInstrumented = true;
        console.log('🚀 MyNitor: Auto-instrumentation active.');
    }

    private getCallSite() {
        try {
            const err = new Error();
            const stack = err.stack?.split('\n') || [];

            // Look for the frame that called the LLM method
            // Stack usually: Error -> getCallSite -> wrapOpenAI wrapper -> USER CODE
            // We iterate to find the first frame NOT in MyNitor SDK

            for (const line of stack) {
                if (!line.includes('mynitor') && !line.includes('Error') && line.includes('/')) {
                    // Typical format: "    at Object.myFunction (/path/to/file.ts:10:5)"
                    const match = line.match(/at\s+(?:(.+?)\s+\()?(.*?):(\d+):(\d+)\)?/);
                    if (match) {
                        const func = match[1] || 'anonymous';
                        const fullPath = match[2];
                        const filename = fullPath.split('/').pop()?.split('.')[0] || 'unknown';

                        return {
                            file: fullPath,
                            line: parseInt(match[3]),
                            functionName: func,
                            workflowGuess: `${filename}:${func}`.replace('Object.', '')
                        };
                    }
                }
            }
        } catch (e) {
            // fail safe
        }
        return { file: 'unknown', line: 0, functionName: 'unknown', workflowGuess: 'default-workflow' };
    }

    private async sendEvent(payload: any) {
        try {
            // Fire and forget
            fetch(this.config.endpoint!, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    ...payload,
                    eventVersion: '1.0'
                })
            }).catch(() => { });
        } catch (e) { }
    }

    private wrapOpenAI() {
        try {
            const OpenAI = require('openai');
            if (!OpenAI || !OpenAI.OpenAI) return;

            const self = this;
            const originalChatCreate = OpenAI.OpenAI.Chat.Completions.prototype.create;

            OpenAI.OpenAI.Chat.Completions.prototype.create = async function (this: any, ...args: any[]) {
                const start = Date.now();
                const body = args[0];
                const callsite = self.getCallSite();

                try {
                    const result = await originalChatCreate.apply(this, args);
                    const end = Date.now();

                    self.sendEvent({
                        requestId: result.id || `req_${Date.now()}`,
                        model: result.model || body.model,
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: callsite.workflowGuess,
                        file: callsite.file,
                        functionName: callsite.functionName,
                        lineNumber: callsite.line,
                        inputTokens: result.usage?.prompt_tokens || 0,
                        outputTokens: result.usage?.completion_tokens || 0,
                        latencyMs: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();

                    self.sendEvent({
                        requestId: `err_${Date.now()}`,
                        model: body?.model || 'unknown',
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: callsite.workflowGuess,
                        file: callsite.file,
                        functionName: callsite.functionName,
                        latencyMs: end - start,
                        status: 'error',
                        errorType: error?.constructor?.name || 'Error'
                    });

                    throw error;
                }
            };
        } catch (e) { }
    }
}

// Global accessor
export const init = MyNitor.init;
