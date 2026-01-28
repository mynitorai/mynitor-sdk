
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
    private pendingPromises: Set<Promise<any>> = new Set();

    private constructor(config: MyNitorConfig) {
        this.config = {
            endpoint: 'https://app.mynitor.ai/api/v1/events',
            ...config
        };

        this.setupAutoFlush();
    }

    private setupAutoFlush(): void {
        const isServerless = !!(
            process.env.AWS_LAMBDA_FUNCTION_NAME ||
            process.env.VERCEL ||
            process.env.NETLIFY ||
            process.env.FUNCTIONS_WORKER_RUNTIME
        );

        if (!isServerless && typeof process !== 'undefined' && typeof process.on === 'function') {
            // Local script or long-running process
            process.on('beforeExit', async () => {
                await this.flush();
            });
        } else if (isServerless) {
            console.warn('🚀 MyNitor: Serverless environment detected. Ensure you call `await mn.flush()` before your function returns to guarantee log delivery.');
        }
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

    /**
     * Waits for all pending network requests to complete.
     * Call this before your process exits (e.g. in AWS Lambda or scripts).
     * @param timeoutMs Maximum time to wait in milliseconds (default: 10000)
     */
    public async flush(timeoutMs: number = 10000): Promise<void> {
        if (this.pendingPromises.size === 0) return;

        console.log(`🚀 MyNitor: Flushing ${this.pendingPromises.size} pending logs...`);

        const timeoutPromise = new Promise((resolve) => setTimeout(resolve, timeoutMs));
        const allSettledPromise = Promise.allSettled(this.pendingPromises);

        await Promise.race([allSettledPromise, timeoutPromise]);
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
            // Fire and forget (but track)
            const promise = fetch(this.config.endpoint!, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    ...payload,
                    event_version: '1.0',
                    timestamp: new Date().toISOString()
                })
            })
                .then(() => { })
                .catch(() => { })
                .finally(() => {
                    this.pendingPromises.delete(promise);
                });

            this.pendingPromises.add(promise);
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
                        request_id: result.id || `req_${Date.now()}`,
                        model: result.model || body.model,
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        line_number: callsite.line,
                        input_tokens: result.usage?.prompt_tokens || 0,
                        output_tokens: result.usage?.completion_tokens || 0,
                        latency_ms: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();

                    self.sendEvent({
                        request_id: `err_${Date.now()}`,
                        model: body?.model || 'unknown',
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        latency_ms: end - start,
                        status: 'error',
                        error_type: error?.constructor?.name || 'Error'
                    });

                    throw error;
                }
            };
        } catch (e) { }
    }
}

// Global accessor
export const init = MyNitor.init;
